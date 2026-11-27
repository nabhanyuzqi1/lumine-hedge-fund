"""Regression tests: paper runner entry/close path must persist (QA F-1).

F-1 (t_36e5fb93): run_iteration called store.insert_order without the
required conn argument, so the first real paper signal crashed with
TypeError before any row reached paper_orders. The old tests never
exercised the non-dry entry path against the database.

These tests drive runner.run_iteration directly with dry=False against the
per-run test database (conftest isolation: fund2_test_*, TELEGRAM_ALERTS_OFF=1)
and assert the INSERT/UPDATE actually happened.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app import db
from paper import runner
from paper.store import DEFAULT_STATE
from strategies.mean_reversion import STRATEGY_ID, OrderIntent, StrategyParams

UTC = timezone.utc
NOW = datetime(2026, 11, 23, 9, 30, 30, tzinfo=UTC)  # Monday, within entry window

TICK = {"bid": 1999.85, "ask": 2000.15, "spread": 0.30, "ts_utc": NOW}
INTENT = OrderIntent(symbol="XAUUSD", side="BUY", volume=0.04, sl=1990.0,
                     tp=2015.0, strategy=STRATEGY_ID, reason="regression F-1")


def make_spec(intent):
    spec = runner.StrategySpec(
        id=STRATEGY_ID, state_key="runner_regression_test",
        params_cls=StrategyParams, decide=lambda context, params: intent)
    return spec


async def _paper_order_rows(conn):
    rows = await conn.execute(
        "SELECT * FROM paper_orders WHERE mode = 'PAPER' ORDER BY created_at")
    return list(await rows.fetchall())


async def test_entry_without_dry_persists_paper_order(_clean_db):
    """The F-1 regression: dry=False entry must reach the paper_orders INSERT."""
    spec = make_spec(INTENT)
    async with db.pool().connection() as conn:
        state = dict(DEFAULT_STATE)
        logs = await runner.run_iteration(
            conn, state, spec=spec, mode="PAPER", settings=await db.get_settings(),
            params=StrategyParams(), tick=TICK, candles=[], spread_median=0.25,
            now=NOW, allow_entry=True, dry=False)

        assert any(line.startswith("ENTRY BUY") for line in logs), logs
        rows = await _paper_order_rows(conn)

    assert len(rows) == 1, "entry with dry=False must INSERT exactly one paper order"
    row = rows[0]
    assert row["status"] == "OPEN"
    assert row["side"] == "BUY"
    assert float(row["volume"]) == 0.04
    assert float(row["entry_price"]) == 2000.15  # filled at ask
    assert float(row["sl"]) == 1990.0 and float(row["tp"]) == 2015.0
    assert row["strategy"] == STRATEGY_ID
    assert state["position"]["order_id"] == str(row["id"])
    assert state["position"]["entry_price"] == 2000.15


async def test_dry_entry_writes_nothing(_clean_db):
    """dry=True keeps the ledger empty (guards the branch the bug hid behind)."""
    spec = make_spec(INTENT)
    async with db.pool().connection() as conn:
        state = dict(DEFAULT_STATE)
        logs = await runner.run_iteration(
            conn, state, spec=spec, mode="PAPER", settings=await db.get_settings(),
            params=StrategyParams(), tick=TICK, candles=[], spread_median=0.25,
            now=NOW, allow_entry=True, dry=True)

        rows = await _paper_order_rows(conn)

    assert any(line.startswith("ENTRY BUY") for line in logs), logs
    assert rows == []
    assert state["position"]["order_id"].startswith("dry-")


async def test_close_after_entry_updates_paper_order(_clean_db):
    """Full round trip: persisted entry, then TP exit updates the same row."""
    spec = make_spec(INTENT)
    async with db.pool().connection() as conn:
        state = dict(DEFAULT_STATE)
        await runner.run_iteration(
            conn, state, spec=spec, mode="PAPER", settings=await db.get_settings(),
            params=StrategyParams(), tick=TICK, candles=[], spread_median=0.25,
            now=NOW, allow_entry=True, dry=False)

        bar = {"open": 2001.0, "high": 2016.0, "low": 2000.5, "close": 2015.5}
        close_logs = await runner.run_iteration(
            conn, state, spec=spec, mode="PAPER", settings=await db.get_settings(),
            params=StrategyParams(), tick=TICK, candles=[], spread_median=0.25,
            now=NOW + timedelta(minutes=5), allow_entry=False, bar=bar, dry=False)

        rows = await _paper_order_rows(conn)

    assert any(line.startswith("CLOSE BUY") for line in close_logs), close_logs
    assert len(rows) == 1, "close must UPDATE the entry row, not create a new one"
    row = rows[0]
    assert row["status"] == "CLOSED"
    assert float(row["exit_price"]) == 2015.0  # TP fill
    assert float(row["profit"]) == pytest.approx((2015.0 - 2000.15) * 0.04 * 100)
    assert row["closed_at"] is not None
    assert state["position"] is None
    assert state["balance"] == 10000.0 + float(row["profit"])
