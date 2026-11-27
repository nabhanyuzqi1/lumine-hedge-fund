"""Portfolio Risk Manager tests (PRD v2.2 §7, t_f2v22a3).

DoD kartu:
- fixture contract spec benar;
- beberapa posisi + pending order bersamaan;
- race dua sinyal simultan (API, advisory lock);
- equity/margin hilang / stale;
- SL tidak terpasang / ditolak broker;
- tidak ada order lolos saat total risk melewati limit.
"""
from __future__ import annotations

import asyncio

import pytest

from app.portfolio_risk import (
    PortfolioFeed,
    PortfolioLeg,
    evaluate,
    leg_worst_case_loss,
    portfolio_config,
    portfolio_spec,
)

# Fixture contract spec BENAR (DoD): XAUUSD terverifikasi.
XAU_SPEC = {
    "contract_size": 100.0,
    "tick_value": 1.00,      # USD per tick 0.01 per lot
    "tick_size": 0.01,
    "spec_verified": True,
    "slippage_usd": 0.35,
    "sl_min_usd": 0.50,
    "sl_max_usd": 15.00,
    "vol_max_lot": 0.10,
    "spread_abs_max_usd": 0.50,
}

SETTINGS = {
    "allowed_symbols": ["XAUUSD"],
    "symbol_specs": {"XAUUSD": XAU_SPEC},
    "exposure_max_usd": 1_000_000.0,
    # portfolio_risk: default modul (max_open 2%, stress 3%, margin 20%,
    # volume 0.30 lot, konsentrasi 1% equity).
}

MARKS = {"XAUUSD": (1999.85, 2000.15)}  # spread 0.30, mid 2000.00

FEED = PortfolioFeed(equity=10_000.0, equity_age_s=0.0)

# Kandidat standar: BUY 0.10 lot, SL 1998 dari entry 2000.15 (dist 2.15).
# Base loss = (2.15 + 0.30 spread + 0.35 slippage) × 100 × 0.10 + 7×0.10 = 28.70
CANDIDATE = {"symbol": "XAUUSD", "side": "BUY", "volume": 0.10,
             "sl": 1998.0, "price": 2000.15}


def _leg(state="OPEN", side="BUY", volume=0.10, entry=2000.0, sl: float | None = 1995.0,
         symbol="XAUUSD"):
    return PortfolioLeg(symbol=symbol, side=side, volume=volume, entry=entry,
                        sl=sl, state=state, ref="t")


# ── Contract spec (DoD 1) ────────────────────────────────────────────────────


def test_verified_spec_accepted():
    spec, err = portfolio_spec("XAUUSD", SETTINGS)
    assert err is None and spec is not None
    assert spec.value_per_price_unit == pytest.approx(100.0)


def test_candidate_with_verified_spec_passes():
    d = evaluate(CANDIDATE, [], FEED, MARKS, SETTINGS)
    assert d.ok, d.reasons


@pytest.mark.parametrize("spec", [
    None,                                    # tanpa spec sama sekali
    {**XAU_SPEC, "tick_value": None},        # tick value hilang
    {**XAU_SPEC, "spec_verified": False},    # flag verifikasi false
    {**XAU_SPEC, "spec_verified": None},
    {**XAU_SPEC, "tick_value": 0},           # tick value tidak valid
    {**XAU_SPEC, "tick_value": -1},
    {**XAU_SPEC, "tick_size": 0},
    {**XAU_SPEC, "contract_size": 0},
    {**XAU_SPEC, "tick_value": float("nan")},
])
def test_unverifiable_spec_rejected_fail_closed(spec):
    settings = {"symbol_specs": {"XAUUSD": spec} if spec is not None else {},
                "exposure_max_usd": 1_000_000.0}
    d = evaluate(CANDIDATE, [], FEED, MARKS, settings)
    assert not d.ok
    assert any("not verified" in r for r in d.reasons), d.reasons


def test_unknown_symbol_rejected():
    d = evaluate({**CANDIDATE, "symbol": "EURUSD"}, [], FEED, {}, SETTINGS)
    assert not d.ok
    assert any("not verified" in r for r in d.reasons)


# ── Perhitungan loss (fixture angka eksak) ───────────────────────────────────


def test_worst_case_loss_open_exact():
    """(5.00 + 0.30 spread + 0.35 slippage) × 100 × 1.0 + 7 komisi = 572.00."""
    cfg = portfolio_config(SETTINGS)
    spec = portfolio_spec("XAUUSD", SETTINGS)[0]
    loss = leg_worst_case_loss(_leg(volume=1.0), spec, MARKS["XAUUSD"],
                               cfg, stress=False)
    assert loss == pytest.approx(572.0, abs=1e-9)


