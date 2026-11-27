"""Tes kontrak normalisasi SL/TP (app/entry_plan.py).

Cacat yang dijaga regresi-nya (audit 26 Nov 2026):
- LLM mengirim sl=2640 tp=2650 untuk XAUUSD di harga 3577 (placeholder);
- TP dikosongkan LLM lalu kode lama mengganti tp dengan sl (order tanpa target);
- R:R 0.14-0.98 lolos ke order bodi dan baru ditolak gate setelah 4 specialist
  + synthesizer dibayar.
"""

from __future__ import annotations

import pytest

from app.entry_plan import StopPlanError, plan_stops

PX_XAU = 3577.29
ATR_M5_XAU = 2.2
ATR_H1_XAU = 5.4


def _xau(**kw):
    base = dict(symbol="XAUUSD", side="BUY", price=PX_XAU, atr_m5=ATR_M5_XAU,
                atr_ref=ATR_H1_XAU, spread=0.30,
                supports=[3566.89], resistances=[3600.37])
    base.update(kw)
    return plan_stops(**base)


def test_placeholder_sl_diperbaiki_dan_tp_dihitung_ulang():
    plan = _xau(sl=2640, tp=2650)
    assert plan["sl"] < PX_XAU < plan["tp"]
    assert plan["rr"] >= 1.5
    assert "sl" in plan["adjusted"] and "tp" in plan["adjusted"]
    assert any("terlalu jauh" in n for n in plan["notes"])


def test_tp_null_tidak_pernah_menjadi_sl():
    plan = _xau(sl=PX_XAU - 8, tp=None)
    assert plan["tp"] > PX_XAU
    assert plan["tp"] != plan["sl"]
    assert plan["rr"] >= 1.5


def test_rr_rendah_digeser_lewat_tp_bukan_sl():
    plan = _xau(sl=PX_XAU - 10, tp=PX_XAU + 2)
    assert plan["sl"] == pytest.approx(PX_XAU - 10)   # SL tidak diubah
    assert plan["rr"] >= 1.5
    assert "tp" in plan["adjusted"]


def test_sell_side_konsisten():
    plan = plan_stops(symbol="XAUUSD", side="SELL", price=PX_XAU,
                      sl=PX_XAU + 8, tp=PX_XAU - 4,
                      atr_m5=ATR_M5_XAU, atr_ref=ATR_H1_XAU)
    assert plan["sl"] > PX_XAU > plan["tp"]
    assert plan["rr"] >= 1.5


def test_sl_salah_sisi_dipindah_ke_sisi_benar():
    plan = _xau(sl=PX_XAU + 20, tp=None)   # BUY dengan SL di atas harga
    assert plan["sl"] < PX_XAU
    assert any("salah" in n for n in plan["notes"])


def test_sl_terlalu_dekat_dijauhkan():
    plan = _xau(sl=PX_XAU - 0.05, tp=None)
    assert (PX_XAU - plan["sl"]) >= 1.5 * ATR_M5_XAU * 0.99


def test_sl_terlalu_jauh_didekatkan_ke_batas_atr_h1():
    plan = _xau(sl=PX_XAU - 500, tp=None)
    assert (PX_XAU - plan["sl"]) <= 3 * ATR_H1_XAU + 0.02


def test_tanpa_atr_tidak_boleh_mengarang():
    with pytest.raises(StopPlanError):
        plan_stops(symbol="XAUUSD", side="BUY", price=PX_XAU, sl=None, tp=None)


def test_harga_tidak_valid_ditolak():
    with pytest.raises(StopPlanError):
        plan_stops(symbol="XAUUSD", side="BUY", price=None, sl=1, tp=2,
                   atr_m5=1.0)


def test_btcusd_tick_dan_skala_benar():
    plan = plan_stops(symbol="BTCUSD", side="BUY", price=60842.65,
                      sl=2640, tp=2650, atr_m5=180.0, atr_ref=700.0)
    assert plan["sl"] < 60842.65 < plan["tp"]
    assert plan["rr"] >= 1.5


def test_tp_level_resistance_dipakai_bila_cukup():
    plan = _xau(sl=PX_XAU - 8, tp=None, resistances=[3600.37, 3650.0])
    assert plan["tp"] == pytest.approx(3600.37, abs=0.02)
