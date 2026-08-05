# Copyright (c) 2026 Lumine. All rights reserved.
"""Unit tests for partition lifecycle DDL generation."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from lumine.data.partitions import (
    _format_partition_name,
    _format_ts,
    _month_start,
    ensure_partitions,
    generate_partition_ddl,
)


class TestMonthStart:
    def test_mid_month_returns_first_day(self) -> None:
        dt = datetime(2026, 8, 15, 14, 30, tzinfo=UTC)
        assert _month_start(dt) == datetime(2026, 8, 1, tzinfo=UTC)

    def test_first_day_unchanged(self) -> None:
        dt = datetime(2026, 8, 1, 0, 0, tzinfo=UTC)
        assert _month_start(dt) == datetime(2026, 8, 1, tzinfo=UTC)

    def test_year_boundary(self) -> None:
        dt = datetime(2026, 12, 31, 23, 59, tzinfo=UTC)
        assert _month_start(dt) == datetime(2026, 12, 1, tzinfo=UTC)


class TestPartitionName:
    def test_ticks_daily_name(self) -> None:
        dt = datetime(2026, 8, 2, tzinfo=UTC)
        assert _format_partition_name("ticks", dt) == "ticks_20260802"

    def test_bars_monthly_name(self) -> None:
        dt = datetime(2026, 8, 1, tzinfo=UTC)
        assert _format_partition_name("bars_1m", dt) == "bars_1m_202608"

    def test_bars_5m_monthly_name(self) -> None:
        dt = datetime(2026, 8, 1, tzinfo=UTC)
        assert _format_partition_name("bars_5m", dt) == "bars_5m_202608"


class TestFormatTs:
    def test_formats_as_timestamptz_literal(self) -> None:
        dt = datetime(2026, 8, 2, 0, 0, tzinfo=UTC)
        assert _format_ts(dt) == "'2026-08-02 00:00:00+0000'"


class TestGeneratePartitionDdl:
    def test_default_lookahead_creates_current_plus_two(self) -> None:
        now = datetime(2026, 8, 2, 12, 0, tzinfo=UTC)
        statements = generate_partition_ddl(now=now)
        # 1 ticks table x 3 periods + 2 bars tables x 3 periods = 9 statements
        assert len(statements) == 9

    def test_lookahead_zero_creates_only_current(self) -> None:
        now = datetime(2026, 8, 2, 12, 0, tzinfo=UTC)
        statements = generate_partition_ddl(now=now, lookahead_periods=0)
        # 1 ticks + 2 bars = 3 statements
        assert len(statements) == 3

    def test_negative_lookahead_raises(self) -> None:
        with pytest.raises(ValueError, match="lookahead_periods"):
            generate_partition_ddl(lookahead_periods=-1)

    def test_ticks_partitions_are_daily_non_overlapping(self) -> None:
        now = datetime(2026, 8, 2, 12, 0, tzinfo=UTC)
        statements = generate_partition_ddl(now=now, lookahead_periods=1)
        tick_stmts = [s for s in statements if s.startswith("CREATE TABLE IF NOT EXISTS ticks_")]
        assert len(tick_stmts) == 2
        # Day 0: 2026-08-02 to 2026-08-03
        assert "FROM ('2026-08-02 00:00:00+0000') TO ('2026-08-03 00:00:00+0000')" in tick_stmts[0]
        # Day 1: 2026-08-03 to 2026-08-04
        assert "FROM ('2026-08-03 00:00:00+0000') TO ('2026-08-04 00:00:00+0000')" in tick_stmts[1]

    def test_bars_partitions_are_monthly_non_overlapping(self) -> None:
        now = datetime(2026, 8, 15, 12, 0, tzinfo=UTC)
        statements = generate_partition_ddl(now=now, lookahead_periods=1)
        bars_1m_stmts = [
            s for s in statements if s.startswith("CREATE TABLE IF NOT EXISTS bars_1m_")
        ]
        assert len(bars_1m_stmts) == 2
        # Aug: 2026-08-01 to 2026-09-01
        assert (
            "FROM ('2026-08-01 00:00:00+0000') TO ('2026-09-01 00:00:00+0000')" in bars_1m_stmts[0]
        )
        # Sep: 2026-09-01 to 2026-10-01
        assert (
            "FROM ('2026-09-01 00:00:00+0000') TO ('2026-10-01 00:00:00+0000')" in bars_1m_stmts[1]
        )

    def test_uses_create_if_not_exists(self) -> None:
        now = datetime(2026, 8, 2, tzinfo=UTC)
        statements = generate_partition_ddl(now=now, lookahead_periods=0)
        for stmt in statements:
            assert stmt.startswith("CREATE TABLE IF NOT EXISTS")

    def test_all_statements_are_partition_of(self) -> None:
        now = datetime(2026, 8, 2, tzinfo=UTC)
        statements = generate_partition_ddl(now=now, lookahead_periods=0)
        for stmt in statements:
            assert "PARTITION OF" in stmt

    def test_naive_datetime_assumed_utc(self) -> None:
        naive = datetime(2026, 8, 2, 12, 0)  # noqa: DTZ001 — intentionally naive
        statements = generate_partition_ddl(now=naive, lookahead_periods=0)
        assert len(statements) == 3
        # Should be formatted with +0000
        assert "+0000" in statements[0]

    def test_year_rollover_bars(self) -> None:
        now = datetime(2026, 12, 15, 12, 0, tzinfo=UTC)
        statements = generate_partition_ddl(now=now, lookahead_periods=1)
        bars_stmts = [s for s in statements if "bars_1m_" in s]
        # Dec 2026 → Jan 2027
        assert "FROM ('2026-12-01 00:00:00+0000') TO ('2027-01-01 00:00:00+0000')" in bars_stmts[0]
        assert "FROM ('2027-01-01 00:00:00+0000') TO ('2027-02-01 00:00:00+0000')" in bars_stmts[1]


class TestEnsurePartitions:
    """ensure_partitions (partitions.py:134-157): executes DDL, returns it, never commits."""

    async def test_executes_each_statement_via_text(self) -> None:
        # ensure_partitions (partitions.py:156) wraps every statement in
        # text() before execute — the callable passed to the session must
        # be a TextClause, not a raw string.
        session = AsyncMock()
        returned = await ensure_partitions(session, now=datetime(2026, 8, 2, 12, 0, tzinfo=UTC))

        assert len(session.execute.await_args_list) == len(returned) == 9
        for call in session.execute.await_args_list:
            clause = call.args[0]
            assert hasattr(clause, "text")
            assert "PARTITION OF" in clause.text

    async def test_returns_statements_that_were_executed(self) -> None:
        # The return value is the audit trail (docstring: "for
        # logging/auditing") — it must match what was actually sent.
        session = AsyncMock()
        returned = await ensure_partitions(
            session, now=datetime(2026, 8, 2, 12, 0, tzinfo=UTC), lookahead_periods=0
        )

        executed = [call.args[0].text for call in session.execute.await_args_list]
        assert len(returned) == 3
        assert executed == returned

    async def test_never_commits(self) -> None:
        # The docstring contract: "Does NOT commit; the caller controls
        # transaction boundaries" — any commit() inside this function
        # would break callers that batch DDL with data writes.
        session = AsyncMock()
        await ensure_partitions(session, now=datetime(2026, 8, 2, 12, 0, tzinfo=UTC))
        session.commit.assert_not_awaited()

    async def test_negative_lookahead_raises_without_executing(self) -> None:
        # ensure_partitions delegates validation to generate_partition_ddl
        # (partitions.py:154) — a bad argument must fail before any
        # statement reaches the session.
        session = AsyncMock()
        with pytest.raises(ValueError, match="lookahead_periods"):
            await ensure_partitions(session, lookahead_periods=-1)
        session.execute.assert_not_awaited()
