"""Risk gate pure-function tests (no DB)."""
from app.risk import RiskContext, risk_gate, symbol_spec

BASE_ORDER = {
    "symbol": "XAUUSD",
    "side": "BUY",
    "volume": 0.10,
    "sl": 1998.00,
    "tp": 2005.00,
}


def ctx(**overrides) -> RiskContext:
    settings = {
        "max_volume": 1.0,
        "max_daily_drawdown": 100.0,
        "max_spread": 0.50,
        "max_orders_per_min": 10,
        "halted": False,
        "kill_switch": False,
        "allowed_symbols": ["XAUUSD"],
        "symbol_specs": {"XAUUSD": ctx_specs_xau()},
        "exposure_max_usd": 107370.0,
        "risk_per_trade_pct": 0.5,
        "daily_start_balance": 10000.0,
    }
    settings.update(overrides.pop("settings", {}))
    defaults = dict(
        settings=settings,
        bid=1999.85,
        ask=2000.15,
        tick_age_s=0.1,
        daily_pnl=0.0,
        orders_last_minute=0,
    )
    defaults.update(overrides)
    return RiskContext(**defaults)


def test_ok_order_passes():
    d = risk_gate(BASE_ORDER, ctx())
    assert d.ok, d.reasons
    assert not d.halt


def test_sl_mandatory():
    d = risk_gate({**BASE_ORDER, "sl": None}, ctx())
    assert not d.ok
    assert any("SL" in r for r in d.reasons)


def test_tp_mandatory():
    d = risk_gate({**BASE_ORDER, "tp": None}, ctx())
    assert not d.ok
    assert any("TP" in r for r in d.reasons)


def test_volume_above_max_rejected():
    d = risk_gate({**BASE_ORDER, "volume": 2.0}, ctx())
    assert not d.ok
    assert any("volume" in r for r in d.reasons)


def test_negative_volume_rejected():
    d = risk_gate({**BASE_ORDER, "volume": -1}, ctx())
    assert not d.ok


def test_volume_non_numeric_rejected():
    """Branch except (TypeError, ValueError): volume bukan angka -> ditolak."""
    for bad in ("abc", None, [0.1], {"v": 1}):
        order = dict(BASE_ORDER, volume=bad)
        d = risk_gate(order, ctx())
        assert not d.ok, bad
        assert any("volume must be positive" in x for x in d.reasons), bad


def test_wrong_sl_side_rejected():
    # BUY with SL above price is invalid
    d = risk_gate({**BASE_ORDER, "sl": 2001.00}, ctx())
    assert not d.ok
    assert any("SL < price" in r for r in d.reasons)


def test_sell_side_checks():
    sell = {**BASE_ORDER, "side": "SELL", "sl": 2002.00, "tp": 1995.00}
    assert risk_gate(sell, ctx()).ok
    # SELL with TP above price is invalid
    bad = {**BASE_ORDER, "side": "SELL", "sl": 2002.00, "tp": 2001.00}
    d = risk_gate(bad, ctx())
    assert not d.ok
    assert any("TP < price" in r for r in d.reasons)


def test_spread_filter():
    d = risk_gate(BASE_ORDER, ctx(bid=1999.00, ask=2000.80))  # spread 1.80 > 0.50
    assert not d.ok
    assert any("spread" in r for r in d.reasons)


def test_stale_tick_rejected():
    d = risk_gate(BASE_ORDER, ctx(tick_age_s=60))
    assert not d.ok
    assert any("fresh market data" in r for r in d.reasons)


def test_no_tick_rejected():
    d = risk_gate(BASE_ORDER, ctx(bid=None, ask=None, tick_age_s=None))
    assert not d.ok


def test_tick_age_3s_boundary():
    """A10 final 3,0 s: tepat 3,0 lulus, di atasnya tolak (KEPUTUSAN_OWNER §I)."""
    d = risk_gate(BASE_ORDER, ctx(tick_age_s=3.0))
    assert not any("fresh market data" in r for r in d.reasons)
    d = risk_gate(BASE_ORDER, ctx(tick_age_s=3.01))
    assert any("fresh market data" in r for r in d.reasons)


def test_tick_age_setting_overrides_default():
    """Ambang tick age dibaca dari settings, bukan hardcoded 10 s."""
    d = risk_gate(BASE_ORDER, ctx(tick_age_s=5.0, settings={"max_tick_age_s": 10.0}))
    assert not any("fresh market data" in r for r in d.reasons)


