"""Property-based tests (PRD 22.1.3): risk calculation & state transitions.

Dua kelompok:
1. Risk gate (pure function, tanpa DB) -> hypothesis @given. Properti yang
   dicek adalah INVARIAN gate, bukan replay kasus unit test yang sudah ada
   di test_risk.py: boundary monotone (volume/spread/drawdown/exposure/A5),
   orientasi SL/TP per side, mode-aware kill-switch, fail-closed spec, dan
   kemurnian fungsi (input sama -> keputusan sama).
2. State transition (DB) -> matrix EKSHAUSTIF semua pasangan (from, to)
   terhadap ALLOWED_TRANSITIONS + properti invarian tabel transisi.
   Ekshaustif > sampling untuk tabel berhingga: coverage 100% pasangan.

Boundary mengikuti semantik gate: perbandingan pakai toleransi _EPS = 1e-9
(tepat di limit LOULUS).
"""
from __future__ import annotations

import pytest
from hypothesis import given, settings, strategies as st

from app import db
from app.risk import RiskContext, risk_gate, symbol_spec
from app.state_machine import (
    ALLOWED_TRANSITIONS,
    CLOSE_OWNER_TARGETS,
    InvalidTransition,
    TERMINAL_STATUSES,
    fetchone,
    transition,
)

EPS = 1e-9


# ------------------------------------------------------------------ helpers

def xau_spec() -> dict:
    return {
        "contract_size": 100.0,
        "sl_min_usd": 0.50,
        "sl_max_usd": 15.00,
        "vol_max_lot": 0.10,
        "spread_abs_max_usd": 0.50,
    }


def base_settings(**over) -> dict:
    s = {
        "max_volume": 1.0,
        "max_daily_drawdown": 100.0,
        "max_spread": 0.50,
        "max_orders_per_min": 10,
        "halted": False,
        "kill_switch": False,
        "allowed_symbols": ["XAUUSD"],
        "symbol_specs": {"XAUUSD": xau_spec()},
        "exposure_max_usd": 107370.0,
        "risk_per_trade_pct": 0.5,
        "daily_start_balance": 10000.0,
    }
    s.update(over)
    return s


def make_ctx(**over) -> RiskContext:
    defaults = dict(
        settings=base_settings(),
        bid=1999.85,
        ask=2000.15,
        tick_age_s=0.1,
        daily_pnl=0.0,
        orders_last_minute=0,
    )
    defaults.update(over)
    return RiskContext(**defaults, equity=None, is_llm=False, llm_orders_last_minute=0, llm_orders_today=0, llm_cooldown_remaining_s=0)


def base_order(**over) -> dict:
    o = {"symbol": "XAUUSD", "side": "BUY", "volume": 0.10,
         "sl": 1998.00, "tp": 2005.00}
    o.update(over)
    return o


def reasons_with(d: RiskContext, order: dict) -> list[str]:
    return risk_gate(order, d).reasons


# ------------------------------------------------------------- risk properties

@given(volume=st.floats(min_value=0.01, max_value=0.20, allow_nan=False))
def test_volume_boundary_monotone(volume: float):
    """Volume <= vol_max (+eps) tidak pernah menambah alasan; > vol_max selalu."""
    d = make_ctx()
    r = risk_gate(base_order(volume=volume), d)
    has_reason = any("exceeds max" in x for x in r.reasons)
    assert has_reason == (volume > 0.10 + EPS), (volume, r.reasons)
    # legacy global backstop (max_volume 1.0) tidak boleh menyala di rentang ini
    assert r.ok == (volume <= 0.10 + EPS)


@given(spread=st.floats(min_value=0.30, max_value=0.70, allow_nan=False))
def test_spread_boundary_monotone(spread: float):
    """Spread <= max (+eps) lolos filter; > max selalu ada alasan spread."""
    bid = 1999.85
    d = make_ctx(bid=bid, ask=bid + spread)
    r = risk_gate(base_order(), d)
    has_reason = any("spread" in x for x in r.reasons)
    assert has_reason == (spread > 0.50 + EPS), (spread, r.reasons)


