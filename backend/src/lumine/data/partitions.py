# Copyright (c) 2026 Lumine. All rights reserved.
"""Partition lifecycle management for time-series tables.

PostgreSQL RANGE-partitioned tables (ticks, bars_1m, bars_5m) require
child partitions to exist before rows in their range can be inserted.
A DEFAULT partition (created by migration 0003) catches out-of-range
rows as a safety net, but proactive creation keeps hot data in the
correct partition for retention/drop efficiency.

This module generates the DDL for daily (ticks) and monthly (bars_1m,
bars_5m) child partitions and executes it against a session. It is
designed to be called at application startup and on a schedule.

Per docs/05-data/migrations.md: partition pre-creation is a runtime
lifecycle job, NOT a migration.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy import text

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


# ── Partition spec ────────────────────────────────────────────────────────────

# ticks: daily partitions (7-day retention per physical-erd.md)
_TICKS_TABLE = "ticks"
_TICKS_UNIT = "day"

# bars_1m, bars_5m: monthly partitions (90-day retention per physical-erd.md)
_BARS_TABLES = ("bars_1m", "bars_5m")
_BARS_UNIT = "month"


def _month_start(dt: datetime) -> datetime:
    """Return the first instant of the month containing dt (tz-aware UTC)."""
    return datetime(dt.year, dt.month, 1, tzinfo=dt.tzinfo or UTC)


def _day_start(dt: datetime) -> datetime:
    """Return midnight UTC of the day containing dt."""
    return datetime(dt.year, dt.month, dt.day, tzinfo=dt.tzinfo or UTC)


def _add_months(dt: datetime, months: int) -> datetime:
    """Add months to a datetime, clamping the day to month end."""
    month_index = (dt.month - 1) + months
    year = dt.year + month_index // 12
    month = month_index % 12 + 1
    return datetime(year, month, 1, tzinfo=dt.tzinfo or UTC)


def _add_days(dt: datetime, days: int) -> datetime:
    return dt + timedelta(days=days)


def _format_partition_name(table: str, boundary: datetime) -> str:
    """Generate a deterministic child partition name: table_YYYYmmdd or table_YYYYmm."""
    if table == _TICKS_TABLE:
        return f"{table}_{boundary.strftime('%Y%m%d')}"
    return f"{table}_{boundary.strftime('%Y%m')}"


def _format_ts(dt: datetime) -> str:
    """Format a datetime as a Postgres timestamptz literal."""
    return f"'{dt.strftime('%Y-%m-%d %H:%M:%S%z')}'"


def _build_partition_ddl(table: str, boundary: datetime, span: int, unit: str) -> str:
    """Generate CREATE TABLE IF NOT EXISTS ... PARTITION OF ... FOR VALUES.

    The partition covers [boundary, boundary + span) — half-open so adjacent
    partitions don't overlap (Postgres rejects overlapping ranges).
    """
    upper = _add_days(boundary, span) if unit == "day" else _add_months(boundary, span)
    name = _format_partition_name(table, boundary)
    return (
        f"CREATE TABLE IF NOT EXISTS {name} "
        f"PARTITION OF {table} "
        f"FOR VALUES FROM ({_format_ts(boundary)}) TO ({_format_ts(upper)})"
    )


def generate_partition_ddl(
    *,
    now: datetime | None = None,
    lookahead_periods: int = 2,
) -> list[str]:
    """Return DDL statements for current + next lookahead_periods partitions.

    For ticks: the partition covering `now`'s day plus the next
    `lookahead_periods` daily partitions.
    For bars_1m/bars_5m: the partition covering `now`'s month plus the next
    `lookahead_periods` monthly partitions.

    Args:
        now: Reference timestamp. Defaults to utcnow(). tz-aware assumed.
        lookahead_periods: How many future partitions to pre-create beyond the
            current one. Must be >= 0.

    Returns:
        Ordered list of CREATE TABLE IF NOT EXISTS DDL statements.

    """
    if lookahead_periods < 0:
        msg = "lookahead_periods must be >= 0"
        raise ValueError(msg)
    ref = now or datetime.now(UTC)
    if ref.tzinfo is None:
        ref = ref.replace(tzinfo=UTC)

    statements: list[str] = []
    # ── ticks: daily ─────────────────────────────────────────────────────
    tick_day = _day_start(ref)
    for i in range(lookahead_periods + 1):
        boundary = _add_days(tick_day, i)
        statements.append(_build_partition_ddl(_TICKS_TABLE, boundary, span=1, unit=_TICKS_UNIT))

    # ── bars_1m, bars_5m: monthly ────────────────────────────────────────
    bar_month = _month_start(ref)
    for table in _BARS_TABLES:
        for i in range(lookahead_periods + 1):
            boundary = _add_months(bar_month, i)
            statements.append(_build_partition_ddl(table, boundary, span=1, unit=_BARS_UNIT))

    return statements


async def ensure_partitions(
    session: AsyncSession,
    *,
    now: datetime | None = None,
    lookahead_periods: int = 2,
) -> list[str]:
    """Create child partitions for current + next N periods on the given session.

    Idempotent — uses CREATE TABLE IF NOT EXISTS, so re-running is safe.
    Does NOT commit; the caller controls transaction boundaries.

    Args:
        session: Async SQLAlchemy session with execute() capability.
        now: Reference timestamp for determining the current period.
        lookahead_periods: Number of future periods to pre-create.

    Returns:
        The list of DDL statements executed (for logging/auditing).

    """
    statements = generate_partition_ddl(now=now, lookahead_periods=lookahead_periods)
    for stmt in statements:
        await session.execute(text(stmt))
    return statements
