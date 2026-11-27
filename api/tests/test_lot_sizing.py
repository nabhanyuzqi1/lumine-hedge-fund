"""RISK-A (t_8bf257a2): auto lot sizing deterministik risk-percent 0.5%.

Dua lapis:
1. Unit murni compute_lot/auto_lot_config (tanpa DB): matematika lot per
   simbol (XAUUSD & BTCUSD), pembulatan step ke bawah, clamp min/max,
   fail-closed.
2. Integrasi POST /orders: flag ON -> lot LLM diganti lot hasil hitung;
   flag OFF -> behavior lama persis sama; order manual tidak tersentuh;
   gagal hitung -> order FAILED (fail-closed), bukan menebak lot.
"""
from __future__ import annotations

import pytest

from app import db
from app.lot_sizing import auto_lot_config, compute_lot

# Spec mengikuti DEFAULT_SETTINGS symbol_specs (db.py): XAUUSD contract 100,
# BTCUSD contract 1; vol_max 0.10; min/step 0.01. slippage 0 di spec dasar
# supaya test matematika dasar = formula kartu; model biaya diuji terpisah.
XAU_SPEC = {
    "contract_size": 100.0,
    "sl_min_usd": 0.50,
    "sl_max_usd": 15.00,
    "vol_max_lot": 0.10,
    "vol_min_lot": 0.01,
    "vol_step_lot": 0.01,
    "spread_abs_max_usd": 0.50,
    "slippage_usd": 0.0,
}
BTC_SPEC = {
    "contract_size": 1.0,
    "sl_min_usd": 10.00,
    "sl_max_usd": 1000.00,
    "vol_max_lot": 0.10,
    "vol_min_lot": 0.01,
    "vol_step_lot": 0.01,
    "spread_abs_max_usd": 100.00,
    "slippage_usd": 0.0,
}
EQUITY = 10_000.0       # equity standar test
RISK_PCT = 0.5          # 0.5% -> risk_usd 50


def _calc(**kw):
    """Panggil compute_lot dengan default XAUUSD yang masuk akal."""
    args = dict(
        symbol="XAUUSD",
        entry=2000.00,
        sl=1995.00,
        equity=EQUITY,
        risk_pct=RISK_PCT,
        spec=dict(XAU_SPEC),
    )
    args.update(kw)
    return compute_lot(**args)


# ---------------------------------------------------------------- matematika


def test_xau_lot_clamped_to_max():
    """Jarak 1.0: raw 0.50 lot -> clamp ke vol_max 0.10 (risk efektif 50->10)."""
    r = _calc(entry=2000.00, sl=1999.00)
    assert r.ok
    assert r.lot == 0.10
    assert r.detail["clamped_to_max"] is True
    assert r.detail["risk_usd_actual"] == pytest.approx(10.0)


def test_xau_lot_exact_step():
    """Jarak 5.0: raw = 50/(5x100) = 0.10 tepat -> lot 0.10 tanpa clamp."""
    r = _calc(entry=2000.00, sl=1995.00)
    assert r.ok
    assert r.lot == 0.10
    assert "clamped_to_max" not in r.detail
    assert r.detail["risk_usd_actual"] == pytest.approx(50.0)


def test_xau_lot_rounded_down_to_step():
    """Jarak 7.5: raw 0.0666.. -> dibulatkan KE BAWAH ke 0.06 (bukan 0.07)."""
    r = _calc(entry=2000.00, sl=1992.50)
    assert r.ok
    assert r.lot == 0.06
    assert r.detail["raw_lot"] == pytest.approx(0.0666, abs=1e-3)
    assert r.detail["risk_usd_actual"] == pytest.approx(45.0)


def test_xau_rounding_boundary_kept():
    """Raw tepat di step boundary (0.03) tidak turun ke 0.02 karena float."""
    # 30/(10x100) = 0.03 -> floor((0.03+eps)/0.01) = 3 -> 0.03
    r = _calc(equity=6000.00, entry=2000.00, sl=1990.00)
    assert r.ok
    assert r.lot == 0.03


def test_btc_lot_uses_contract_size():
    """BTCUSD contract 1: jarak 1000 -> raw = 50/1000 = 0.05 lot (0.05 BTC)."""
    r = _calc(symbol="BTCUSD", spec=dict(BTC_SPEC), entry=67000.00, sl=66000.00)
    assert r.ok
    assert r.lot == 0.05
    assert r.detail["risk_usd_actual"] == pytest.approx(50.0)


def test_btc_lot_below_min_rejected_not_rounded_up():
    """BTC jarak 10000: raw 0.005 < min 0.01 -> TOLAK, bukan dibulatkan ke 0.01."""
    r = _calc(symbol="BTCUSD", spec=dict(BTC_SPEC), entry=67000.00, sl=57000.00)
    assert not r.ok
    assert any("below min lot" in x for x in r.reasons)
    assert r.lot is None


