"""Test replay E2E shadow (PRD 9.2/9.3): window lampau, sinyal tercatat,
tripwire order tetap nol."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app import db
from shadow import replay as replay_mod
from shadow import runner, store
from shadow.loop import OrderLedgerTripwire
from shadow.specs import ShadowSpec

UTC = timezone.utc
START = datetime(2026, 11, 23, 6, 55, tzinfo=UTC)
NOW = datetime(2026, 11, 23, 9, 30, 30, tzinfo=UTC)
INTENT = {
    "strategy_id": "london_breakout", "strategy_version": "1.0.0",
    "signal_id": "r" * 32, "client_order_id": "c" * 32, "symbol": "XAUUSD",
    "side": "BUY", "order_type": "MARKET", "volume": 0.04,
    "requested_price": None, "stop_loss": 1990.0, "take_profit": 2015.0,
    "created_at": NOW.isoformat(), "expires_at": NOW.isoformat(),
    "reason_code": "STRATEGY_SIGNAL", "reason": "replay test",
    "context_hash": "h" * 16, "sl_distance": 10.0, "risk_usd": 20.0,
}
SPEC = ShadowSpec(label="lb-replay-test", strategy_id="london_breakout",
                  strategy_version="1.0.0", module="strategies.london_breakout")


def _tick(ts):
    return {"bid": 1999.85, "ask": 2000.15, "spread": 0.30, "ts_utc": ts,
            "exchange_ts": ts}


def _candle(ts):
    return {"ts": ts.isoformat(), "open": 2000.0, "high": 2001.0, "low": 1999.0,
            "close": 2000.5, "volume": 0}


@pytest.fixture
async def rp_setup(_clean_db, monkeypatch):
    await db.set_setting("max_volume", 1.0)
    await db.set_setting("max_spread", 0.50)
    await db.set_setting("max_orders_per_min", 10)
    await db.set_setting("kill_switch", False)
    await db.set_setting("halted", False)
    await db.set_setting("regime_detection_enabled", "off")

    def fake_read_ticks(minutes, now, symbol=None):
        def _tick(age_s):
            px = 2000.0 + (30 - age_s) * 0.01  # harga bergerak: pasar dianggap buka
            return {"bid": px - 0.15, "ask": px + 0.15, "spread": 0.30,
                    "ts_utc": now - timedelta(seconds=age_s),
                    "exchange_ts": now - timedelta(seconds=age_s)}
        return [_tick(s) for s in (30, 25, 20, 15, 10, 5, 2, 1)]

    async def fake_load_candles(conn, **kwargs):
        base = kwargs["now"].replace(minute=0, second=0, microsecond=0)
        return [_candle(base - timedelta(seconds=300 * i)) for i in range(60, 0, -1)]

    async def fake_decide(conn, **kwargs):
        from types import SimpleNamespace
        return SimpleNamespace(
            strategy_id="london_breakout", status="PAPER", intent=INTENT,
            rejected=False, reason=None, reason_code=None, breaker={},
            signal_id="rrr123")

    monkeypatch.setattr(replay_mod.feed, "read_ticks", fake_read_ticks)
    monkeypatch.setattr(replay_mod, "load_candles_until", fake_load_candles)
    monkeypatch.setattr(runner, "_decide", fake_decide)
    yield


async def test_replay_records_signal_and_never_orders(rp_setup, _clean_db):
    async with db.pool().connection() as conn:
        summary = await replay_mod.replay_window(
            conn, spec=SPEC, start=START, end=START + timedelta(minutes=3),
            step_s=60, settings=await db.get_settings())
        assert summary["tripwire_ok"] is True
        assert summary["steps"] == 3
        assert summary["stats"]["filled"] >= 1  # sinyal replay tercatat
        rows = await conn.execute(
            "SELECT sim_status FROM shadow_signals WHERE label = %s",
            (SPEC.label,))
        assert all(r["sim_status"] in ("FILLED", "REJECTED", "REGIME_BLOCKED")
                   for r in await rows.fetchall())
        # run replay ditutup COMPLETED dengan note jejak window
        run = await conn.execute(
            "SELECT status, note, config FROM shadow_runs WHERE label = %s",
            (SPEC.label,))
        r = await run.fetchone()
        assert r["status"] == "COMPLETED"
        assert r["config"].get("replay") is True
        # ledger order tetap kosong (DoD: shadow tak bisa kirim order)
        for table in ("orders", "bridge_commands", "paper_orders"):
            n = await conn.execute(f"SELECT count(*) AS n FROM {table}")
            assert (await n.fetchone())["n"] == 0


async def test_replay_run_row_isolated_per_label(rp_setup):
    async with db.pool().connection() as conn:
        await replay_mod.replay_window(
            conn, spec=SPEC, start=START, end=START + timedelta(minutes=2),
            step_s=60, settings=await db.get_settings())
        runs = await conn.execute(
            "SELECT count(*) AS n FROM shadow_runs WHERE label = %s",
            (SPEC.label,))
        assert (await runs.fetchone())["n"] == 1