def test_stress_loss_exact_gap_and_widened_spread():
    """Stress: gap 0.5% × 2000 = 10, spread 3×0.30 = 0.90, slippage 0.35.
    (5.00 + 10 + 0.90 + 0.35) × 100 × 1.0 + 7 = 1632.00."""
    cfg = portfolio_config(SETTINGS)
    loss = leg_worst_case_loss(_leg(volume=1.0), portfolio_spec("XAUUSD", SETTINGS)[0],
                               MARKS["XAUUSD"], cfg, stress=True)
    assert loss == pytest.approx(1632.0, abs=1e-9)


def test_pending_order_worst_fill_includes_slippage():
    """Pending BUY: fill terburuk = 2000 + 0.35 -> dist ke SL 1995 = 5.35.
    (5.35 + 0.65) × 100 × 1.0 + 7 = 607.00."""
    cfg = portfolio_config(SETTINGS)
    loss = leg_worst_case_loss(_leg(state="PENDING", volume=1.0),
                               portfolio_spec("XAUUSD", SETTINGS)[0],
                               MARKS["XAUUSD"], cfg, stress=False)
    assert loss == pytest.approx(607.0, abs=1e-9)


def test_stress_loss_always_ge_base():
    cfg = portfolio_config(SETTINGS)
    spec = portfolio_spec("XAUUSD", SETTINGS)[0]
    for state in ("OPEN", "PENDING", "SENT"):
        leg = _leg(state=state, volume=1.0)
        base = leg_worst_case_loss(leg, spec, MARKS["XAUUSD"], cfg, stress=False)
        stress = leg_worst_case_loss(leg, spec, MARKS["XAUUSD"], cfg, stress=True)
        assert stress >= base, state


# ── Agregat posisi + pending + SENT (DoD 2) ──────────────────────────────────


def test_aggregate_counts_positions_pending_sent():
    # Pending/SENT entry 1999.65 -> fill terburuk 2000.00 -> dist SL = 5.00,
    # loss per 0.02 lot = (5.65 × 100 × 0.02) + 0.14 = 11.44 (sama semua state).
    # Kandidat 0.02 lot: fill terburuk BUY = 2000.15+0.35 -> dist 2.50 ->
    # (3.15 × 100 × 0.02) + 0.14 = 6.44.
    legs = [
        _leg(state="OPEN", volume=0.02),
        _leg(state="OPEN", volume=0.02),
        _leg(state="PENDING", volume=0.02, entry=1999.65),
        _leg(state="SENT", volume=0.02, entry=1999.65),
    ]
    candidate = {**CANDIDATE, "volume": 0.02}
    d = evaluate(candidate, legs, FEED, MARKS, SETTINGS)
    assert d.ok, d.reasons
    s = d.snapshot
    assert s.open_positions == 2
    assert s.pending_orders == 1
    assert s.sent_orders == 1
    assert s.total_volume_lot == pytest.approx(0.10)
    assert s.open_risk_usd == pytest.approx(4 * 11.44 + 6.44, abs=1e-6)


def test_open_risk_over_limit_rejected():
    """DoD 6: tidak ada order lolos saat total risk melewati limit."""
    legs = [_leg(state="OPEN", volume=0.10) for _ in range(3)]  # 3 × 57.2 = 171.6
    d = evaluate(CANDIDATE, legs, FEED, MARKS, SETTINGS)  # +28.7 = 200.3 > cap 200
    assert not d.ok
    assert any("total open risk" in r for r in d.reasons), d.reasons


def test_open_risk_just_under_limit_passes():
    """Boundary aman: total sedikit di bawah cap harus LOLOS."""
    legs = [_leg(state="OPEN", volume=0.05), _leg(state="OPEN", volume=0.05)]
    # 2×28.6 + kandidat 0.05 lot 16.1 = 73.3 < cap 0.734% × 10.000 = 73.4.
    settings = {**SETTINGS, "portfolio_risk": {"max_open_risk_pct": 0.734}}
    d = evaluate({**CANDIDATE, "volume": 0.05}, legs, FEED, MARKS, settings)
    assert d.ok, d.reasons


def test_candidate_with_missing_sl_rejected():
    d = evaluate({**CANDIDATE, "sl": None}, [], FEED, MARKS, SETTINGS)
    assert not d.ok
    assert any("candidate SL missing" in r for r in d.reasons)


