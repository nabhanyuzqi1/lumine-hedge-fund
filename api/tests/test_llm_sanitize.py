"""Kontrak keras (sanitize) pada keluaran LLM specialist + synthesizer.

Dasar: QA live 26 Nov 2026 menemukan technical mengirim rr=1.17 (< 1.5) dan
macro menyatakan aman tanpa menyebut kalender kosong. Prompt saja tidak cukup,
jadi aturan keras ditegakkan deterministik di sini dan alasannya dicatat.
"""
from app import llm_specialists


def _ctx(status="ok", errors=None, drawdown=0.0, halt=3.0, corr=None,
         open_positions=0, unknown=0, cal_status="ok", events=None,
         minutes=None, vol_max=0.10, atr: float | None = 1.8, spread_ratio=None) -> dict:
    spread = {"avg": 0.43, "atr_m5": atr, "ratio": spread_ratio,
              "threshold": 0.2, "high": bool(spread_ratio and spread_ratio > 0.2)}
    return {"facts": {
        "symbols": {
            "XAUUSD": {"timeframes": {"M5": {"atr14": atr}}, "spread": spread,
                       "levels": {"support": 3565.57, "resistance": 3566.34,
                                  "atr_m5": atr, "squeeze": True,
                                  "reason": "harga terjepit: band S/R sempit"}},
            "BTCUSD": {"timeframes": {"M5": {"atr14": 80.8}},
                       "spread": {"avg": 40.0, "atr_m5": 80.8, "ratio": 0.5,
                                  "threshold": 0.2, "high": True}},
        },
        "macro": {"calendar": {"status": cal_status,
                               "events": events if events is not None else [],
                               "minutes_to_next_high_impact": minutes}},
        "portfolio": {
            "status": status, "errors": errors or [],
            "daily_drawdown_pct": drawdown, "correlation_h1": corr,
            "open_positions": open_positions, "worst_case_unknown_legs": unknown,
            "risk_limits": {"daily_drawdown_halt_pct": halt,
                            "symbol_specs": {"XAUUSD": {"vol_max_lot": vol_max}}},
        },
    }}


def test_technical_rr_di_bawah_minimum_diturunkan():
    data = {"setup": {"side": "long", "entry": 100.0, "sl": 99.0, "tp": 101.17,
                      "rr": 1.17}, "confidence": 0.8}
    out, notes = llm_specialists.sanitize_evidence("technical", data, _ctx(), "XAUUSD")
    assert out["setup"]["side"] == "none"
    assert out["setup"]["rr"] is None
    assert out["confidence"] <= 0.4
    assert notes


def test_technical_rr_dihitung_bila_tidak_diberikan():
    data = {"setup": {"side": "short", "entry": 100.0, "sl": 102.0, "tp": 95.0},
            "confidence": 0.7}
    out, _ = llm_specialists.sanitize_evidence("technical", data, _ctx(), "XAUUSD")
    assert out["setup"]["side"] == "short"
    assert out["setup"]["rr"] == 2.5


def test_technical_angka_tidak_lengkap_jadi_none():
    data = {"setup": {"side": "long", "entry": 100.0, "sl": None, "tp": None},
            "confidence": 0.9}
    out, _ = llm_specialists.sanitize_evidence("technical", data, _ctx(), "XAUUSD")
    assert out["setup"] == {"side": "none", "entry": None, "sl": None,
                            "tp": None, "rr": None}


def test_macro_kalender_error_jadi_tidak_diketahui():
    data = {"event_risk": "rendah", "trade_window": {"aman": True, "alasan": "x"},
            "confidence": 0.9}
    out, _ = llm_specialists.sanitize_evidence(
        "macro", data, _ctx(cal_status="error"), "XAUUSD")
    assert out["event_risk"] == "tidak_diketahui"
    assert out["trade_window"]["aman"] is False
    assert out["confidence"] <= 0.75