def test_daily_drawdown_auto_halt():
    """A6 (AUDIT-A2): halt dari PERSEN Ops, bukan USD max_daily_drawdown."""
    pct3 = {"kill_switch_triggers": {"daily_drawdown_pct": 3.0}}
    # -350 USD dari saldo awal 10.000 = 3,5% >= 3% -> halt
    d = risk_gate(BASE_ORDER, ctx(daily_pnl=-350.0, settings=pct3))
    assert not d.ok
    assert d.halt, "daily drawdown breach must trigger auto-halt"
    assert any("daily drawdown" in r for r in d.reasons), d.reasons
    # field profil USD yang lebih ketat tidak lagi memicu halt
    d = risk_gate(BASE_ORDER, ctx(daily_pnl=-150.0, settings={
        "max_daily_drawdown": 100.0,
        "kill_switch_triggers": {"daily_drawdown_pct": 10.0}}))
    assert d.ok, d.reasons
    assert not d.halt


def test_halted_mirror_tidak_memblokir_kill_switch_sumber_kebenaran():
    """t_4d524475: mirror 'halted' basi tidak boleh fail-closed permanen.

    Sumber kebenaran blokir = settings 'kill_switch'. Dulu mirror 'halted' yang
    tertinggal True membuat SEMUA order ditolak selamanya setelah release.
    """
    d = risk_gate(BASE_ORDER, ctx(settings={"halted": True,
                                            "kill_switch": {"active": False}}))
    assert d.ok, d.reasons
    d = risk_gate(BASE_ORDER, ctx(settings={"halted": False,
                                            "kill_switch": {"active": True,
                                                            "mode": "GLOBAL_HALT"}}))
    assert not d.ok
    assert any("kill-switch" in r for r in d.reasons)


def test_kill_switch_blocks():
    d = risk_gate(BASE_ORDER, ctx(settings={"kill_switch": True}))
    assert not d.ok


def test_rate_limit():
    d = risk_gate(BASE_ORDER, ctx(orders_last_minute=10))
    assert not d.ok
    assert any("rate limit" in r for r in d.reasons)


def test_symbol_filter():
    d = risk_gate({**BASE_ORDER, "symbol": "EURUSD"}, ctx())
    assert not d.ok
    assert any("not allowed" in r for r in d.reasons)


def test_kill_switch_mode_stop_new_orders_blocks():
    d = risk_gate(BASE_ORDER, ctx(settings={
        "kill_switch": {"active": True, "mode": "STOP_NEW_ORDERS"}}))
    assert not d.ok
    assert any("kill-switch" in r for r in d.reasons)


def test_kill_switch_mode_global_halt_blocks():
    d = risk_gate(BASE_ORDER, ctx(settings={
        "kill_switch": {"active": True, "mode": "GLOBAL_HALT"}}))
    assert not d.ok
    assert any("GLOBAL_HALT" in r for r in d.reasons)


def test_kill_switch_mode_pause_strategy_selective():
    paused = {"kill_switch": {"active": True, "mode": "PAUSE_STRATEGY"},
              "paused_strategies": ["news_trader"]}
    d = risk_gate(BASE_ORDER, ctx(settings=dict(paused)))  # strategi manual
    assert d.ok
    d = risk_gate({**BASE_ORDER, "strategy": "news_trader"}, ctx(settings=dict(paused)))
    assert not d.ok
    assert any("PAUSE_STRATEGY" in r for r in d.reasons)


def test_kill_switch_inactive_allows():
    d = risk_gate(BASE_ORDER, ctx(settings={
        "kill_switch": {"active": False, "mode": None}}))
    assert d.ok


# ------------------------------------------------------ multipair (F1)
# Spec per-simbol: XAUUSD angka A dikunci; BTCUSD dari contract spec MT5
# (contract size 1 BTC/lot terverifikasi 8 deal live; spread live median $39).

BTC_SPEC = {
    "contract_size": 1.0,
    "sl_min_usd": 10.00,
    "sl_max_usd": 1000.00,
    "vol_max_lot": 0.10,
    "spread_abs_max_usd": 100.00,
}

BTC_ORDER = {
    "symbol": "BTCUSD",
    "side": "BUY",
    "volume": 0.01,
    "sl": 58700.00,   # jarak 400.00 dari ask 59100.00
    "tp": 60100.00,
}