def test_candidate_missing_price_uses_mark_mid():
    d = evaluate({"symbol": "XAUUSD", "side": "BUY", "volume": 0.10, "sl": 1998.0},
                 [], FEED, MARKS, SETTINGS)
    assert d.ok, d.reasons  # entry fallback = mid 2000.00, dist 2.00


# ── SL ditolak / tidak terpasang di posisi (DoD 5) ───────────────────────────


def test_open_position_without_sl_blocks_new_orders():
    """Posisi yang SL-nya ditolak broker = loss tak terbatas -> order baru
    diblokir sampai posisi diselesaikan owner (PRD §7.3)."""
    legs = [_leg(state="OPEN", volume=0.10, sl=None)]
    d = evaluate(CANDIDATE, legs, FEED, MARKS, SETTINGS)
    assert not d.ok
    assert any("without SL" in r for r in d.reasons), d.reasons
    assert d.snapshot.unbounded_sl == 1


def test_pending_without_sl_blocks_new_orders():
    d = evaluate(CANDIDATE, [_leg(state="SENT", sl=None)], FEED, MARKS, SETTINGS)
    assert not d.ok
    assert any("without SL" in r for r in d.reasons)


# ── Equity / margin feed (DoD 4) ─────────────────────────────────────────────


def test_equity_missing_blocks_new_orders():
    feed = PortfolioFeed(equity=None, equity_age_s=None)
    d = evaluate(CANDIDATE, [], feed, MARKS, SETTINGS)
    assert not d.ok
    assert any("equity feed missing" in r for r in d.reasons)


def test_equity_stale_blocks_new_orders():
    feed = PortfolioFeed(equity=10_000.0, equity_age_s=120.0)  # > 60s
    d = evaluate(CANDIDATE, [], feed, MARKS, SETTINGS)
    assert not d.ok
    assert any("equity feed stale" in r for r in d.reasons)


def test_equity_age_unknown_blocks_new_orders():
    feed = PortfolioFeed(equity=10_000.0, equity_age_s=None)
    d = evaluate(CANDIDATE, [], feed, MARKS, SETTINGS)
    assert not d.ok
    assert any("equity feed age unknown" in r for r in d.reasons)


def test_margin_feed_stale_blocks_new_orders():
    feed = PortfolioFeed(equity=10_000.0, equity_age_s=0.0,
                         margin_used=100.0, margin_age_s=999.0)
    d = evaluate(CANDIDATE, [], feed, MARKS, SETTINGS)
    assert not d.ok
    assert any("margin feed stale" in r for r in d.reasons)


def test_margin_feed_missing_is_computed_not_blocking():
    """Feed margin broker absen -> margin dihitung dari notional (bukan blokir),
    kecuali hasilnya melewati batas margin utilization."""
    feed = PortfolioFeed(equity=10_000.0, equity_age_s=0.0, margin_used=None)
    d = evaluate(CANDIDATE, [], feed, MARKS, SETTINGS)
    assert d.ok, d.reasons
    # Notional kandidat = 0.10 × 100 × 2000.15 = 20001.5 -> margin 200.0 (2%).
    assert d.snapshot.margin_used_usd == pytest.approx(200.0, abs=0.1)
    assert d.snapshot.margin_utilization_pct == pytest.approx(2.0, abs=0.01)


# ── Stress scenario ──────────────────────────────────────────────────────────


def test_stress_scenario_blocks_when_stress_risk_over_limit():
    """Gap + spread melebar + beberapa SL bersamaan: loss stress melewati
    cap stress -> order ditolak walau base risk masih aman."""
    legs = [_leg(state="OPEN", volume=0.10) for _ in range(4)]
    # base 4×57.2 + 28.7 = 257.5 < 200? Tidak: > 200. Pakai 2 leg.
    legs = legs[:2]
    # base 142.9 < 200 aman; stress 2×134.75 + kandidat 134.75... hitung:
    # stress per leg 0.10 lot = (5+10+0.9+0.35)×10+0.7 = 169.2; total 3×169.2
    # = 507.6 > cap stress 3% = 300 -> ditolak.
    d = evaluate(CANDIDATE, legs, FEED, MARKS, SETTINGS)
    assert not d.ok
    assert any("stress loss" in r for r in d.reasons), d.reasons