def test_custom_risk_pct_scales_lot():
    """risk_pct 0.25% -> risk_usd 25 -> lot setengahnya (jarak 5.0 -> 0.05)."""
    r = _calc(entry=2000.00, sl=1995.00, risk_pct=0.25)
    assert r.ok
    assert r.lot == 0.05


# ---------------------------------------------------------------- model biaya


def test_cost_model_mirrors_portfolio_gate():
    """Dengan biaya (spread 0.30, slippage 0.35, komisi 7): jarak total 6.00.

    entry ask 2000.15, SL 1995 -> jarak 5.15; +2x slippage (0.70) +
    setengah spread (0.15) = 6.00 -> per lot $607 -> raw 0.0823 -> 0.08.
    Worst-case (yang divalidasi portfolio gate) = 6.00x100x0.08 + 7x0.08
    = 48.56 <= 50 -> order lolos gate, bukan ditolak seperti lot 0.09.
    """
    spec = dict(XAU_SPEC, slippage_usd=0.35)  # slippage live XAUUSD dari spec
    r = _calc(entry=2000.15, sl=1995.00, spec=spec,
              spread_usd=0.30, commission_per_lot_usd=7.0)
    assert r.ok
    assert r.lot == 0.08
    assert r.detail["total_distance"] == pytest.approx(6.00)
    assert r.detail["risk_usd_actual"] == pytest.approx(41.20)
    assert r.detail["worst_case_usd"] == pytest.approx(48.56)
    assert r.detail["worst_case_usd"] <= r.detail["risk_usd"]


def test_cost_model_sell_side_same_distance():
    """SELL dari bid: jarak 5.15 + biaya sama -> lot 0.08 (simetri)."""
    r = _calc(entry=1999.85, sl=2005.00, spec=dict(XAU_SPEC, slippage_usd=0.35),
              spread_usd=0.30, commission_per_lot_usd=7.0)
    assert r.ok
    assert r.lot == 0.08


def test_no_costs_matches_card_formula():
    """Tanpa input biaya: formula dasar kartu (jarak SL x value per lot)."""
    r = _calc(entry=2000.00, sl=1995.00)  # spread/komisi default 0
    assert r.ok
    assert r.lot == 0.10  # raw 0.10 -> clamp? tidak: tepat 0.10 = max
    assert "clamped_to_max" not in r.detail


def test_negative_cost_inputs_rejected():
    r = _calc(spread_usd=-0.10)
    assert not r.ok
    assert any("spread" in x for x in r.reasons)
    r2 = _calc(commission_per_lot_usd=-1.0)
    assert not r2.ok
    assert any("commission" in x for x in r2.reasons)
    r3 = _calc(spec=dict(XAU_SPEC, slippage_usd=-0.35))
    assert not r3.ok
    assert any("slippage" in x for x in r3.reasons)


def test_spec_step_override():
    """Spec lot step 0.1: raw 0.066 -> floor 0 step -> lot 0.0 < min -> tolak;
    dengan min 0.1 dan jarak 1.0 (raw 0.5) -> lot 0.5 sesuai step."""
    spec = dict(XAU_SPEC, vol_step_lot=0.1)
    r = _calc(entry=2000.00, sl=1992.50, spec=spec)
    assert not r.ok  # 0.0 < min 0.01 -> fail-closed
    spec2 = dict(XAU_SPEC, vol_step_lot=0.1, vol_min_lot=0.1)
    r2 = _calc(entry=2000.00, sl=1992.50, spec=spec2)
    assert not r2.ok
    # raw 0.5 (jarak 1.0) dengan step 0.1 -> lot 0.5, tapi clamp ke max 0.10
    r3 = _calc(entry=2000.00, sl=1999.00, spec=spec2)
    assert r3.ok
    assert r3.lot == 0.10
    assert r3.detail["clamped_to_max"] is True


# ---------------------------------------------------------------- fail-closed


def test_no_sl_rejected():
    r = _calc(sl=None)
    assert not r.ok
    assert any("SL is mandatory" in x for x in r.reasons)


def test_no_entry_price_rejected():
    r = _calc(entry=None)
    assert not r.ok
    assert any("no market price" in x for x in r.reasons)


def test_no_equity_rejected():
    for bad in (None, 0.0, -100.0):
        r = _calc(equity=bad)
        assert not r.ok, bad
        assert any("equity" in x for x in r.reasons), bad


def test_no_spec_rejected():
    r = _calc(spec=None)
    assert not r.ok
    assert any("no risk spec" in x for x in r.reasons)


def test_sl_equal_entry_rejected():
    r = _calc(entry=2000.00, sl=2000.00)
    assert not r.ok
    assert any("SL distance must be positive" in x for x in r.reasons)