def btc_ctx(**overrides) -> RiskContext:
    settings = {
        "max_volume": 1.0,
        "max_daily_drawdown": 100.0,
        "max_spread": 0.50,
        "max_orders_per_min": 10,
        "halted": False,
        "kill_switch": False,
        "allowed_symbols": ["XAUUSD", "BTCUSD"],
        "symbol_specs": {"XAUUSD": dict(ctx_specs_xau()), "BTCUSD": dict(BTC_SPEC)},
        "exposure_max_usd": 107370.0,
        "risk_per_trade_pct": 0.5,
        "daily_start_balance": 10000.0,
    }
    base = dict(settings)
    base.update(overrides.pop("settings", {}))
    defaults = dict(
        settings=base,
        bid=59080.00,
        ask=59100.00,      # spread 20.00 (dalam max 100.00)
        tick_age_s=0.1,
        daily_pnl=0.0,
        orders_last_minute=0,
    )
    defaults.update(overrides)
    return RiskContext(**defaults)


def ctx_specs_xau():
    return {
        "contract_size": 100.0,
        "sl_min_usd": 0.50,
        "sl_max_usd": 15.00,
        "vol_max_lot": 0.10,
        "spread_abs_max_usd": 0.50,
    }


def test_btc_order_passes_with_own_spec():
    """Toleransi BTC: SL jarak 400 & spread 20 lolos di simbol BTCUSD."""
    d = risk_gate(BTC_ORDER, btc_ctx())
    assert d.ok, d.reasons


def test_btc_spread_would_reject_xau_but_not_btc():
    """Spread $20 menolak XAUUSD (max 0.50) tapi lolos di BTCUSD (max 100)."""
    d = risk_gate(BASE_ORDER, ctx(bid=1999.00, ask=2001.00))  # spread 2.00
    assert not d.ok
    assert any("spread" in r for r in d.reasons)
    d = risk_gate(BTC_ORDER, btc_ctx(bid=59080.00, ask=59100.00))  # spread 20.00
    assert d.ok, d.reasons


def test_btc_sl_too_close_rejected():
    # jarak 5.00 < sl_min 10.00 (tetap di bawah harga)
    d = risk_gate({**BTC_ORDER, "sl": 59095.00}, btc_ctx())
    assert not d.ok
    assert any("below min" in r for r in d.reasons)


def test_btc_sl_too_far_rejected():
    # jarak 1500.00 > sl_max 1000.00
    d = risk_gate({**BTC_ORDER, "sl": 57600.00}, btc_ctx())
    assert not d.ok
    assert any("exceeds max" in r for r in d.reasons)


def test_xau_sl_too_close_rejected():
    # jarak 0.30 < sl_min 0.50 (XAUUSD A2)
    d = risk_gate({**BASE_ORDER, "sl": 1999.85}, ctx())
    assert not d.ok
    assert any("below min" in r for r in d.reasons)


def test_xau_sl_too_far_rejected():
    # jarak 20.00 > sl_max 15.00 (XAUUSD A2)
    d = risk_gate({**BASE_ORDER, "sl": 1980.00}, ctx())
    assert not d.ok
    assert any("exceeds max" in r for r in d.reasons)


def test_xau_sl_distance_boundary_passes():
    # jarak tepat 0.50 dan 15.00 harus LOLOS batas A2 (boundary).
    # Lot 0.03 agar risk 15.00 × 100 × 0.03 = 45.00 masih di bawah 0.5% equity.
    d = risk_gate({**BASE_ORDER, "volume": 0.03, "sl": 1999.65}, ctx())  # ask - 0.50
    assert d.ok, d.reasons
    d = risk_gate({**BASE_ORDER, "volume": 0.03, "sl": 1985.15}, ctx())  # ask - 15.00
    assert d.ok, d.reasons


def test_xau_sl_max_at_full_lot_rejected_by_a5():
    """Jarak 15.00 pada lot penuh 0.10 lolos A2 tapi tertahan A5 (risk 150 > 50)."""
    d = risk_gate({**BASE_ORDER, "volume": 0.10, "sl": 1985.15}, ctx())
    assert not d.ok
    assert any("trade risk" in r for r in d.reasons)
    assert not any("SL distance" in r for r in d.reasons)


def test_btc_volume_above_per_symbol_max_rejected():
    d = risk_gate({**BTC_ORDER, "volume": 0.20}, btc_ctx())
    assert not d.ok
    assert any("exceeds max 0.1" in r for r in d.reasons)


def test_volume_uses_per_symbol_spec_not_global():
    """vol_max_lot per simbol menolak lot yang lolos global max_volume lama."""
    # 0.50 lot < global 1.0 tapi > vol_max_lot 0.10
    d = risk_gate({**BASE_ORDER, "volume": 0.50}, ctx())
    assert not d.ok
    assert any("exceeds max 0.1" in r for r in d.reasons)