def test_stress_within_limit_passes():
    legs = [_leg(state="OPEN", volume=0.10)]
    # stress 2×169.2 = 338.4 > 300? per leg 0.10 lot = 169.2, total 2 = 338.4.
    # Cap stress default 3% = 300 -> pakai 1 leg + kandidat = 338.4 tetap >.
    # Turunkan volume leg: 0.05 lot -> 85.28; total 170.6 < 300 -> ok.
    legs = [_leg(state="OPEN", volume=0.05)]
    d = evaluate(CANDIDATE, legs, FEED, MARKS, SETTINGS)
    assert d.ok, d.reasons
    assert d.snapshot.stress_risk_usd < 300.0


# ── Limit lainnya ────────────────────────────────────────────────────────────


def test_concentration_per_symbol_rejected():
    """Konsentrasi: worst-case loss satu simbol > 1% equity -> tolak."""
    legs = [_leg(state="OPEN", volume=0.10), _leg(state="OPEN", volume=0.10)]
    # per simbol 114.4 + 28.7 = 143.1 > cap 100 -> ditolak.
    d = evaluate(CANDIDATE, legs, FEED, MARKS, SETTINGS)
    assert not d.ok
    assert any("concentration" in r for r in d.reasons), d.reasons


def test_margin_utilization_cap_rejected():
    settings = {**SETTINGS, "portfolio_risk": {"max_margin_utilization_pct": 1.0}}
    d = evaluate(CANDIDATE, [], FEED, MARKS, settings)
    assert not d.ok
    assert any("margin used" in r for r in d.reasons), d.reasons


def test_total_volume_cap_rejected():
    """PRD §7.4: total volume maksimum 0.30 lot (0.15 + 0.10 + 0.10 = 0.35)."""
    legs = [_leg(state="OPEN", volume=0.15), _leg(state="PENDING", volume=0.10)]
    d = evaluate(CANDIDATE, legs, FEED, MARKS, SETTINGS)
    assert not d.ok
    assert any("total volume" in r for r in d.reasons), d.reasons


def test_gross_exposure_cap_rejected():
    # Notional = lot × contract_size × harga: kandidat 0.10×100×2000 = 20.000
    # + posisi 20.000 = 40.000. Stress 163.2+138.2 = 301.4 -> cap stress
    # dinaikkan agar hanya gross exposure yang diuji.
    settings = {**SETTINGS, "exposure_max_usd": 45_000.0,
                "portfolio_risk": {"stress_max_risk_pct": 3.5}}
    d = evaluate(CANDIDATE, [_leg(state="OPEN", volume=0.10)], FEED, MARKS, settings)
    assert d.ok, d.reasons  # 40.000 < 45.000
    settings = {**SETTINGS, "exposure_max_usd": 39_000.0,
                "portfolio_risk": {"stress_max_risk_pct": 3.5}}
    d = evaluate(CANDIDATE, [_leg(state="OPEN", volume=0.10)], FEED, MARKS, settings)
    assert not d.ok
    assert any("gross exposure" in r for r in d.reasons), d.reasons


def test_no_hedging_credit_buy_and_sell_both_counted():
    """PRD §7.3: jangan asumsikan dua posisi saling meng-hedge. BUY + SELL
    simbol sama tetap dihitung keduanya (gross, tanpa netting)."""
    legs = [_leg(state="OPEN", volume=0.10, side="BUY"),
            _leg(state="OPEN", volume=0.10, side="SELL")]
    d = evaluate({**CANDIDATE, "side": "SELL", "sl": 2002.0, "price": 1999.85},
                 legs, FEED, MARKS, SETTINGS)
    assert d.snapshot.total_volume_lot == pytest.approx(0.30)
    # SELL: fill terburuk = 1999.85-0.35 = 1999.50, SL 2002.0 -> dist 2.50
    # (lebih buruk dari 2.15) -> loss 32.2; total 2×57.2 + 32.2.
    assert d.snapshot.open_risk_usd == pytest.approx(2 * 57.2 + 32.2, abs=1e-6)


def test_candidate_non_numeric_volume_rejected():
    d = evaluate({**CANDIDATE, "volume": "abc"}, [], FEED, MARKS, SETTINGS)
    assert not d.ok
    assert any("volume" in r for r in d.reasons)


def test_disable_flag_skips_portfolio_gate():
    """Kill-switch konfigurasi: enabled=false menonaktifkan lapisan portofolio
    (dipakai caller, bukan di evaluate; diuji via config merge saja)."""
    settings = {**SETTINGS, "portfolio_risk": {"enabled": False}}
    cfg = portfolio_config(settings)
    assert cfg["enabled"] is False