@given(pnl=st.floats(min_value=-600.0, max_value=0.0, allow_nan=False),
       pct=st.floats(min_value=1.0, max_value=5.0, allow_nan=False))
def test_daily_drawdown_halt_boundary(pnl: float, pct: float):
    """A6 (AUDIT-A2): drawdown harian >= pct% saldo awal -> halt; di bawahnya tidak.

    Ambang HANYA dari kill_switch_triggers.daily_drawdown_pct; field USD
    max_daily_drawdown tidak berpengaruh.
    """
    s = base_settings()
    s["daily_start_balance"] = 10000.0
    s["max_daily_drawdown"] = 1.0  # sengaja sangat ketat: harus diabaikan
    s["kill_switch_triggers"] = {"daily_drawdown_pct": pct}
    d = make_ctx(settings=s, daily_pnl=pnl)
    r = risk_gate(base_order(), d)
    breached = (-pnl) / 10000.0 * 100.0 >= pct - EPS
    assert r.halt is breached, (pnl, pct, r.halt, r.reasons)
    assert any("daily drawdown" in x for x in r.reasons) == breached


@given(sl=st.floats(min_value=1995.0, max_value=1999.5, allow_nan=False))
def test_risk_per_trade_a5_boundary(sl: float):
    """A5: sl_distance*contract*volume <= cap lolos; > cap selalu ditolak."""
    d = make_ctx()
    r = risk_gate(base_order(sl=sl), d)
    distance = 2000.15 - sl
    risk_usd = distance * 100.0 * 0.10
    has_reason = any("trade risk" in x for x in r.reasons)
    assert has_reason == (risk_usd > 50.0 + EPS), (sl, risk_usd, r.reasons)


@given(cap=st.floats(min_value=15000.0, max_value=30000.0, allow_nan=False))
def test_exposure_a4_boundary(cap: float):
    """A4: open_exposure + notional order <= cap lolos; > cap selalu ditolak."""
    s = base_settings()
    s["exposure_max_usd"] = cap
    d = make_ctx(settings=s, open_exposure_usd=0.0)
    r = risk_gate(base_order(), d)
    notional = 0.10 * 100.0 * 2000.15
    has_reason = any("open exposure" in x for x in r.reasons)
    assert has_reason == (notional > cap + EPS), (cap, r.reasons)


@given(sl=st.floats(min_value=1990.0, max_value=2005.0, allow_nan=False),
       tp=st.floats(min_value=1995.0, max_value=2010.0, allow_nan=False))
def test_buy_sl_tp_ordering_invariant(sl: float, tp: float):
    """BUY: alasan orientasi muncul iff TIDAK (sl < price < tp)."""
    price = 2000.15
    d = make_ctx()
    r = risk_gate(base_order(sl=sl, tp=tp), d)
    violated = not (sl < price < tp)
    has_reason = any("BUY requires SL < price < TP" in x for x in r.reasons)
    assert has_reason == violated, (sl, tp, r.reasons)


@given(sl=st.floats(min_value=1995.0, max_value=2010.0, allow_nan=False),
       tp=st.floats(min_value=1990.0, max_value=2005.0, allow_nan=False))
def test_sell_sl_tp_ordering_invariant(sl: float, tp: float):
    """SELL: alasan orientasi muncul iff TIDAK (tp < price < sl)."""
    price = 1999.85  # bid
    d = make_ctx()
    r = risk_gate(base_order(side="SELL", sl=sl, tp=tp), d)
    violated = not (tp < price < sl)
    has_reason = any("SELL requires TP < price < SL" in x for x in r.reasons)
    assert has_reason == violated, (sl, tp, r.reasons)


KILL_SWITCH_CASES = st.tuples(
    st.sampled_from([None, "STOP_NEW_ORDERS", "STOP_AND_FLATTEN",
                     "PAUSE_STRATEGY", "GLOBAL_HALT"]),
    st.sampled_from(["manual", "london_breakout"]),
    st.sampled_from([[], ["london_breakout"], ["news_trader"]]),
    st.booleans(),  # halted
)