def test_legacy_global_volume_backstop_still_binds():
    """max_volume global tetap dihormati sebagai backstop akun."""
    settings = {"symbol_specs": {"XAUUSD": {**ctx_specs_xau(), "vol_max_lot": 5.0}}}
    d = risk_gate({**BASE_ORDER, "volume": 2.0}, ctx(settings=settings))
    assert not d.ok
    assert any("exceeds max" in r for r in d.reasons)


def test_symbol_without_spec_rejected_fail_closed():
    """Simbol diizinkan tapi tanpa spec risk -> ditolak (fail-closed)."""
    settings = {"allowed_symbols": ["XAUUSD", "EURUSD"], "symbol_specs": {"XAUUSD": ctx_specs_xau()}}
    d = risk_gate({**BASE_ORDER, "symbol": "EURUSD"}, ctx(settings=settings))
    assert not d.ok
    assert any("no risk spec" in r for r in d.reasons)


def test_btc_spread_filter_per_symbol():
    # spread 120.00 > 100.00 -> tolak; 100.00 tepat -> lolos
    d = risk_gate(BTC_ORDER, btc_ctx(bid=59000.00, ask=59120.00))
    assert not d.ok
    assert any("spread" in r for r in d.reasons)
    d = risk_gate(BTC_ORDER, btc_ctx(bid=59000.00, ask=59100.00))
    assert d.ok, d.reasons


def test_aggregate_exposure_cross_symbol_rejects():
    """A4: eksposur XAUUSD terbuka + notional order BTCUSD > cap -> tolak."""
    # open XAUUSD 0.20 lot @ 2000 = 40.000; order BTC 0.10 lot @ 59.100 = 5.910
    # cap diturunkan jadi 45.000 -> total 45.910 > cap
    d = risk_gate({**BTC_ORDER, "volume": 0.10}, btc_ctx(open_exposure_usd=40000.0,
                                                          settings={"exposure_max_usd": 45000.0}))
    assert not d.ok
    assert any("open exposure" in r for r in d.reasons)


def test_aggregate_exposure_within_cap_passes():
    # total 40.000 + 5.910 = 45.910 <= 50.000
    d = risk_gate(BTC_ORDER, btc_ctx(open_exposure_usd=40000.0,
                                     settings={"exposure_max_usd": 50000.0}))
    assert d.ok, d.reasons


def test_aggregate_exposure_boundary_passes():
    # notional order 0.01 × 1 × 59.100 = 591.00; cap tepat 591.00 -> lolos
    d = risk_gate(BTC_ORDER, btc_ctx(open_exposure_usd=0.0,
                                     settings={"exposure_max_usd": 591.0}))
    assert d.ok, d.reasons


def test_trade_risk_a5_uses_contract_size():
    """A5: risk = jarak SL × contract size × lot ≤ 0.5% equity."""
    # XAUUSD: 0.10 lot, jarak 5.00 -> 5 × 100 × 0.10 = 50.00 = 0.5% dari 10.000
    d = risk_gate({**BASE_ORDER, "sl": 1995.15}, ctx(equity=10000.0))
    assert d.ok, d.reasons
    # jarak 5.02 -> 50.20 > 50 -> tolak
    d = risk_gate({**BASE_ORDER, "sl": 1995.13}, ctx(equity=10000.0))
    assert not d.ok
    assert any("trade risk" in r for r in d.reasons)


def test_trade_risk_a5_btc_contract_size_one():
    # BTCUSD 0.10 lot, jarak 500 -> 500 × 1 × 0.10 = 50.00 = 0.5% -> lolos
    d = risk_gate({**BTC_ORDER, "volume": 0.10, "sl": 58600.00}, btc_ctx(equity=10000.0))
    assert d.ok, d.reasons
    # jarak 501 -> 50.10 > 50 -> tolak
    d = risk_gate({**BTC_ORDER, "volume": 0.10, "sl": 58599.00}, btc_ctx(equity=10000.0))
    assert not d.ok
    assert any("trade risk" in r for r in d.reasons)


def test_trade_risk_a5_falls_back_to_daily_start_balance():
    """equity None -> fallback daily_start_balance settings."""
    d = risk_gate({**BASE_ORDER, "sl": 1995.13}, ctx(equity=None))  # risk 50.20 > 50
    assert not d.ok
    assert any("trade risk" in r for r in d.reasons)


