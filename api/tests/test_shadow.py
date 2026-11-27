"""Tests shadow strategy runner (PRD v2.2 §9, t_f2v22a4).

Behavior tests: sinyal tercatat lengkap, fill konservatif, multi-versi,
regime/risk gate tercatat. Isolation/negative tests: test_shadow_isolation.py.
"""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app import db
from shadow import runner, store
from shadow.fill import FillModel
from shadow.specs import ShadowSpec, load_specs, params_hash

UTC = timezone.utc
NOW = datetime(2026, 11, 24, 9, 30, 30, tzinfo=UTC)  # Tuesday
TICK = {"bid": 1999.85, "ask": 2000.15, "spread": 0.30, "ts_utc": NOW}
SL, TP = 1990.0, 2015.0

INTENT = {
    "strategy_id": "london_breakout", "strategy_version": "1.0.0",
    "signal_id": "abc123", "client_order_id": "c" * 32, "symbol": "XAUUSD",
    "side": "BUY", "order_type": "MARKET", "volume": 0.04,
    "requested_price": None, "stop_loss": SL, "take_profit": TP,
    "created_at": NOW.isoformat(), "expires_at": NOW.isoformat(),
    "reason_code": "STRATEGY_SIGNAL", "reason": "unit test",
    "context_hash": "h" * 16, "sl_distance": 10.0, "risk_usd": 20.0,
}

SPEC = ShadowSpec(label="lb-test", strategy_id="london_breakout",
                  strategy_version="1.0.0", module="strategies.london_breakout")


def fake_decision(intent=INTENT, rejected=False, reason=None, signal_id="abc123"):
    return SimpleNamespace(
        strategy_id="london_breakout", status="PAPER", intent=intent,
        rejected=rejected, reason=reason, reason_code=None, breaker={},
        signal_id=signal_id)


@pytest.fixture
async def run_setup(_clean_db):
    """Settings dasar + run row + state; return (conn ctx, run_id)."""
    await db.set_setting("max_volume", 1.0)
    await db.set_setting("max_spread", 0.50)
    await db.set_setting("max_orders_per_min", 10)
    await db.set_setting("halted", False)
    await db.set_setting("kill_switch", False)
    async with db.pool().connection() as conn:
        run_id = await store.ensure_run(
            conn, strategy_id="london_breakout", strategy_version="1.0.0",
            label=SPEC.label, symbol="XAUUSD", timeframe="5m",
            params_hash=params_hash({}), code_commit="test123", config={})
        yield conn, run_id


async def _signal_rows(conn, run_id):
    rows = await conn.execute(
        "SELECT * FROM shadow_signals WHERE run_id = %s ORDER BY id", (run_id,))
    return list(await rows.fetchall())


async def test_shadow_records_full_signal(run_setup, monkeypatch):
    """PRD 9.2: harga referensi, spread, timestamp, regime, alasan tercatat."""
    conn, run_id = run_setup
    monkeypatch.setattr(runner, "_decide", lambda *a, **kw: _async(fake_decision()))
    state = dict(store.DEFAULT_STATE)
    logs = await runner.run_iteration(
        conn, state, spec=SPEC, run_id=run_id,
        settings=await db.get_settings(), params=None, tick=TICK, candles=[],
        spread_median=0.25, now=NOW, allow_entry=True,
        code_commit_hash="test123", fill_model=FillModel())
    rows = await _signal_rows(conn, run_id)
    assert len(rows) == 1
    r = rows[0]
    assert r["ts"].astimezone(UTC) == NOW
    assert float(r["ref_bid"]) == 1999.85 and float(r["ref_ask"]) == 2000.15
    assert float(r["spread"]) == 0.30
    assert r["label"] == "lb-test" and r["params_hash"]
    assert r["code_commit"] == "test123"
    assert r["is_simulation"] is True  # tanda simulasi, bukan realized (PRD 9.2)
    assert r["sim_status"] == "FILLED"
    assert float(r["sim_fill_price"]) == 2000.15 + 0.10  # BUY @ ask + slippage
    assert r["side"] == "BUY" and float(r["volume"]) == 0.04
    assert float(r["sl"]) == SL and float(r["tp"]) == TP
    assert "unit test" in (r["reason"] or "")
    assert state["position"]["entry_price"] == 2000.15 + 0.10
    assert any("SIM ENTRY" in line for line in logs)