@given(case=KILL_SWITCH_CASES)
def test_kill_switch_mode_aware_invariant(case):
    """Invarian kill-switch mode-aware:
    - aktif non-PAUSE -> blocked
    - aktif PAUSE_STRATEGY -> blocked iff strategi order ada di daftar pause
    - tidak aktif -> tanpa alasan kill-switch (flag mirror 'halted' diabaikan;
      sumber kebenaran = state kill-switch, t_4d524475)
    """
    mode, order_strategy, paused, halted = case
    ks = ({"active": True, "mode": mode} if mode is not None else False)
    s = base_settings()
    s["kill_switch"] = ks
    s["halted"] = halted
    s["paused_strategies"] = paused
    d = make_ctx(settings=s)
    r = risk_gate(base_order(strategy=order_strategy), d)
    ks_reasons = [x for x in r.reasons if "kill-switch" in x]
    if mode is None or mode is False:
        assert ks_reasons == [], (case, r.reasons)
    elif mode == "PAUSE_STRATEGY":
        should_block = order_strategy in [p.lower() for p in paused]
        assert bool(ks_reasons) == should_block, (case, r.reasons)
    else:
        assert ks_reasons, (case, r.reasons)


@given(missing_key=st.sampled_from(
    ["contract_size", "sl_min_usd", "sl_max_usd", "vol_max_lot",
     "spread_abs_max_usd"]))
def test_symbol_spec_fail_closed(missing_key: str):
    """Spec parsial (satu key risk wajib hilang) -> None -> order ditolak."""
    spec = xau_spec()
    del spec[missing_key]
    s = base_settings()
    s["symbol_specs"] = {"XAUUSD": spec}
    assert symbol_spec("XAUUSD", s) is None
    d = make_ctx(settings=s)
    r = risk_gate(base_order(), d)
    assert not r.ok
    assert any("no risk spec" in x for x in r.reasons)


@given(volume=st.floats(min_value=0.01, max_value=0.20, allow_nan=False),
       spread=st.floats(min_value=0.30, max_value=0.70, allow_nan=False),
       pnl=st.floats(min_value=-90.0, max_value=0.0, allow_nan=False))
def test_gate_is_pure(volume: float, spread: float, pnl: float):
    """risk_gate pure: input sama -> RiskDecision identik (dipanggil 2x)."""
    bid = 1999.85
    d = make_ctx(bid=bid, ask=bid + spread, daily_pnl=pnl)
    order = base_order(volume=volume)
    a = risk_gate(order, d)
    b = risk_gate(order, d)
    assert a.ok == b.ok and a.reasons == b.reasons and a.halt == b.halt


def test_ok_iff_no_reasons():
    """Invarian bentuk: ok == (tidak ada reasons), halt hanya dari drawdown."""
    for order, d in [
        (base_order(), make_ctx()),
        (base_order(volume=5.0), make_ctx()),
        (base_order(sl=None), make_ctx()),
        (base_order(), make_ctx(daily_pnl=-500.0)),
    ]:
        r = risk_gate(order, d)
        assert r.ok == (len(r.reasons) == 0)


# --------------------------------------------- state transition properties

def test_transition_table_final_has_no_outgoing():
    """Status final tanpa keluar: FAILED, FILLED_THEN_CLOSED, ORPHAN_CLOSED,
    RECONCILED. FILLED masuk TERMINAL_STATUSES (resolved_at di-set) tapi tetap
    punya outbound refinements reconciler (PRD 5.8) - invarian dibedakan."""
    final = {"FAILED", "FILLED_THEN_CLOSED", "ORPHAN_CLOSED", "RECONCILED"}
    for status, targets in ALLOWED_TRANSITIONS.items():
        if status in final:
            assert targets == set(), status
        else:
            assert len(targets) >= 1, status
    # FILLED hanya boleh refine ke penutupan sah / FAILED
    assert ALLOWED_TRANSITIONS["FILLED"] <= {"FILLED_THEN_CLOSED", "FAILED"}


def test_transition_table_nonterminal_has_outgoing():
    for status, targets in ALLOWED_TRANSITIONS.items():
        if status not in TERMINAL_STATUSES:
            assert len(targets) >= 1, status


def test_transition_table_targets_are_known_statuses():
    all_statuses = set(ALLOWED_TRANSITIONS)
    for targets in ALLOWED_TRANSITIONS.values():
        assert targets <= all_statuses