def test_macro_kalender_kosong_alasan_dilengkapi_dan_conf_dipangkas():
    data = {"event_risk": "rendah", "trade_window": {"aman": True, "alasan": "tenang"},
            "confidence": 0.95}
    out, notes = llm_specialists.sanitize_evidence("macro", data, _ctx(), "XAUUSD")
    assert "kalender" in out["trade_window"]["alasan"].lower()
    assert out["confidence"] <= 0.75
    assert notes


def test_macro_alasan_calendar_unavailable_dibuang_saat_kalender_ok():
    """Kalender status ok -> alasan lama tidak boleh memblokir order."""
    data = {"event_risk": "tidak_diketahui",
            "trade_window": {"aman": False, "alasan": "calendar_unavailable"},
            "confidence": 0.5}
    out, notes = llm_specialists.sanitize_evidence("macro", data, _ctx(), "XAUUSD")
    assert out["trade_window"]["aman"] is True
    assert "calendar_unavailable" not in out["trade_window"]["alasan"].lower()
    assert notes


def test_technical_squeeze_alasan_dan_level_dilampirkan():
    data = {"setup": {"side": "none", "entry": None, "sl": None, "tp": None, "rr": None},
            "confidence": 0.3, "note": ""}
    out, notes = llm_specialists.sanitize_evidence("technical", data, _ctx(), "XAUUSD")
    assert out["levels"]["support"] == 3565.57
    assert out["levels"]["squeeze"] is True
    assert "terjepit" in out["note"].lower() or "squeeze" in out["note"].lower()
    assert notes


def test_macro_high_impact_dekat_memblokir_window():
    data = {"event_risk": "rendah", "trade_window": {"aman": True}, "confidence": 0.8}
    out, _ = llm_specialists.sanitize_evidence(
        "macro", data, _ctx(minutes=12), "XAUUSD")
    assert out["event_risk"] == "tinggi"
    assert out["trade_window"]["aman"] is False


def test_sentiment_dijepit():
    data = {"sentiment": {"XAUUSD": -3, "BTCUSD": 2}, "crowding": "seimbang"}
    out, _ = llm_specialists.sanitize_evidence("sentiment", data, _ctx(), "XAUUSD")
    assert out["sentiment"] == {"XAUUSD": -1.0, "BTCUSD": 1.0}


def test_portfolio_flag_blind_hanya_tanpa_atr():
    """ATR lengkap -> BLIND_TO_VOLATILITY tidak boleh muncul (dulu selalu)."""
    data = {"room": {"XAUUSD": "boleh_tambah", "BTCUSD": "boleh_tambah"},
            "risk_flags": [], "max_new_volume": 0.05, "confidence": 0.6}
    out, _ = llm_specialists.sanitize_evidence("portfolio", data, _ctx(), "XAUUSD")
    assert "BLIND_TO_VOLATILITY" not in out["risk_flags"]
    assert out["max_new_volume"] == 0.05

    out2, _ = llm_specialists.sanitize_evidence("portfolio", data, _ctx(atr=None), "XAUUSD")
    assert "BLIND_TO_VOLATILITY" in out2["risk_flags"]
    assert out2["max_new_volume"] == 0.0


def test_portfolio_spread_tinggi_memotong_volume():
    data = {"room": {"XAUUSD": "boleh_tambah"}, "risk_flags": [],
            "max_new_volume": 0.10, "confidence": 0.6}
    out, _ = llm_specialists.sanitize_evidence(
        "portfolio", data, _ctx(spread_ratio=0.24), "XAUUSD")
    assert "SPREAD_ATR_HIGH" in out["risk_flags"]
    assert out["max_new_volume"] == 0.05  # 0.24 < 0.5 -> x0.5

    out2, _ = llm_specialists.sanitize_evidence(
        "portfolio", data, _ctx(spread_ratio=0.8), "XAUUSD")
    assert out2["max_new_volume"] == 0.03  # >= 0.5 -> x0.25


