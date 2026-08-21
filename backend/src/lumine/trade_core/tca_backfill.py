# Copyright (c) 2026 Lumine. All rights reserved.
"""Backfill TCA records for historical fills that lack them (gap B-08).

Fills created before TCA wiring (or with missing metadata) get a retroactive
TCA record computed from the authoritative tick store. The fill's own
timestamp is used as decision_ts — the honest benchmark for a backfill is
"arrival at execution time", not re-derivation.

Safety contract (mirrors tca.py):
- Missing benchmark tick = hard skip (recorded in stats), never guessed.
- Each fill commits independently; one bad row does not abort the batch.
- Idempotent: only fills WITHOUT an existing TcaRecord are processed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select

from lumine.data.models import Fill, TcaRecord
from lumine.trade_core.tca import calculate_tca, resolve_benchmark


@dataclass
class BackfillStats:
    """Outcome counters for one backfill run."""

    scanned: int = 0
    backfilled: int = 0
    skipped_no_tick: int = 0
    errors: list[str] = field(default_factory=list)


async def backfill_missing_tca(
    session: Any,
    *,
    symbol: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    regime_id: str = "backfill",
    broker_id: str = "unknown",
    account_id: str = "unknown",
    pip_value: Decimal = Decimal(1),
    pip_size: Decimal | None = None,
    calendar: Any = None,
    batch_size: int = 500,
) -> BackfillStats:
    """Create TcaRecord rows for fills that have none.

    Args:
        session: AsyncSession owned by the caller (transaction scope outside).
        symbol: optional symbol filter (e.g. "XAUUSD").
        since: optional inclusive lower bound on fill timestamp.
        until: optional exclusive upper bound on fill timestamp.
        regime_id: provenance marker; ``"backfill"`` flags non-live rows.
        broker_id: broker provenance for retro rows (unknown if untracked).
        account_id: account provenance for retro rows (unknown if untracked).
        pip_value: instrument pip value for cost conversion.
        pip_size: optional instrument pip size override.
        calendar: optional market calendar forwarded to benchmark resolution.
        batch_size: max fills processed per invocation.

    Returns:
        BackfillStats describing what happened (never raises for per-fill
        data problems — those are captured in ``stats.errors``).

    """
    stats = BackfillStats()

    statement = (
        select(Fill)
        .outerjoin(TcaRecord, TcaRecord.fill_id == Fill.fill_id)
        .where(TcaRecord.tca_id.is_(None))
        .order_by(Fill.ts.asc())
        .limit(batch_size)
    )
    if symbol is not None:
        statement = statement.where(Fill.symbol == symbol)
    if since is not None:
        statement = statement.where(Fill.ts >= since)
    if until is not None:
        statement = statement.where(Fill.ts < until)

    result = await session.execute(statement)
    fills = list(result.scalars().all())
    stats.scanned = len(fills)

    for fill in fills:
        try:
            # decision_ts = fill ts: arrival benchmark at execution time.
            benchmark = await resolve_benchmark(
                session, fill.symbol, fill.ts, calendar=calendar
            )
            calculation = calculate_tca(
                side=fill.side,
                fill_price=fill.price,
                benchmark_price=benchmark.price,
                size=fill.size,
                pip_value=pip_value,
                pip_size=pip_size,
                benchmark_source=benchmark.source,
            )
            session.add(
                TcaRecord(
                    fill_id=fill.fill_id,
                    benchmark_price=benchmark.price,
                    slippage_bps=calculation.slippage_bps,
                    slippage_cost_ccy=calculation.slippage_cost_ccy,
                    decision_ts=fill.ts,
                    regime_id=regime_id,
                    broker_id=broker_id,
                    account_id=account_id,
                    benchmark_source=f"backfill:{benchmark.source}",
                )
            )
            stats.backfilled += 1
        except ValueError as exc:
            # resolve_benchmark hard-fails when no tick exists — honest skip.
            stats.skipped_no_tick += 1
            stats.errors.append(f"fill={fill.fill_id}: {exc}")
        except Exception as exc:
            stats.errors.append(f"fill={fill.fill_id}: {type(exc).__name__}: {exc}")

    return stats


__all__ = ["BackfillStats", "backfill_missing_tca"]