def test_owner_override_merges_partial():
    settings = {**SETTINGS, "portfolio_risk": {"max_open_risk_pct": 5.0}}
    cfg = portfolio_config(settings)
    assert cfg["max_open_risk_pct"] == 5.0
    assert cfg["stress"]["gap_pct"] == 0.5  # default stress tetap
    settings = {**SETTINGS,
                "portfolio_risk": {"stress": {"gap_pct": 1.0}}}
    cfg = portfolio_config(settings)
    assert cfg["stress"]["gap_pct"] == 1.0
    assert cfg["stress"]["spread_multiplier"] == 3.0


# ── Jalur API /orders (DB) ───────────────────────────────────────────────────

from app import db  # noqa: E402


@pytest.fixture(autouse=True)
async def _reset_portfolio_settings():
    """settings tidak di-TRUNCATE antar test -> reset portfolio_risk agar
    override uji (mis. max_open_risk_pct 0.1) tidak bocor ke test berikutnya."""
    yield
    await db.set_setting("portfolio_risk", None)


async def _csrf(client) -> str:
    return (await client.get("/auth/me")).json()["csrf_token"]


def _body(**overrides):
    body = {"symbol": "XAUUSD", "side": "BUY", "volume": 0.1, "sl": 1998.0, "tp": 2005.0}
    body.update(overrides)
    return body


async def test_order_rejected_when_portfolio_risk_over_limit(client, tick_2000):
    """DoD 6 di jalur API: total risk lewat limit -> FAILED + snapshot audit."""
    await db.set_setting("portfolio_risk", {"max_open_risk_pct": 0.1})  # cap $10
    resp = await client.post("/orders", json=_body(),
                             headers={"x-csrf-token": await _csrf(client)})
    assert resp.status_code == 422, resp.text
    order = resp.json()
    assert order["status"] == "FAILED"
    assert any("total open risk" in r for r in order["rejected_reasons"])
    # Snapshot portofolio ter-audit di order_events (PRD §3.1 #10).
    async with db.pool().connection() as conn:
        row = await conn.execute(
            "SELECT payload FROM order_events WHERE order_id = %s "
            "AND to_status = 'FAILED' ORDER BY id DESC LIMIT 1", (order["id"],))
        ev = (await row.fetchone())["payload"]
    assert ev["risk"] == "rejected"
    assert ev["portfolio"]["open_risk_usd"] > 10.0
    assert "limits" in ev["portfolio"]


async def test_order_passes_within_portfolio_limits(client, tick_2000):
    """Default limits: satu order 0.10 lot masih lolos semua lapisan."""
    resp = await client.post("/orders", json=_body(),
                             headers={"x-csrf-token": await _csrf(client)})
    assert resp.status_code == 201, resp.text
    assert resp.json()["status"] == "RISK_PASS"
    async with db.pool().connection() as conn:
        row = await conn.execute(
            "SELECT payload FROM order_events WHERE order_id = %s "
            "AND to_status = 'RISK_PASS' ORDER BY id DESC LIMIT 1", (resp.json()["id"],))
        ev = (await row.fetchone())["payload"]
    assert ev["risk"] == "pass"
    assert ev["portfolio"]["unbounded_sl"] == 0


async def test_race_two_simultaneous_signals(client, tick_2000):
    """DoD 3: dua sinyal simultan -> advisory lock menyerialisasi evaluasi.

    Cap total open risk 0.35% ($35); order masing-masing $28.70. Tanpa lock,
    kedua request membaca portofolio kosong dan dua-duanya lolos
    (oversubscription $57.4 > $35). Dengan lock: tepat satu yang lolos.
    """
    await db.set_setting("portfolio_risk", {"max_open_risk_pct": 0.35})
    csrf = await _csrf(client)
    r1 = client.post("/orders", json=_body(), headers={"x-csrf-token": csrf})
    r2 = client.post("/orders", json=_body(), headers={"x-csrf-token": csrf})
    resp1, resp2 = await asyncio.gather(r1, r2)
    o1, o2 = resp1.json(), resp2.json()
    statuses = sorted([o1["status"], o2["status"]])
    assert statuses == ["FAILED", "RISK_PASS"], (o1, o2)
    failed = o1 if o1["status"] == "FAILED" else o2
    assert any("total open risk" in r for r in failed["rejected_reasons"]), failed
    # Tidak ada order lain yang lolos di luar kapasitas risk.
    async with db.pool().connection() as conn:
        row = await conn.execute(
            "SELECT COUNT(*) AS n FROM orders WHERE status = 'RISK_PASS'")
        assert (await row.fetchone())["n"] == 1