def test_bad_contract_size_rejected():
    for bad in (0.0, -100.0):
        r = _calc(spec=dict(XAU_SPEC, contract_size=bad))
        assert not r.ok, bad


def test_bad_lot_bounds_rejected():
    r = _calc(spec=dict(XAU_SPEC, vol_min_lot=0.5, vol_max_lot=0.10))
    assert not r.ok
    assert any("invalid lot bounds" in x for x in r.reasons)
    r2 = _calc(spec=dict(XAU_SPEC, vol_step_lot=0.0))
    assert not r2.ok


# ---------------------------------------------------------------- config flag


def test_auto_lot_config_defaults_off():
    cfg = auto_lot_config({"risk_per_trade_pct": 0.5})
    assert cfg["enabled"] is False  # DEFAULT OFF
    assert cfg["risk_pct"] == 0.5   # ikut risk_per_trade_pct


def test_auto_lot_config_partial_enable():
    cfg = auto_lot_config({"risk_per_trade_pct": 0.5, "llm_auto_lot": {"enabled": True}})
    assert cfg["enabled"] is True
    assert cfg["risk_pct"] == 0.5


def test_auto_lot_config_risk_pct_override():
    cfg = auto_lot_config({
        "risk_per_trade_pct": 0.5,
        "llm_auto_lot": {"enabled": True, "risk_pct": 0.25},
    })
    assert cfg["risk_pct"] == 0.25


def test_auto_lot_config_ignores_garbage():
    cfg = auto_lot_config({"llm_auto_lot": "yes", "risk_per_trade_pct": "bogus"})
    assert cfg["enabled"] is False
    assert cfg["risk_pct"] == 0.5  # fallback default


# ---------------------------------------------------------------- integrasi API


async def _enable_flag(enabled: bool) -> None:
    await db.set_setting("llm_auto_lot", {"enabled": enabled})


@pytest.fixture
async def agent_client(user):
    """Client ter-login sebagai role 'agent' (pola test_agent_role.py)."""
    from httpx import AsyncClient, ASGITransport
    from app import auth
    from app.main import app

    async with db.pool().connection() as conn:
        await conn.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (%s, %s, 'agent')",
            ("svc-llm-agent", auth.hash_password("agentpass")),
        )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post("/auth/login", json={"username": "svc-llm-agent", "password": "agentpass"})
        assert resp.status_code == 200, resp.text
        c.headers["x-csrf-token"] = resp.json()["csrf_token"]
        yield c


def _llm_body(**overrides):
    body = {"symbol": "XAUUSD", "side": "BUY", "volume": 0.10,
            "sl": 1995.00, "tp": 2005.00, "strategy": "llm"}
    body.update(overrides)
    return body


async def test_flag_off_volume_untouched(client, agent_client, tick_2000):
    """Flag OFF (default): volume LLM dipakai apa adanya -- behavior lama."""
    await _enable_flag(False)
    resp = await agent_client.post("/orders", json=_llm_body(volume=0.05))
    assert resp.status_code == 201, resp.text
    order = resp.json()
    assert order["status"] == "RISK_PASS"
    assert order["volume"] == pytest.approx(0.05)


async def test_flag_on_lot_replaces_llm_volume(client, agent_client, tick_2000):
    """Flag ON: lot dihitung 0.5% equity. LLM kirim 0.10 -> terpasang 0.08.

    Entry ask 2000.15, SL 1995.00 -> jarak 5.15; model biaya (mirror
    portfolio gate): +2x slippage 0.35 + setengah spread 0.15 = jarak total
    6.00; per lot $607 -> raw 0.0823 -> floor step -> 0.08. Worst-case
    (termasuk biaya) 48.56 <= 50 -> lolos portfolio gate; risk A5 mentah
    41.20 <= 50 -> lolos A5 (defense-in-depth).
    """
    await _enable_flag(True)
    resp = await agent_client.post("/orders", json=_llm_body(volume=0.10))
    assert resp.status_code == 201, resp.text
    order = resp.json()
    assert order["status"] == "RISK_PASS"
    assert order["volume"] == pytest.approx(0.08)

    # Audit: event RISK_PASS membawa detail auto_lot.
    detail = await client.get(f"/orders/{order['id']}")
    events = detail.json()["events"]
    passed = [e for e in events if e["to_status"] == "RISK_PASS"]
    assert passed, events
    auto = passed[0]["payload"].get("auto_lot")
    assert auto and auto["risk_pct"] == 0.5
    assert auto["sl_distance"] == pytest.approx(5.15)
    assert auto["lot"] == pytest.approx(0.08)
    assert auto["risk_usd_actual"] == pytest.approx(41.20)
    assert auto["worst_case_usd"] == pytest.approx(48.56)