async def test_conservative_fill_and_exit(run_setup, monkeypatch):
    """BUY fill @ ask+slippage; exit SL @ sl-slippage; komisi didiskon."""
    conn, run_id = run_setup
    monkeypatch.setattr(runner, "_decide",
                        lambda *a, **kw: _async(fake_decision()))
    state = dict(store.DEFAULT_STATE)
    await runner.run_iteration(
        conn, state, spec=SPEC, run_id=run_id,
        settings=await db.get_settings(), params=None, tick=TICK, candles=[],
        spread_median=0.25, now=NOW, allow_entry=True,
        code_commit_hash="test123", fill_model=FillModel())
    # Tick berikutnya menembus SL (bid 1989 < SL 1990)
    exit_now = datetime(2026, 11, 24, 10, 0, 0, tzinfo=UTC)
    tick2 = {"bid": 1989.00, "ask": 1989.30, "spread": 0.30, "ts_utc": exit_now}
    await runner.run_iteration(
        conn, state, spec=SPEC, run_id=run_id,
        settings=await db.get_settings(), params=None, tick=tick2, candles=[],
        spread_median=0.25, now=exit_now, allow_entry=False,
        code_commit_hash="test123", fill_model=FillModel())
    rows = await _signal_rows(conn, run_id)
    assert len(rows) == 1
    r = rows[0]
    assert r["sim_exit_reason"] == "SL"
    # BUY exit @ SL(1990) - slippage(0.10)
    assert float(r["sim_exit_price"]) == 1989.90
    # pnl = (1989.90 - 2000.25) * 100 * 0.04 - komisi 7*0.04 = -41.40 - 0.28
    assert float(r["sim_pnl_usd"]) == pytest.approx(-41.68, abs=0.01)
    assert state["position"] is None
    assert state["sim_balance"] == pytest.approx(10000.0 - 41.68, abs=0.01)


async def test_supervisor_rejection_recorded(run_setup, monkeypatch):
    conn, run_id = run_setup
    monkeypatch.setattr(
        runner, "_decide",
        lambda *a, **kw: _async(fake_decision(rejected=True, reason="circuit breaker OPEN",
                                          signal_id=None)))
    state = dict(store.DEFAULT_STATE)
    await runner.run_iteration(
        conn, state, spec=SPEC, run_id=run_id,
        settings=await db.get_settings(), params=None, tick=TICK, candles=[],
        spread_median=0.25, now=NOW, allow_entry=True,
        code_commit_hash="test123", fill_model=FillModel())
    rows = await _signal_rows(conn, run_id)
    assert len(rows) == 1
    assert rows[0]["sim_status"] == "REJECTED"
    assert "circuit breaker" in rows[0]["reason"]
    assert state["position"] is None


async def test_regime_block_recorded(run_setup, monkeypatch):
    """Regime tidak diizinkan: sinyal tercatat REGIME_BLOCKED + regime-nya."""
    conn, run_id = run_setup
    import strategies.london_breakout as lb_mod
    monkeypatch.setattr(lb_mod, "ALLOWED_REGIMES", ["TREND_UP"], raising=False)
    monkeypatch.setattr(runner, "_decide", lambda *a, **kw: _async(fake_decision()))
    state = dict(store.DEFAULT_STATE)
    regime_result = SimpleNamespace(
        label="TREND_DOWN", confidence=0.9, classifier_version="t",
        state={"last_bar_ts": NOW.isoformat()}, features={}, data_quality={},
        reason="test downtrend")
    await runner.run_iteration(
        conn, state, spec=SPEC, run_id=run_id,
        settings=await db.get_settings(), params=None, tick=TICK, candles=[],
        spread_median=0.25, now=NOW, allow_entry=True,
        regime_result=regime_result, code_commit_hash="test123",
        fill_model=FillModel())
    rows = await _signal_rows(conn, run_id)
    assert len(rows) == 1
    r = rows[0]
    assert r["sim_status"] == "REGIME_BLOCKED"
    assert r["regime_label"] == "TREND_DOWN"
    assert "ENTRY BLOCKED by regime TREND_DOWN" in r["reason"]
    assert state["position"] is None