async def test_risk_portfolio_endpoint(client, tick_2000):
    """GET /risk/portfolio: snapshot agregat + breaches untuk UI/monitoring."""
    async with db.pool().connection() as conn:
        await conn.execute(
            "INSERT INTO positions (ticket, symbol, side, volume, open_price, sl, status) "
            "VALUES (9001, 'XAUUSD', 'BUY', 0.10, 2000.00, 1995.00, 'OPEN')")
    resp = await client.get("/risk/portfolio")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["open_positions"] == 1
    assert data["open_risk_usd"] == pytest.approx(57.2, abs=0.2)
    assert data["stress_risk_usd"] > data["open_risk_usd"]
    assert data["gross_exposure_usd"] == pytest.approx(20000.0, abs=1.0)
    assert data["total_volume_lot"] == pytest.approx(0.10)
    assert data["per_symbol"]["XAUUSD"]["risk_usd"] == pytest.approx(57.2, abs=0.2)
    assert data["breaches"] == []
    assert data["limits"]["max_open_risk_pct"] == 2.0


async def test_risk_portfolio_endpoint_flags_unbounded_sl(client, tick_2000):
    """Posisi tanpa SL (ditolak broker) muncul sebagai breach unbounded_sl."""
    async with db.pool().connection() as conn:
        await conn.execute(
            "INSERT INTO positions (ticket, symbol, side, volume, open_price, sl, status) "
            "VALUES (9002, 'XAUUSD', 'BUY', 0.10, 2000.00, NULL, 'OPEN')")
    resp = await client.get("/risk/portfolio")
    assert resp.status_code == 200
    data = resp.json()
    assert data["unbounded_sl"] == 1
    assert "unbounded_sl" in data["breaches"]


# ── STUCK grace period (insiden 25 Nov 2026) ─────────────────────────────────


async def _insert_stuck_order(age_s: int, sl: float | None = None) -> str:
    """Order STUCK (tanpa hasil EA) berumur `age_s` detik sejak jadi STUCK."""
    from app import db

    async with db.pool().connection() as conn:
        async with conn.transaction():
            cur = await conn.execute(
                """
                INSERT INTO orders (symbol, side, volume, sl, tp, status,
                                    price_requested, action, sent_at)
                VALUES ('XAUUSD', 'BUY', 0.10, %s, NULL, 'STUCK', 2000.0, 'OPEN', now())
                RETURNING id
                """,
                (sl,),
            )
            order_id = (await cur.fetchone())["id"]
            await conn.execute(
                "UPDATE orders SET updated_at = now() - (%s * interval '1 second') "
                "WHERE id = %s",
                (age_s, order_id),
            )
            return str(order_id)


async def test_collect_legs_excludes_expired_stuck_orders():
    """STUCK > grace period bukan leg pending lagi; STUCK segar tetap dihitung."""
    from app.portfolio_risk import collect_legs

    expired = await _insert_stuck_order(age_s=1000, sl=None)
    fresh = await _insert_stuck_order(age_s=60, sl=None)

    async with db.pool().connection() as conn:
        legs = await collect_legs(conn, SETTINGS)

    refs = {leg.ref for leg in legs}
    assert fresh in refs
    assert expired not in refs
    stuck_legs = [leg for leg in legs if leg.state == "STUCK"]
    assert len(stuck_legs) == 1


async def test_expired_stuck_order_does_not_block_new_orders(client, tick_2000):
    """Regresi insiden 25 Nov: STUCK lama tanpa SL tidak memblokir order baru.

    Dulu: STUCK dihitung leg pending tanpa SL -> gate fail-closed permanen
    ("open leg(s) without SL") -> agent LLM kena breaker 3 FAILED beruntun.
    """
    await _insert_stuck_order(age_s=1000, sl=None)

    resp = await client.post("/orders", json=_body(),
                             headers={"x-csrf-token": await _csrf(client)})
    assert resp.status_code == 201, resp.text
    assert resp.json()["status"] == "RISK_PASS"


async def test_fresh_stuck_order_still_blocks_new_orders(client, tick_2000):
    """STUCK segar (belum lewat grace period) tetap dihitung: leg tanpa SL blokir."""
    await _insert_stuck_order(age_s=60, sl=None)

    resp = await client.post("/orders", json=_body(),
                             headers={"x-csrf-token": await _csrf(client)})
    assert resp.status_code == 422, resp.text
    assert any("without SL" in r for r in resp.json()["rejected_reasons"])