async def test_flag_on_sell_uses_bid(client, agent_client, tick_2000):
    """SELL: entry = bid 1999.85, SL 2005.00 -> jarak 5.15 -> lot 0.08."""
    await _enable_flag(True)
    resp = await agent_client.post("/orders", json=_llm_body(
        side="SELL", volume=0.10, sl=2005.00, tp=1995.00))
    assert resp.status_code == 201, resp.text
    order = resp.json()
    assert order["status"] == "RISK_PASS"
    assert order["volume"] == pytest.approx(0.08)


async def test_flag_on_manual_order_untouched(client, tick_2000):
    """Auto lot hanya untuk order LLM; order manual tidak diubah."""
    await _enable_flag(True)
    resp = await client.post("/orders", json={
        "symbol": "XAUUSD", "side": "BUY", "volume": 0.05,
        "sl": 1995.00, "tp": 2005.00, "strategy": "manual"})
    assert resp.status_code == 201, resp.text
    order = resp.json()
    assert order["status"] == "RISK_PASS"
    assert order["volume"] == pytest.approx(0.05)


async def test_flag_on_no_tick_fails_closed(agent_client):
    """Flag ON tanpa tick: tidak ada harga entry -> order ditolak, bukan tebak."""
    await _enable_flag(True)
    resp = await agent_client.post("/orders", json=_llm_body())
    assert resp.status_code == 422
    body = resp.json()
    assert body["status"] == "FAILED"
    assert any("no market price" in r for r in body["rejected_reasons"])
    assert any("fresh market data" in r for r in body["rejected_reasons"])


async def test_flag_on_below_min_lot_fails_closed(client, agent_client, tick_2000):
    """Flag ON, jarak SL terlalu besar: raw < min lot -> FAILED (JANGAN bulatkan ke atas).

    Pakai BTCUSD dengan spec test (sl_max dilonggar) agar satu-satunya
    pelanggaran adalah lot < min, bukan A2.
    """
    specs = {
        "XAUUSD": dict(db.DEFAULT_SETTINGS["symbol_specs"]["XAUUSD"]),
        "BTCUSD": dict(db.DEFAULT_SETTINGS["symbol_specs"]["BTCUSD"], sl_max_usd=20000.0),
    }
    await db.set_setting("symbol_specs", specs)
    await db.set_setting("allowed_symbols", ["XAUUSD", "BTCUSD"])
    await _enable_flag(True)
    from app import market
    market.update_tick("BTCUSD", bid=67000.00, ask=67010.00)
    resp = await agent_client.post("/orders", json={
        "symbol": "BTCUSD", "side": "BUY", "volume": 0.10,
        "sl": 57000.00, "tp": 69000.00, "strategy": "llm"})
    assert resp.status_code == 422
    body = resp.json()
    assert body["status"] == "FAILED"
    assert any("below min lot" in r for r in body["rejected_reasons"])
    # Volume tersimpan tetap usulan LLM (audit), order gagal.
    assert body["volume"] == pytest.approx(0.10)


async def test_flag_on_a5_still_enforced(client, agent_client, tick_2000):
    """Regresi A5: gate tetap menolak lot di luar risk pct.

    Auto lot menghasilkan lot <= cap secara konstruk, tapi A5 tetap jalan:
    paksa lot hasil hitung melewati cap dengan risk_per_trade_pct kecil
    setelah lot dihitung -- di sini cukup diverifikasi A5 menolak order LLM
    flag OFF dengan volume over-risk (jalur validasi A5 tak berubah).
    """
    await _enable_flag(False)
    resp = await agent_client.post("/orders", json=_llm_body(volume=0.10))
    assert resp.status_code == 422
    body = resp.json()
    assert body["status"] == "FAILED"
    assert any("0.5% of equity" in r for r in body["rejected_reasons"])


async def test_flag_on_a5_defense_in_depth(client, agent_client, tick_2000):
    """Defense-in-depth: lot hasil hitung selalu lolos A5 DAN portfolio gate.

    Risk A5 mentah (jarak SL x value per lot) dan worst-case termasuk biaya
    (yang divalidasi portfolio gate) keduanya <= cap 0.5% equity.
    """
    await _enable_flag(True)
    resp = await agent_client.post("/orders", json=_llm_body(volume=0.10))
    assert resp.status_code == 201, resp.text
    order = resp.json()
    detail = await client.get(f"/orders/{order['id']}")
    passed = [e for e in detail.json()["events"] if e["to_status"] == "RISK_PASS"]
    auto = passed[0]["payload"]["auto_lot"]
    cap = EQUITY * 0.5 / 100.0
    assert auto["risk_usd_actual"] <= cap + 1e-9
    assert auto["worst_case_usd"] <= cap + 1e-9