async def test_multiple_versions_simultaneous(run_setup, monkeypatch):
    """PRD 9.2: dua versi strategi berjalan bersamaan, dua run + dua sinyal."""
    conn, run_id = run_setup
    monkeypatch.setattr(runner, "_decide", lambda *a, **kw: _async(fake_decision()))
    spec2 = ShadowSpec(label="lb-tight", strategy_id="london_breakout",
                       strategy_version="1.0.0",
                       module="strategies.london_breakout",
                       params={"max_spread_abs": 0.40})
    run2 = await store.ensure_run(
        conn, strategy_id="london_breakout", strategy_version="1.0.0",
        label="lb-tight", symbol="XAUUSD", timeframe="5m",
        params_hash=params_hash(spec2.params), code_commit="test123", config={})
    for spec, rid in ((SPEC, run_id), (spec2, run2)):
        state = dict(store.DEFAULT_STATE)
        await runner.run_iteration(
            conn, state, spec=spec, run_id=rid,
            settings=await db.get_settings(), params=None, tick=TICK, candles=[],
            spread_median=0.25, now=NOW, allow_entry=True,
            code_commit_hash="test123", fill_model=FillModel())
    for rid, label in ((run_id, "lb-test"), (run2, "lb-tight")):
        rows = await _signal_rows(conn, rid)
        assert len(rows) == 1
        assert rows[0]["label"] == label
        assert rows[0]["sim_status"] == "FILLED"


async def test_ensure_run_rehash_starts_new_run(run_setup):
    """Label sama, parameter berubah -> run lama COMPLETED, run baru RUNNING."""
    conn, run_id = run_setup
    new_id = await store.ensure_run(
        conn, strategy_id="london_breakout", strategy_version="1.0.0",
        label=SPEC.label, symbol="XAUUSD", timeframe="5m",
        params_hash="different", code_commit="test124", config={})
    assert new_id != run_id
    old = await conn.execute(
        "SELECT status, note FROM shadow_runs WHERE run_id = %s", (run_id,))
    old = await old.fetchone()
    assert old["status"] == "COMPLETED" and "spec changed" in old["note"]
    same = await store.ensure_run(
        conn, strategy_id="london_breakout", strategy_version="1.0.0",
        label=SPEC.label, symbol="XAUUSD", timeframe="5m",
        params_hash="different", code_commit="test124", config={})
    assert same == new_id  # run yang sama dipakai ulang selama tidak berubah


def test_load_specs_multiple_and_invalid():
    settings = {"shadow_strategies": [
        {"label": "a", "module": "strategies.london_breakout", "params": {}},
        {"label": "a", "module": "strategies.mean_reversion"},   # duplikat
        {"label": "", "module": "strategies.mean_reversion"},    # tanpa label
        {"label": "b", "module": "no.such.module"},              # module invalid
        {"label": "c", "module": "strategies.btc_range_breakout"},
    ]}
    specs, errors = load_specs(settings)
    assert [s.label for s in specs] == ["a", "c"]
    assert len(errors) == 3
    btc = specs[-1]
    assert btc.symbol == "BTCUSD" and btc.timeframe == "H1"
    assert btc.contract_size == 1.0


def _async(value):
    async def _coro(*a, **k):
        return value
    return _coro()
