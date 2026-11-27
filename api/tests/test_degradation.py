"""Tests: Strategy Degradation Detection (PRD v2.2 §10, t_f2v22a5).

DoD kartu:
- degradation trigger teruji sesuai test: ladder NORMAL→WATCH→DEGRADED→
  HALTED, eskalasi hanya dengan konfirmasi berlapis;
- false alarm terkendali: minimum sample size, cooldown, evaluasi per
  regime, konfirmasi new-trade (pisahkan kerugian acak dari perubahan
  struktural), threshold berversi (config_hash).
- re-enable hanya owner; tidak pernah auto-deescalate.

Bagian murni tanpa DB (evaluator, indikator, gate); bagian DB di bawah.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app import degradation
from app.degradation import (
    DegradationParams,
    entry_allowed,
    entry_block_reason,
    evaluate,
    load_params,
    re_enable_state,
)

UTC = timezone.utc
T0 = datetime(2026, 11, 1, 0, 0, tzinfo=UTC)
SID = "degr_strategy"


def make_trades(n: int, *, r: float = -0.3, profit: float = -30.0,
                regime: str | None = "RANGE", mae_r: float = 0.10,
                mfe_r: float = 0.40, start: datetime = T0) -> list[dict]:
    """Trade closed sintetis deterministik (ascending closed_at)."""
    return [{
        "r": r, "profit": profit, "regime": regime,
        "mae_r": mae_r, "mfe_r": mfe_r,
        "closed_at": (start + timedelta(hours=i)).isoformat(),
    } for i in range(n)]


def good_inputs(n: int = 30, **kw) -> dict:
    """Inputs sehat: expectancy +0.2R, PF 2.0, drawdown kecil."""
    trades = make_trades(n, r=0.2, profit=20.0, **kw)
    curve = [{"ts": "", "equity": 10000.0}]
    eq = 10000.0
    for t in trades:
        eq += t["profit"]
        curve.append({"ts": t["closed_at"], "equity": eq})
    return {"trades": trades, "equity_curve": curve,
            "closed_trades_total": n}


def bad_inputs(n: int = 30, total: int | None = None, **kw) -> dict:
    """Inputs buruk: expectancy -0.3R, PF 0/0 (semua loss), dd ~9%."""
    trades = make_trades(n, **kw)
    curve = [{"ts": "", "equity": 10000.0}]
    eq = 10000.0
    for t in trades:
        eq += t["profit"]
        curve.append({"ts": t["closed_at"], "equity": eq})
    return {"trades": trades, "equity_curve": curve,
            "closed_trades_total": total if total is not None else n}


def run(inputs: dict, state: dict | None = None, now=T0,
        params: DegradationParams | None = None):
    return evaluate(strategy_id=SID, now=now, params=params or DegradationParams(),
                    state=state, inputs=inputs)


def indicator(result, name: str):
    for ind in result.indicators:
        if ind.name == name:
            return ind
    raise AssertionError(f"indicator {name} tidak ditemukan")


# ── Trigger: ladder status ──────────────────────────────────────────────────
def test_watch_requires_confirm_evals():
    """Expectancy warn-level (-0.06R): 3 evaluasi beruntun -> WATCH."""
    inputs = bad_inputs(r=-0.06, profit=-10.0)
    r1 = run(inputs)
    assert r1.status == "NORMAL"          # kandidat, belum confirm
    assert r1.target_status == "WATCH"
    r2 = run(inputs, state=r1.state, now=T0 + timedelta(minutes=5))
    assert r2.status == "NORMAL"
    r3 = run(inputs, state=r2.state, now=T0 + timedelta(minutes=10))
    assert r3.status == "WATCH"
    assert r3.escalated is True


def test_degraded_requires_confirm_and_new_trades():
    """Expectancy degraded-level: confirm 3 evaluasi + >=3 trade baru."""
    inputs = bad_inputs(r=-0.3, profit=-30.0)
    r1 = run(inputs)
    assert r1.status == "NORMAL"
    assert r1.target_status == "DEGRADED"
    # evaluasi kedua: window sama (tidak ada trade baru) -> belum eskalasi
    r2 = run(inputs, state=r1.state, now=T0 + timedelta(minutes=5))
    assert r2.status == "NORMAL"
    # evaluasi ketiga: 3 trade baru masuk window -> eskalasi DEGRADED
    inputs_new = bad_inputs(r=-0.3, profit=-30.0, total=33)
    r3 = run(inputs_new, state=r2.state, now=T0 + timedelta(minutes=10))
    assert r3.status == "DEGRADED"
    assert r3.escalated is True
    assert "trade baru" in r3.reason


def test_single_bad_eval_is_filtered_as_random_loss():
    """Satu evaluasi buruk lalu sehat -> kandidat di-reset (kerugian acak)."""
    r1 = run(bad_inputs())
    assert r1.state["confirm_status"] == "DEGRADED"
    r2 = run(good_inputs(), state=r1.state, now=T0 + timedelta(minutes=5))
    assert r2.status == "NORMAL"
    assert r2.state["confirm_status"] is None
    r3 = run(bad_inputs(), state=r2.state, now=T0 + timedelta(minutes=10))
    assert r3.status == "NORMAL"          # konfirmasi mulai dari nol lagi


def test_drawdown_halt_is_immediate():
    """Drawdown >= halt% -> HALTED langsung (bypass confirm + cooldown)."""
    curve = [{"ts": "", "equity": 10000.0}]
    eq = 10000.0
    for i in range(10):
        eq -= 130.0
        curve.append({"ts": (T0 + timedelta(hours=i)).isoformat(),
                      "equity": eq})
    inputs = good_inputs()
    inputs["equity_curve"] = curve
    result = run(inputs)
    assert result.status == "HALTED"
    assert result.escalated is True
    assert indicator(result, "drawdown").severity == 3


def test_cooldown_blocks_immediate_escalation():
    """Setelah eskalasi, eskalasi berikutnya ditahan cooldown (kecuali halt)."""
    inputs = bad_inputs()
    r1 = run(inputs)
    r2 = run(inputs, state=r1.state, now=T0 + timedelta(minutes=5))
    r3 = run(bad_inputs(total=33), state=r2.state, now=T0 + timedelta(minutes=10))
    assert r3.status == "DEGRADED"
    # dalam cooldown: kandidat WATCH/DEGRADED lain tidak menaikkan status
    cooldown_until = datetime.fromisoformat(r3.state["cooldown_until"])
    r4 = run(bad_inputs(total=36), state=r3.state,
             now=cooldown_until - timedelta(seconds=1))
    assert r4.status == "DEGRADED"
    assert r4.escalated is False
    # setelah cooldown lewat: eskalasi jalan lagi (masih buruk)
    r5 = run(bad_inputs(total=39), state=r4.state,
             now=cooldown_until + timedelta(seconds=1))
    assert r5.status == "DEGRADED"        # sudah DEGRADED, tidak menurun
    assert r5.escalated is False


def test_no_auto_deescalation_when_healthy():
    """DEGRADED tetap DEGRADED walau indikator sehat (re-enable owner saja)."""
    state = run(bad_inputs()).state
    # paksa status DEGRADED seperti hasil eskalasi
    state["status"] = "DEGRADED"
    result = run(good_inputs(), state=state)
    assert result.status == "DEGRADED"
    assert result.escalated is False


def test_re_enable_owner_only():
    """re_enable_state: dari DEGRADED -> NORMAL + riwayat; dari NORMAL raise."""
    state = run(bad_inputs()).state
    state["status"] = "DEGRADED"
    new_state = re_enable_state(state, now=T0, actor="owner", note="review selesai")
    assert new_state["status"] == "NORMAL"
    assert new_state["reenable_history"][0]["from_status"] == "DEGRADED"
    assert new_state["reenable_history"][0]["actor"] == "owner"
    assert new_state["cooldown_until"] is None
    with pytest.raises(ValueError):
        re_enable_state(new_state, now=T0, actor="owner", note="sudah NORMAL")


def test_gate_semantics():
    """NORMAL/WATCH boleh entry; DEGRADED/HALTED diblok dengan alasan PRD."""
    assert entry_allowed("NORMAL") is True
    assert entry_allowed("WATCH") is True
    assert entry_allowed("DEGRADED") is False
    assert entry_allowed("HALTED") is False
    assert entry_allowed(None) is True
    reason_deg = entry_block_reason("DEGRADED")
    reason_halt = entry_block_reason("HALTED")
    assert reason_deg is not None and "DEGRADED" in reason_deg
    assert reason_halt is not None and "HALTED" in reason_halt
    assert entry_block_reason("NORMAL") is None
    # DEGRADED vs HALTED punya alasan berbeda (tambah risiko vs stop entry)
    assert reason_deg != reason_halt


# ── Anti false alarm: sample size / per-regime ──────────────────────────────
def test_min_sample_size_blocks_trigger():
    """Sampel < min_trades: indikator nonaktif, TIDAK eskalasi."""
    inputs = bad_inputs(n=10, r=-0.5)     # 10 < min_trades 20
    result = run(inputs)
    assert result.status == "NORMAL"
    ind = indicator(result, "expectancy")
    assert ind.sample_ok is False
    assert ind.severity == 0
    assert "sampel" in ind.reason


def test_per_regime_small_group_does_not_fire():
    """Regime dengan sampel < min per-regime tidak menyalakan sinyal."""
    # 11 trade jelek di TREND_UP (< min_trades_per_regime 12), 20 bagus RANGE
    trades = (make_trades(11, r=-0.6, regime="TREND_UP")
              + make_trades(20, r=0.3, regime="RANGE"))
    curve = [{"ts": "", "equity": 10000.0}]
    result = run({"trades": trades, "closed_trades_total": 31})
    assert result.status == "NORMAL"
    # scope fallback global: expectancy pool = semua 31 trade
    # (11 jelek + 20 bagus) -> expectancy sehat
    assert indicator(result, "expectancy").sample_ok is True


def test_per_regime_qualifying_group_fires():
    """Grup regime >= min sampel yang memburuk menyalakan indikator."""
    trades = (make_trades(12, r=-0.6, regime="TREND_UP")
              + make_trades(20, r=0.3, regime="RANGE"))
    result = run({"trades": trades, "closed_trades_total": 32})
    ind = indicator(result, "expectancy")
    assert ind.sample_ok is True
    assert ind.severity == 2
    assert "per-regime" in result.reason


def test_drawdown_needs_minimum_points():
    """Kurang titik equity -> drawdown nonaktif (bukan dianggap 0%)."""
    result = run({"equity_curve": [{"ts": "", "equity": 10000.0}]})
    ind = indicator(result, "drawdown")
    assert ind.sample_ok is False


# ── Indikator murni (PRD §10.2) ─────────────────────────────────────────────
def test_expectancy_and_pf_math():
    trades = (make_trades(8, r=0.5, profit=50.0)
              + make_trades(22, r=-1.0, profit=-30.0))
    assert degradation.rolling_expectancy(trades) == pytest.approx(
        (8 * 0.5 + 22 * -1.0) / 30)
    pf = degradation.rolling_profit_factor(trades)
    assert pf == pytest.approx(8 * 50.0 / (22 * 30.0))
    # tanpa loss -> PF None (tidak diasumsikan)
    assert degradation.rolling_profit_factor(make_trades(5, profit=10.0)) is None


def test_drawdown_math():
    curve = [{"ts": "", "equity": 100.0},
             {"ts": "", "equity": 120.0},
             {"ts": "", "equity": 90.0},
             {"ts": "", "equity": 110.0}]
    dd, peak = degradation.max_drawdown_pct(curve)
    assert peak == 120.0
    assert dd == pytest.approx(25.0)      # (120-90)/120


def test_mae_mfe_math():
    trades = make_trades(4, mae_r=0.4, mfe_r=0.2)
    stats = degradation.mae_mfe_stats(trades)
    assert stats is not None
    assert stats["ratio"] == pytest.approx(2.0)
    assert stats["mae_avg_r"] == pytest.approx(0.4)


def test_spread_slippage_ratio_math():
    # median current / median baseline = 1.6 / 0.9
    assert degradation.median_ratio([1.5, 1.7, 1.6], [0.8, 1.0, 0.9]) == \
        pytest.approx(1.778, abs=0.01)
    assert degradation.median_ratio([1.0], []) is None


def test_rejection_rate_math():
    orders = ([{"status": "FILLED"}] * 8 + [{"status": "FAILED"}] * 2)
    stats = degradation.rejection_rate(orders)
    assert stats["rate"] == pytest.approx(0.2)
    assert degradation.rejection_rate([]) is None


def test_distribution_distance_math():
    cur = {"RANGE": 60, "TREND_UP": 40}
    base = {"RANGE": 90, "TREND_UP": 10}
    tv = degradation.distribution_distance(cur, base)
    assert tv == pytest.approx(0.30)      # 0.5*(|0.6-0.9|+|0.4-0.1|)
    assert degradation.distribution_distance({}, base) is None


def test_frequency_ratio_math():
    freq = {"window": 14, "window_days": 7, "baseline": 60, "baseline_days": 30}
    assert degradation.frequency_ratio(freq) == pytest.approx(1.0)
    assert degradation.frequency_ratio(
        {"window": 7, "window_days": 7, "baseline": 60, "baseline_days": 30}) == \
        pytest.approx(0.5)
    # baseline 0 -> tak terdefinisi (nonaktif, bukan tak terhingga)
    assert degradation.frequency_ratio(
        {"window": 5, "window_days": 7, "baseline": 0, "baseline_days": 30}) is None


def test_divergence_math():
    assert degradation.divergence_r([0.2, 0.3], [-0.3, -0.1]) == pytest.approx(0.45)
    assert degradation.divergence_r([0.2], []) is None


def test_psi_math_and_drift():
    import random
    rng = random.Random(7)
    base = [rng.gauss(0, 1) for _ in range(300)]
    same = [rng.gauss(0, 1) for _ in range(300)]
    shifted = [rng.gauss(2, 1) for _ in range(300)]
    psi_same = degradation.psi(base, same)
    psi_shift = degradation.psi(base, shifted)
    assert psi_same is not None and psi_same < 0.2
    assert psi_shift is not None and psi_shift > 1.0
    worst = degradation.max_feature_psi(
        {"atr": base, "adx": base}, {"atr": shifted, "adx": same}, 30)
    assert worst is not None
    assert worst["feature"] == "atr"
    # sampel kurang -> None
    assert degradation.max_feature_psi(
        {"atr": base[:10]}, {"atr": shifted[:10]}, 30) is None


# ── Versioning threshold ────────────────────────────────────────────────────
def test_config_hash_changes_with_threshold_override():
    """Override threshold via settings -> config_hash berubah (berversi)."""
    base = DegradationParams()
    custom = DegradationParams(expectancy_degraded_r=-0.50)
    assert degradation.config_hash(base) != degradation.config_hash(custom)
    settings = {"degradation": {"expectancy_degraded_r": -0.50,
                                "min_trades": 25}}
    params = load_params(settings)
    assert params.expectancy_degraded_r == -0.50
    assert params.min_trades == 25
    assert params.trade_window == base.trade_window   # key tak dioverride
    assert load_params({}) == base


def test_state_records_config_version():
    result = run(good_inputs())
    assert result.config_version == degradation.DEGRADATION_VERSION
    assert result.config_hash == degradation.config_hash(DegradationParams())
    assert result.state["config_hash"] == result.config_hash


def test_evaluate_is_deterministic():
    a = run(bad_inputs(), state=None)
    b = run(bad_inputs(), state=None)
    assert a.status == b.status
    assert a.reason == b.reason
    assert [i.severity for i in a.indicators] == [i.severity for i in b.indicators]


# ── DB: store, collector, orkestrator, gate order ───────────────────────────
async def _seed_trade(conn, *, strategy: str = SID, profit: float = -30.0,
                      entry: float = 2000.0, sl: float = 1997.0,
                      volume: float = 0.1, side: str = "BUY",
                      opened_at=None, closed_at=None, status: str = "CLOSED"):
    """Satu baris paper_orders CLOSED (r = profit / risiko 30 USD)."""
    opened = opened_at or (T0 + timedelta(hours=1))
    closed = closed_at or (opened + timedelta(hours=2))
    row = await conn.execute(
        """
        INSERT INTO paper_orders (mode, strategy, symbol, side, volume, sl, tp,
                                  status, entry_price, exit_price, profit,
                                  reason, opened_at, closed_at, created_at)
        VALUES ('PAPER', %s, 'XAUUSD', %s, %s, %s, 2010.0, %s, %s, %s, %s,
                'seed', %s, %s, %s)
        RETURNING id
        """,
        (strategy, side, volume, sl, status, entry, entry, profit,
         opened, closed, closed))
    return str((await row.fetchone())["id"])


async def _seed_regime_order_tag(conn, order_id: str, regime: str = "RANGE"):
    await conn.execute(
        """
        INSERT INTO regime_observations (symbol, timeframe, ts, regime,
                                         confidence, classifier_version,
                                         context, ref_type, ref_id)
        VALUES ('XAUUSD', '5m', now(), %s, 0.9, '1.0.0', 'ORDER',
                'paper_order', %s)
        """,
        (regime, order_id))


async def test_store_roundtrip_and_status(db_conn=None):
    """save/load state + statuses() + event append-only (PRD §10/§18)."""
    from app import db, degradation_store
    async with db.pool().connection() as conn:
        state = await degradation_store.load_state(conn, SID)
        assert state["status"] == "NORMAL"      # default tanpa row
        state["status"] = "WATCH"
        state["since"] = T0.isoformat()
        await degradation_store.save_state(conn, SID, state)
        loaded = await degradation_store.load_state(conn, SID)
        assert loaded["status"] == "WATCH"
        statuses = await degradation_store.statuses(conn)
        assert statuses[SID] == "WATCH"
        await degradation_store.record_event(
            conn, SID, trigger="EVALUATION", from_status="NORMAL",
            to_status="WATCH", reason="uji", indicators=[{"name": "x"}],
            actor="test")
        events = await degradation_store.recent_events(conn, SID)
        assert events[0]["to_status"] == "WATCH"
        # append-only: UPDATE ditolak trigger
        import psycopg
        with pytest.raises(psycopg.errors.RaiseException, match="append-only"):
            await conn.execute(
                "UPDATE degradation_events SET reason = 'rusak' "
                "WHERE strategy_id = %s", (SID,))


async def test_collect_inputs_from_seeded_ledger(db_conn=None):
    """Collector: R, equity curve, regime tag, MAE/MFE dari candles."""
    from app import db, degradation_store
    async with db.pool().connection() as conn:
        ids = []
        for i in range(24):
            oid = await _seed_trade(conn, profit=-30.0 if i % 2 == 0 else 60.0)
            await _seed_regime_order_tag(conn, oid, "RANGE")
            ids.append(oid)
        # candle utk MAE/MFE trade pertama (BUY 2000, SL 1997, 2 jam)
        first = ids[0]
        await conn.execute(
            """
            INSERT INTO candles (symbol, timeframe, ts, open, high, low, close)
            VALUES ('XAUUSD', '5m', %s, 2000.0, 2001.5, 1998.5, 2000.5),
                   ('XAUUSD', '5m', %s, 2000.5, 2002.0, 1999.0, 2001.0)
            """,
            (T0 + timedelta(hours=1, minutes=30),
             T0 + timedelta(hours=1, minutes=45)))
        settings = await db.get_settings()
        inputs = await degradation_store.collect_inputs(
            conn, strategy_id=SID, symbol="XAUUSD", timeframe="5m",
            now=T0 + timedelta(days=1), settings=settings)
    assert inputs["closed_trades_total"] == 24
    assert len(inputs["trades"]) == 24
    rs = [t["r"] for t in inputs["trades"] if t["r"] is not None]
    assert len(rs) == 24
    assert -1.0 in rs and 2.0 in rs          # -30/30 loss, +60/30 win
    assert inputs["trades"][0]["regime"] == "RANGE"
    assert inputs["trades"][0]["mae_r"] is not None   # dari candle
    assert inputs["equity_curve"][0]["equity"] == 10000.0
    assert inputs["equity_curve"][-1]["equity"] == pytest.approx(
        10000.0 + 12 * (-30.0) + 12 * 60.0)


async def test_evaluate_strategy_escalates_and_persists(db_conn=None):
    """Trigger E2E: 30 trade buruk -> evaluasi beruntun -> DEGRADED persist."""
    from app import db, degradation_store
    async with db.pool().connection() as conn:
        for i in range(30):
            await _seed_trade(conn)
        settings = await db.get_settings()
        assert "degradation" in settings       # seed migration i009
        now = T0 + timedelta(days=2)
        r1 = await degradation_store.evaluate_strategy(
            conn, strategy_id=SID, symbol="XAUUSD", timeframe="5m",
            now=now, settings=settings, notify=False)
        assert r1.status == "NORMAL"
        assert r1.target_status == "DEGRADED"
        r2 = await degradation_store.evaluate_strategy(
            conn, strategy_id=SID, symbol="XAUUSD", timeframe="5m",
            now=now + timedelta(minutes=5), settings=settings, notify=False)
        assert r2.status == "NORMAL"
        # trade baru masuk (konfirmasi new-trade) lalu evaluasi lagi
        for i in range(3):
            await _seed_trade(conn, opened_at=now - timedelta(hours=1),
                              closed_at=now + timedelta(minutes=i))
        r3 = await degradation_store.evaluate_strategy(
            conn, strategy_id=SID, symbol="XAUUSD", timeframe="5m",
            now=now + timedelta(minutes=10), settings=settings, notify=False)
        assert r3.status == "DEGRADED"
        assert r3.escalated is True
        state = await degradation_store.load_state(conn, SID)
        assert state["status"] == "DEGRADED"
        events = await degradation_store.recent_events(conn, SID)
        assert events[0]["to_status"] == "DEGRADED"
        assert events[0]["trigger"] == "EVALUATION"
        # gate: entry diblok saat DEGRADED
        assert degradation.entry_allowed(state["status"]) is False


async def test_risk_gate_blocks_degraded_strategy(db_conn=None):
    """risk_gate: order strategi DEGRADED/HALTED ditolak; NORMAL lolos."""
    from app import db, degradation_store, risk
    async with db.pool().connection() as conn:
        state = await degradation_store.load_state(conn, SID)
        state["status"] = "DEGRADED"
        await degradation_store.save_state(conn, SID, state)
        statuses = await degradation_store.statuses(conn)
    order = {"symbol": "XAUUSD", "side": "BUY", "volume": 0.01,
             "sl": 1999.0, "tp": 2005.0, "strategy": SID}
    settings = {"allowed_symbols": ["XAUUSD"],
                "symbol_specs": {"XAUUSD": {
                    "contract_size": 100.0, "tick_value": 1.0,
                    "tick_size": 0.01, "spec_verified": True,
                    "slippage_usd": 0.35, "sl_min_usd": 0.5,
                    "sl_max_usd": 15.0, "vol_max_lot": 0.1,
                    "spread_abs_max_usd": 0.5}},
                "max_volume": 1.0, "max_daily_drawdown": 100.0,
                "max_orders_per_min": 10}
    ctx = risk.RiskContext(settings=settings, bid=1999.85, ask=2000.15,
                           tick_age_s=0.5, daily_pnl=0.0,
                           orders_last_minute=0,
                           degradation_status=statuses.get(SID))
    decision = risk.risk_gate(order, ctx)
    assert decision.ok is False
    assert any("DEGRADED" in r for r in decision.reasons)
    # kontrol: status NORMAL -> tidak ada alasan degradation
    ctx_ok = risk.RiskContext(settings=settings, bid=1999.85, ask=2000.15,
                              tick_age_s=0.5, daily_pnl=0.0,
                              orders_last_minute=0, degradation_status="NORMAL")
    decision_ok = risk.risk_gate(order, ctx_ok)
    assert not any("degradation" in r for r in decision_ok.reasons)


async def test_api_re_enable_requires_2fa_owner(client, db_conn=None):
    """API: re-enable butuh 2FA (owner); GET terbuka utk user ter-autentikasi."""
    from app import db, degradation_store
    # state DEGRADED via evaluator path (persist)
    async with db.pool().connection() as conn:
        for i in range(30):
            await _seed_trade(conn)
        settings = await db.get_settings()
        now = T0 + timedelta(days=3)
        await degradation_store.evaluate_strategy(
            conn, strategy_id=SID, symbol="XAUUSD", timeframe="5m",
            now=now, settings=settings, notify=False)
        await degradation_store.evaluate_strategy(
            conn, strategy_id=SID, symbol="XAUUSD", timeframe="5m",
            now=now + timedelta(minutes=5), settings=settings, notify=False)
        # trade baru (konfirmasi new-data) lalu evaluasi ke-3 -> DEGRADED
        for i in range(3):
            await _seed_trade(conn, opened_at=now - timedelta(hours=1),
                              closed_at=now + timedelta(minutes=i))
        await degradation_store.evaluate_strategy(
            conn, strategy_id=SID, symbol="XAUUSD", timeframe="5m",
            now=now + timedelta(minutes=10), settings=settings, notify=False)
    # GET monitoring
    resp = await client.get("/strategies/degradation")
    assert resp.status_code == 200
    states = {s["strategy_id"]: s for s in resp.json()["states"]}
    assert states[SID]["status"] == "DEGRADED"
    resp = await client.get(f"/strategies/{SID}/degradation")
    assert resp.status_code == 200
    assert len(resp.json()["events"]) >= 1
    # re-enable TANPA 2FA -> 403 (butuh approval owner, PRD §10.3)
    resp = await client.post(f"/strategies/{SID}/degradation/re-enable",
                             json={"review_note": "review manual selesai"})
    assert resp.status_code == 403


async def test_api_re_enable_owner_2fa(client_2fa, db_conn=None):
    """Re-enable dengan 2FA owner: DEGRADED -> NORMAL + event REENABLE."""
    from app import db, degradation_store
    async with db.pool().connection() as conn:
        state = await degradation_store.load_state(conn, SID)
        state["status"] = "HALTED"
        state["since"] = T0.isoformat()
        await degradation_store.save_state(conn, SID, state)
    # note terlalu pendek -> validasi 422 (bukti review wajib)
    resp = await client_2fa.post(f"/strategies/{SID}/degradation/re-enable",
                                 json={"review_note": "pendek"})
    assert resp.status_code == 422
    resp = await client_2fa.post(f"/strategies/{SID}/degradation/re-enable",
                                 json={"review_note": "indikator sudah pulih, "
                                                      "review owner 24 Nov"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["from_status"] == "HALTED"
    assert body["status"] == "NORMAL"
    async with db.pool().connection() as conn:
        events = await degradation_store.recent_events(conn, SID)
        assert events[0]["trigger"] == "REENABLE_OWNER"
        assert events[0]["actor"] == "tester"
        state = await degradation_store.load_state(conn, SID)
        assert state["status"] == "NORMAL"
    # re-enable saat NORMAL -> 400
    resp = await client_2fa.post(f"/strategies/{SID}/degradation/re-enable",
                                 json={"review_note": "sudah NORMAL lagi"})
    assert resp.status_code == 400


# ═══ EOF ═══