def test_close_owner_targets_are_legal_transitions():
    for src, dst in CLOSE_OWNER_TARGETS.items():
        assert dst in ALLOWED_TRANSITIONS[src], (src, dst)


# Path menuju setiap status non-terminal (untuk setup ekshaustif).
WALK_PATHS: dict[str, list[str]] = {
    "RECEIVED": [],
    "RISK_PASS": ["RISK_PASS"],
    "SENT": ["RISK_PASS", "SENT"],
    "STUCK": ["RISK_PASS", "SENT", "STUCK"],
    "FILLED": ["RISK_PASS", "SENT", "FILLED"],
    "FILLED_THEN_CLOSED": ["RISK_PASS", "SENT", "FILLED", "FILLED_THEN_CLOSED"],
    "FAILED": ["FAILED"],
    "ORPHAN_ADOPTED": [],   # di-set langsung via SQL (orphan tidak punya inbound)
    "ORPHAN_CLOSED": [],
    "RECONCILED": ["RISK_PASS", "SENT", "STUCK", "RECONCILED"],
}

# status yang TIDAK bisa di-walk dari RECEIVED via transisi legal
DIRECT_SET = {"ORPHAN_ADOPTED", "ORPHAN_CLOSED"}


async def _insert_order_at(status: str) -> str:
    """Insert order lalu jalanikan path ke `status` (atau SET langsung utk orphan)."""
    async with db.pool().connection() as conn:
        async with conn.transaction():
            row = await fetchone(
                conn,
                """
                INSERT INTO orders (symbol, side, volume, sl, tp, status)
                VALUES ('XAUUSD', 'BUY', 0.10, 1998, 2005, 'RECEIVED') RETURNING id
                """,
            )
            oid = row["id"]
            await conn.execute(
                "INSERT INTO order_events (order_id, from_status, to_status) "
                "VALUES (%s, NULL, 'RECEIVED')", (oid,))
            if status in DIRECT_SET:
                # orphan tidak punya inbound dari RECEIVED; set langsung (setup only)
                await conn.execute(
                    "UPDATE orders SET status = %s WHERE id = %s", (status, oid))
            else:
                for step in WALK_PATHS[status]:
                    # Constraint orders_failed_requires_reason: setiap FAILED
                    # wajib membawa alasan, jadi setup pun harus menyertakannya.
                    if step == "FAILED":
                        await transition(conn, oid, step,
                                         set_fields={"fail_reason": "qa-fixture"})
                    else:
                        await transition(conn, oid, step)
    return oid


ALL_STATUSES = list(ALLOWED_TRANSITIONS)


@pytest.mark.parametrize("from_status", ALL_STATUSES)
@pytest.mark.parametrize("to_status", ALL_STATUSES)
async def test_transition_matrix_exhaustive(from_status: str, to_status: str):
    """Ekshaustif semua pasangan (from, to): berhasil iff ada di tabel.

    Properti: transition() sukses ⇔ to_status ∈ ALLOWED_TRANSITIONS[from_status],
    dan setiap sukses meng-append baris order_events from->to.
    """
    oid = await _insert_order_at(from_status)
    allowed = to_status in ALLOWED_TRANSITIONS[from_status]
    async with db.pool().connection() as conn:
        async with conn.transaction():
            if allowed:
                # to_status FAILED wajib membawa alasan (constraint DB).
                if to_status == "FAILED":
                    result = await transition(conn, oid, to_status,
                                              set_fields={"fail_reason": "qa-fixture"})
                else:
                    result = await transition(conn, oid, to_status)
                assert result["from"] == from_status
                assert result["to"] == to_status
            else:
                with pytest.raises(InvalidTransition):
                    await transition(conn, oid, to_status)
    if allowed:
        async with db.pool().connection() as conn:
            cur = await conn.execute(
                "SELECT from_status, to_status FROM order_events "
                "WHERE order_id = %s AND to_status = %s",
                (oid, to_status))
            rows = await cur.fetchall()
        assert len(rows) == 1
        assert rows[0]["from_status"] == from_status