def test_order_rate_limit_is_account_level():
    """A8 tetap akun-level: hitungan lintas simbol dikonsumsi gate apa adanya."""
    d = risk_gate(BTC_ORDER, btc_ctx(orders_last_minute=10))
    assert not d.ok
    assert any("rate limit" in r for r in d.reasons)


def test_spec_values_xauusd_match_locked_policy():
    """XAUUSD memakai angka A2/A3/A9 yang dikunci - tidak berubah."""
    s = {"symbol_specs": {"XAUUSD": ctx_specs_xau()}}
    spec = symbol_spec("XAUUSD", s)
    assert spec is not None
    assert spec["sl_min_usd"] == 0.50
    assert spec["sl_max_usd"] == 15.00
    assert spec["vol_max_lot"] == 0.10
    assert spec["spread_abs_max_usd"] == 0.50
    assert spec["contract_size"] == 100.0


def test_spec_lookup_missing_returns_none():
    assert symbol_spec("XAUUSD", {}) is None
    assert symbol_spec("XAUUSD", {"symbol_specs": {"XAUUSD": {}}}) is None


def test_legacy_mode_without_symbol_specs_keeps_old_semantics():
    """Settings tanpa symbol_specs (backtest/paper) = gate lama: tanpa cek
    jarak SL / A4 / A5, volume & spread pakai global max_volume/max_spread."""
    settings = {
        "allowed_symbols": ["XAUUSD"], "max_volume": 1.0, "max_spread": 0.50,
        "max_daily_drawdown": 100.0, "max_orders_per_min": 10,
        "symbol_specs": {},  # kosong = mode legacy
    }
    # 0.50 lot lolos (legacy max_volume 1.0), jarak SL 20.00 tidak dicek
    d = risk_gate({**BASE_ORDER, "volume": 0.50, "sl": 1980.00}, ctx(settings=settings))
    assert d.ok, d.reasons
    # simbol tanpa spec di mode legacy tidak ditolak fail-closed
    d = risk_gate(BASE_ORDER, ctx(settings=settings))
    assert d.ok, d.reasons


def test_llm_limits_none_value_keeps_default():
    """Branch raw.get(key) is None: nilai None di settings llm_risk -> default."""
    s = {"llm_risk": {"max_orders_per_min": None, "max_orders_per_day": 5}}
    d = RiskContext(settings=s, is_llm=True, llm_orders_last_minute=2,
                    llm_orders_today=0, bid=1999.85, ask=2000.15, tick_age_s=0.1)
    r = risk_gate(BASE_ORDER, d)
    # max_orders_per_min None -> default 2 tetap aktif (2 >= 2 -> limit kena)
    assert any("LLM order rate limit exceeded (max 2/min)" in x for x in r.reasons)
    # max_orders_per_day 5 override tetap terbaca (0 < 5 -> tidak kena)
    assert not any("daily order limit" in x for x in r.reasons)


def test_llm_limits_no_settings_key_uses_defaults():
    """Branch isinstance(raw, dict) False (tanpa key llm_risk) -> default penuh."""
    d = RiskContext(settings={}, is_llm=True, llm_orders_last_minute=0,
                    llm_orders_today=0, llm_cooldown_remaining_s=0.0,
                    bid=1999.85, ask=2000.15, tick_age_s=0.1)
    r = risk_gate(BASE_ORDER, d)
    assert r.ok, r.reasons


def test_llm_limits_all_none_keeps_every_default():
    """Semua nilai None -> seluruh default DEFAULT_LLM_RISK aktif."""
    s = {"llm_risk": {k: None for k in (
        "max_orders_per_min", "max_orders_per_day", "cooldown_s",
        "drawdown_pause_pct", "consecutive_failed_pause",
        "ea_offline_block_s", "check_interval_seconds")}}
    d = RiskContext(settings=s, is_llm=True, llm_orders_last_minute=0,
                    llm_orders_today=0, llm_cooldown_remaining_s=0.0,
                    bid=1999.85, ask=2000.15, tick_age_s=0.1)
    r = risk_gate(BASE_ORDER, d)
    assert r.ok, r.reasons  # tidak ada limit LLM yang menyala


def test_fresh_tick_without_bid_ask_skips_spread_filter():
    """Branch 216->225: tick segar tapi bid/ask None -> tanpa alasan spread."""
    d = ctx(bid=None, ask=None, tick_age_s=0.1)
    r = risk_gate(BASE_ORDER, d)
    assert not any("spread" in x for x in r.reasons)
    assert not any("fresh market data" in x for x in r.reasons)