def test_portfolio_korelasi_null_dengan_posisi_memotong_volume():
    data = {"room": {"XAUUSD": "boleh_tambah"}, "risk_flags": [],
            "max_new_volume": 0.10, "confidence": 0.6}
    out, _ = llm_specialists.sanitize_evidence(
        "portfolio", data, _ctx(corr=None, open_positions=1), "XAUUSD")
    assert "CORRELATION_H1_NULL" in out["risk_flags"]
    assert out["max_new_volume"] == 0.05

    out2, _ = llm_specialists.sanitize_evidence(
        "portfolio", data, _ctx(corr=None, open_positions=0), "XAUUSD")
    assert "CORRELATION_H1_NULL" in out2["risk_flags"]
    assert out2["max_new_volume"] == 0.10  # tanpa posisi, volume utuh


def test_portfolio_volume_dibatasi_vol_max():
    data = {"room": {"XAUUSD": "boleh_tambah"}, "risk_flags": [],
            "max_new_volume": 5.0, "confidence": 0.6}
    out, _ = llm_specialists.sanitize_evidence("portfolio", data, _ctx(vol_max=0.1), "XAUUSD")
    assert out["max_new_volume"] == 0.1


def test_portfolio_hard_block_menutup_room():
    data = {"room": {"XAUUSD": "boleh_tambah"}, "risk_flags": [],
            "max_new_volume": 0.05, "confidence": 0.8}
    out, _ = llm_specialists.sanitize_evidence(
        "portfolio", data, _ctx(errors=["daily_pnl: boom"]), "XAUUSD")
    assert out["max_new_volume"] == 0.0
    assert out["room"]["XAUUSD"] in ("hold_saja", "tutup")


def test_portfolio_unknown_legs_dan_korelasi():
    data = {"room": {"XAUUSD": "boleh_tambah"}, "risk_flags": [],
            "max_new_volume": 0.10, "confidence": 0.7}
    out, _ = llm_specialists.sanitize_evidence(
        "portfolio", data, _ctx(unknown=1), "XAUUSD")
    assert "UNKNOWN_SL_LEGS" in out["risk_flags"]
    assert out["max_new_volume"] == 0.0

    out2, _ = llm_specialists.sanitize_evidence(
        "portfolio", data, _ctx(corr=-0.85, open_positions=1, unknown=0), "XAUUSD")
    assert "HIGH_CORRELATION_H1" in out2["risk_flags"]
    assert out2["max_new_volume"] == 0.05


def test_decision_volume_dipotong_dan_symbol_dinormalkan():
    evidence = {"portfolio": {"state": "ok", "data": {"max_new_volume": 0.02,
                                                      "room": {"XAUUSD": "boleh_tambah"}}}}
    data = {"kind": "order", "symbol": "BTCUSD", "side": "BUY", "volume": 0.08,
            "sl": 3500.0, "confidence": 0.7}
    out, notes = llm_specialists.sanitize_decision(data, evidence, _ctx(), "XAUUSD")
    assert out["volume"] == 0.02
    assert out["symbol"] == "XAUUSD"
    assert notes


def test_decision_room_tutup_membatalkan_order():
    evidence = {"portfolio": {"state": "ok", "data": {"max_new_volume": 0.0,
                                                      "room": {"XAUUSD": "tutup"}}}}
    data = {"kind": "layer", "symbol": "XAUUSD", "side": "BUY", "volume": 0.05}
    out, _ = llm_specialists.sanitize_decision(data, evidence, _ctx(), "XAUUSD")
    assert out["kind"] == "hold"
    assert out["volume"] is None


def test_decision_hold_tidak_disentuh():
    data = {"kind": "hold", "reasoning": "konflik", "confidence": 0.3}
    out, notes = llm_specialists.sanitize_decision(data, {}, _ctx(), "XAUUSD")
    assert out == data and notes == []
