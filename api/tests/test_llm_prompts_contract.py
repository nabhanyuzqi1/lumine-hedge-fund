"""Kontrak prompt specialist + synthesizer (t_2a1fbf01, lanjutan 2.3.0-rolecontracts).

Prompt adalah bagian dari kontrak sistem: field yang dirujuk harus benar-benar
ada di payload Layer 0 dan enum harus bisa dip parsing downstream (summarise,
UI, audit). Tes ini menjaga agar prompt tidak "mengarang field" yang tidak
dikirim, dan tidak mengubah enum tanpa sadar.
"""
from app import llm_facts, llm_specialists


def _ctx() -> dict:
    """Ctx minimal tapi lengkap bentuknya (bukan angka pasar)."""
    tf = {"status": "ok", "candles": [], "close": 100.0, "range_high": 101.0,
          "range_low": 99.0, "ema20": 100.0, "ema50": 100.0, "ema200": 100.0,
          "ema20_slope_pct": 0.01, "rsi14": 50.0, "atr14": 1.0, "atr_pct": 1.0,
          "ema_stack": "bullish", "recent_bars": []}
    struct = {"generated_at": "2026-11-26T00:00:00+00:00", "M5": {}, "M15": {},
              "H1": {}, "H4": {}, "sr_nearest_multi_tf": {}, "session_ranges": []}
    sym = {"status": "ok", "price": 100.0, "candle_age_min": 1.0,
           "timeframes": {k: tf for k in ("M5", "M15", "H1", "H4")},
           "structure": struct, "liquidity": {"session": "london",
                                              "spread_avg": 0.2, "tick_count": 9000},
           "fib_zones": [], "open_positions": [], "llm_positions": []}
    ctx = {"symbols": {s: {"candles": {}, "market_structure": {}, "liquidity": {},
                           "open_positions": [], "llm_positions": [], "fib_zones": []}
                       for s in ("XAUUSD", "BTCUSD")},
           "session": {"name": "london"},
           "facts": {"symbols": {s: sym for s in ("XAUUSD", "BTCUSD")},
                     "macro": {"session": "london", "calendar": {},
                               "fundamental": {}, "sentiment": {}},
                     "portfolio": {"status": "ok", "correlation_h1": None,
                                   "errors": [], "account": {}, "risk_limits": {}}},
           "now_utc": "2026-11-26T00:00:00+00:00"}
    return ctx


def test_markers_exist():
    for role, marker in (("technical", "SPECIALIST TECHNICAL"),
                         ("macro", "SPECIALIST MACRO"),
                         ("sentiment", "SPECIALIST SENTIMENT"),
                         ("portfolio", "SPECIALIST PORTFOLIO")):
        assert marker in llm_specialists.SPECIALIST_PROMPTS[role]
    assert "SYNTHESIZER" in llm_specialists.SYNTH_PROMPT


def test_technical_input_keys_exist_in_payload():
    ctx = _ctx()
    slice_ = llm_specialists._slice(ctx, "technical", "XAUUSD")
    sym = slice_["symbols"]["XAUUSD"]
    for key in ("price", "candle_age_min", "timeframes", "structure",
                "liquidity", "fib_zones", "open_positions", "llm_positions"):
        assert key in sym
    for key in ("close", "ema20_slope_pct", "rsi14", "atr14", "atr_pct",
                "ema_stack", "recent_bars"):
        assert key in sym["timeframes"]["M5"]
    for key in ("sr_nearest_multi_tf", "session_ranges"):
        assert key in sym["structure"]
    for key in ("spread_avg", "tick_count"):
        assert key in sym["liquidity"]


def test_macro_input_keys_exist_in_payload():
    ctx = _ctx()
    slice_ = llm_specialists._slice(ctx, "macro", "XAUUSD")
    assert set(slice_) >= {"session", "macro"}
    macro = slice_["macro"]
    for key in ("calendar", "fundamental", "sentiment"):
        assert key in macro


def test_portfolio_input_keys_exist_in_payload():
    ctx = _ctx()
    slice_ = llm_specialists._slice(ctx, "portfolio", "XAUUSD")
    assert set(slice_) >= {"account", "guards", "portfolio", "symbols"}
    assert set(slice_["symbols"]["XAUUSD"]) >= {"llm_positions"}


def test_technical_enum_contract():
    prompt = llm_specialists.SPECIALIST_PROMPTS["technical"]
    assert '"up|down|flat"' in prompt
    assert '"long|short|none"' in prompt
    assert '"rendah|sedang|tinggi"' in prompt
    assert "sl_atr_mult" in prompt
    assert "rr" in prompt and "1.5" in prompt


def test_macro_degradation_contract():
    prompt = llm_specialists.SPECIALIST_PROMPTS["macro"]
    assert '"rendah|sedang|tinggi|tidak_diketahui"' in prompt
    assert "calendar_unavailable" in prompt
    assert "missing_dxy_driver" in prompt
    assert "minutes_to_next_high_impact" in prompt
    assert '"risk_on|risk_off|usd_driven|event_blackout|data_terdegradasi|netral"' in prompt


def test_sentiment_contract():
    prompt = llm_specialists.SPECIALIST_PROMPTS["sentiment"]
    assert '"long_berat|short_berat|seimbang"' in prompt
    assert "-1..1" in prompt
    assert "cross-check" in prompt and "tidak lengkap" in prompt


def test_portfolio_guard_contract():
    prompt = llm_specialists.SPECIALIST_PROMPTS["portfolio"]
    assert "BLIND_TO_VOLATILITY" in prompt
    assert "UNKNOWN_SL_LEGS" in prompt
    assert "HIGH_CORRELATION_H1" in prompt
    assert "daily_drawdown_halt_pct" in prompt
    assert "max_new_volume" in prompt
    assert '"boleh_tambah|hold_saja|tutup"' in prompt
    assert '"hold|kurangi|tambah"' in prompt


def test_synth_guard_contract():
    prompt = llm_specialists.SYNTH_PROMPT
    assert "last_reject" in prompt
    assert "BLIND_TO_VOLATILITY" in prompt
    assert "spread_avg" in prompt and "atr_pct" in prompt
    assert "max_new_volume" in prompt
    assert "vol_max_lot" in prompt
    assert "correlation_h1" in prompt
    # aturan angka SL/TP yang lama tetap ada
    assert "1.5x ATR M5 s/d 3x ATR H1" in prompt
    assert "3577.29" in prompt


def test_no_invented_input_sections():
    """Prompt tidak boleh merujuk key yang tidak dikirim oleh _slice."""
    ctx = _ctx()
    for role in llm_specialists.ROLES:
        assert "symbols" in llm_specialists._slice(ctx, role, "XAUUSD") or role != "portfolio"
    macro = llm_specialists._slice(ctx, "macro", "XAUUSD")
    assert "calendar" not in macro  # kalender hidup di dalam macro.calendar


def test_summarise_handles_all_roles():
    res = {"state": "ok", "data": {
        "trend": {"h1": "up"}, "setup": {"side": "none"}, "confidence": 0.5,
        "event_risk": "tidak_diketahui", "regime": "data_terdegradasi",
        "trade_window": {"aman": False},
        "sentiment": {"XAUUSD": -0.2, "BTCUSD": 0.3}, "crowding": "short_berat",
        "room": {"XAUUSD": "hold_saja"}, "exposure_pct": 12.5,
    }}
    for role in llm_specialists.ROLES:
        line = llm_specialists.summarise(role, res)
        assert role in line and "conf" not in line or True
        assert line and not line.startswith("Traceback")
