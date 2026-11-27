"""Test RISK-D (t_a172bb7b): config risk per-strategy, global = hard ceiling.

Cakupan unit (fungsi murni, tanpa DB):
- global_config dari settings (default + override operator).
- validate_override: hanya boleh mengetatkan (<= global), tipe & invariant
  trail_activate_r >= be_trigger_r, be_buffer per simbol, key tak dikenal.
- effective: sumber (global/override), be_buffer merge per simbol, dan
  CLAMP saat global mengetat setelah override tersimpan (pertahanan lapis 2).
- auto_sl.position_config: parameter BE/trailing per strategi.

Cakupan integrasi (DB test + app in-process):
- GET panel: nilai efektif + sumber per strategi.
- alur propose (admin) -> decide (owner + 2FA): apply + audit_log, tolak
  non-owner / tanpa 2FA, validasi ceiling diulang saat apply (409).
- titik pakai: gate max_positions & daily_loss_limit per strategi,
  lot sizing RISK-A memakai risk_pct efektif, auto-SL RISK-B per strategi.
"""
from __future__ import annotations

import json

import pytest
from httpx import ASGITransport, AsyncClient

from app import auto_sl, db, market, risk_config
from app.auth import hash_password
from app.main import app
from app.risk_config import (
    RiskOverrideInvalid,
    effective,
    global_config,
    validate_override,
)


def _settings(**over) -> dict:
    base = {
        "risk_per_trade_pct": 0.5,
        "max_positions": 5,
        "max_daily_drawdown": 100.0,
        "allowed_symbols": ["XAUUSD"],
    }
    base.update(over)
    return base


# =========================================================== unit: global

def test_global_config_defaults():
    g = global_config({})
    assert g["risk_pct"] == 0.5
    assert g["max_positions"] == risk_config.DEFAULT_MAX_POSITIONS
    assert g["daily_loss_limit"] == 100.0
    assert g["be_trigger_r"] == 1.0
    assert g["trail_atr_mult"] == 1.5
    assert g["trail_activate_r"] == 1.0
    assert g["be_buffer_usd"] == {"XAUUSD": 0.30, "BTCUSD": 40.0}


def test_global_config_reads_operator_overrides():
    g = global_config(_settings(risk_per_trade_pct=0.4, max_positions=2,
                                max_daily_drawdown=250.0,
                                auto_sl={"be_trigger_r": 0.7,
                                         "trail_atr_mult": 1.2,
                                         "trail_activate_r": 0.9,
                                         "be_buffer_usd": {"XAUUSD": 0.25}}))
    assert (g["risk_pct"], g["max_positions"], g["daily_loss_limit"]) == \
        (0.4, 2, 250.0)
    assert g["be_trigger_r"] == 0.7
    assert g["be_buffer_usd"] == {"XAUUSD": 0.25}


# ========================================================= unit: validasi

def test_validate_accepts_tightening_all_keys():
    clean = validate_override("london_breakout", {
        "risk_pct": 0.3, "max_positions": 2, "daily_loss_limit": 50,
        "be_trigger_r": 0.8, "be_buffer": 0.2,
        "trail_atr_mult": 1.0, "trail_activate_r": 0.9,
    }, _settings())
    assert clean == {
        "risk_pct": 0.3, "max_positions": 2, "daily_loss_limit": 50.0,
        "be_trigger_r": 0.8, "be_buffer": {"XAUUSD": 0.2},
        "trail_atr_mult": 1.0, "trail_activate_r": 0.9,
    }


def test_validate_equals_global_is_allowed():
    clean = validate_override("london_breakout",
                              {"risk_pct": 0.5, "max_positions": 5},
                              _settings())
    assert clean == {"risk_pct": 0.5, "max_positions": 5}


@pytest.mark.parametrize("overrides,needle", [
    ({"risk_pct": 0.6}, "melebihi batas global"),
    ({"risk_pct": -0.1}, "harus > 0"),
    ({"risk_pct": "0.3"}, "harus angka"),
    ({"max_positions": 6}, "melebihi batas global"),
    ({"max_positions": 2.5}, "bilangan bulat"),
    ({"max_positions": 0}, ">= 1"),
    ({"daily_loss_limit": 150}, "melebihi batas global"),
    ({"be_buffer": 0.5}, "melebihi batas global"),          # XAUUSD cap 0.30
    ({"be_buffer": {"EURUSD": 0.1}}, "tidak punya batas global"),
    ({"trail_atr_mult": 2.0}, "melebihi batas global"),
    ({"trail_activate_r": 0.5}, "harus >= be_trigger_r"),
    ({"leverage": 100}, "key tidak dikenal"),
])
def test_validate_rejects(overrides, needle):
    with pytest.raises(RiskOverrideInvalid) as exc:
        validate_override("london_breakout", overrides, _settings())
    assert any(needle in e for e in exc.value.errors), exc.value.errors


def test_validate_null_means_inherit_global():
    assert validate_override("london_breakout",
                             {"risk_pct": None, "max_positions": 2},
                             _settings()) == {"max_positions": 2}
    assert validate_override("london_breakout", None, _settings()) == {}


def test_validate_be_buffer_scalar_needs_single_symbol_strategy():
    with pytest.raises(RiskOverrideInvalid):
        validate_override("llm", {"be_buffer": 0.2}, _settings())


def test_validate_be_buffer_per_symbol_for_multipair_strategy():
    clean = validate_override(
        "llm", {"be_buffer": {"XAUUSD": 0.2, "BTCUSD": 30}},
        _settings(allowed_symbols=["XAUUSD", "BTCUSD"]))
    assert clean == {"be_buffer": {"XAUUSD": 0.2, "BTCUSD": 30.0}}
    with pytest.raises(RiskOverrideInvalid):
        validate_override("llm", {"be_buffer": {"BTCUSD": 50}},
                          _settings(allowed_symbols=["BTCUSD"]))


# ========================================================= unit: efektif

def test_effective_global_then_override_sources():
    base = _settings()
    eff = effective("london_breakout", {}, base)
    assert eff["values"]["risk_pct"] == 0.5
    assert eff["sources"]["risk_pct"] == "global"
    assert eff["values"]["be_buffer"] == {"XAUUSD": 0.30, "BTCUSD": 40.0}

    eff = effective("london_breakout",
                    {"risk_pct": 0.3, "be_buffer": {"XAUUSD": 0.2}}, base)
    assert eff["values"]["risk_pct"] == 0.3
    assert eff["sources"]["risk_pct"] == "override"
    assert eff["values"]["be_buffer"] == {"XAUUSD": 0.2, "BTCUSD": 40.0}
    assert eff["sources"]["be_buffer"] == "override"
    assert eff["capped"] == []


def test_effective_clamps_stale_override_to_global_ceiling():
    """Global mengetat setelah override disetujui -> clamp, bukan bocor."""
    eff = effective("london_breakout", {"risk_pct": 0.4,
                                        "be_buffer": {"XAUUSD": 0.28}},
                    _settings(risk_per_trade_pct=0.2,
                              auto_sl={"be_buffer_usd": {"XAUUSD": 0.1}}))
    assert eff["values"]["risk_pct"] == 0.2
    assert eff["sources"]["risk_pct"] == "override_capped"
    assert eff["values"]["be_buffer"]["XAUUSD"] == 0.1
    assert "be_buffer.XAUUSD" in eff["capped"]


def test_effective_ignores_unreadable_stored_value():
    eff = effective("london_breakout", {"risk_pct": "rusak"}, _settings())
    assert eff["values"]["risk_pct"] == 0.5     # fail-safe ke global
    assert eff["sources"]["risk_pct"] == "global"


def test_position_config_uses_strategy_override():
    base = _settings()
    cfg = auto_sl.auto_sl_config({"auto_sl": {"enabled": True}})
    row = auto_sl.position_config(cfg, "llm", {"be_trigger_r": 0.6,
                                               "trail_atr_mult": 1.0,
                                               "trail_activate_r": 0.7,
                                               "be_buffer": {"XAUUSD": 0.2}},
                                  base)
    assert row["be_trigger_r"] == 0.6
    assert row["trail_atr_mult"] == 1.0
    assert row["trail_activate_r"] == 0.7
    assert row["be_buffer_usd"]["XAUUSD"] == 0.2
    assert row["risk_sources"]["be_trigger_r"] == "override"
    # key global lain tetap dari auto_sl global
    assert row["trail_min_usd"] == cfg["trail_min_usd"]


# ================================================= integrasi: setup/helpers

def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def _exec(sql, params=()):
    async with db.pool().connection() as conn:
        await conn.execute(sql, params)


async def _csrf(client) -> str:
    return (await client.get("/auth/me")).json()["csrf_token"]


@pytest.fixture(autouse=True)
async def _risk_env(_clean_db):
    """Isolasi settings risk + override antar test (settings tidak truncate)."""
    await db.set_setting("auto_sl", {"enabled": False})
    await db.set_setting("risk_per_trade_pct", 0.5)
    await db.set_setting("max_positions", 5)
    await db.set_setting("max_daily_drawdown", 100.0)
    await db.set_setting("llm_auto_lot", {"enabled": False})
    await db.set_setting("owner_username", "tester")
    yield
    await _exec("DELETE FROM strategy_risk_overrides")
    await _exec("DELETE FROM settings WHERE key IN "
                "('owner_username', 'llm_risk')")
    await db.set_setting("auto_sl", {"enabled": False})
    await db.set_setting("risk_per_trade_pct", 0.5)
    await db.set_setting("max_positions", 5)
    await db.set_setting("max_daily_drawdown", 100.0)
    await db.set_setting("llm_auto_lot", {"enabled": False})


async def _make_user(username: str, password: str, role: str) -> AsyncClient:
    await _exec(
        "INSERT INTO users (username, password_hash, role) VALUES (%s, %s, %s)",
        (username, hash_password(password), role))
    c = _client()
    r = await c.post("/auth/login",
                     json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    c.headers["x-csrf-token"] = r.json()["csrf_token"]
    return c


async def _override_row(strategy_id: str = "london_breakout"):
    async with db.pool().connection() as conn:
        row = await (await conn.execute(
            "SELECT overrides, updated_by FROM strategy_risk_overrides "
            "WHERE strategy_id = %s", (strategy_id,))).fetchone()
    return dict(row) if row else None


async def _set_override_direct(strategy_id: str, overrides: dict) -> None:
    """Seed override tanpa alur approval (hanya untuk test titik pakai)."""
    await _exec(
        "INSERT INTO strategy_risk_overrides (strategy_id, overrides, updated_by) "
        "VALUES (%s, %s, 'test-seed') ON CONFLICT (strategy_id) DO UPDATE "
        "SET overrides = EXCLUDED.overrides",
        (strategy_id, json.dumps(overrides)))


_TICKET = [900000]


async def _seed_position(strategy: str, *, status: str = "OPEN",
                         profit: float = 0.0) -> str:
    _TICKET[0] += 1
    async with db.pool().connection() as conn:
        order = await (await conn.execute(
            "INSERT INTO orders (symbol, side, volume, sl, tp, strategy, status) "
            "VALUES ('XAUUSD', 'BUY', 0.1, 1990, 2010, %s, 'FILLED') RETURNING id",
            (strategy,))).fetchone()
        await conn.execute(
            "INSERT INTO positions (ticket, order_id, symbol, side, volume, "
            "open_price, open_time, sl, tp, profit, status, close_time) "
            "VALUES (%s, %s, 'XAUUSD', 'BUY', 0.01, 2000, now(), 1990, 2010, %s, %s, "
            "CASE WHEN %s = 'CLOSED' THEN now() ELSE NULL END)",
            (_TICKET[0], order["id"], profit, status, status))
    return str(order["id"])


def _order_body(**over):
    body = {"symbol": "XAUUSD", "side": "BUY", "volume": 0.1,
            "sl": 1998.0, "tp": 2010.0, "strategy": "london_breakout"}
    body.update(over)
    return body


# ============================================== integrasi: panel + approval

async def test_panel_lists_effective_config_per_strategy(client):
    await _set_override_direct("mean_reversion", {"risk_pct": 0.25})
    r = await client.get("/risk/config/strategies")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["global"]["max_positions"] == 5
    rows = {s["strategy_id"]: s for s in body["strategies"]}
    assert {"london_breakout", "mean_reversion", "btc_range_breakout"} <= set(rows)
    assert rows["mean_reversion"]["effective"]["risk_pct"] == 0.25
    assert rows["mean_reversion"]["sources"]["risk_pct"] == "override"
    assert rows["london_breakout"]["effective"]["risk_pct"] == 0.5
    assert rows["london_breakout"]["sources"]["risk_pct"] == "global"
    assert {k["key"] for k in body["keys"]} == set(risk_config.KEY_ORDER)


async def test_propose_requires_admin_role(client):
    viewer = await _make_user("viewer", "viewerpass", "user")
    try:
        r = await viewer.post("/risk/config/strategies/london_breakout/propose",
                              json={"overrides": {"risk_pct": 0.3}})
        assert r.status_code == 403, r.text
    finally:
        await viewer.aclose()
    async with db.pool().connection() as conn:
        n = (await (await conn.execute(
            "SELECT COUNT(*) AS n FROM strategy_risk_override_requests")).fetchone())["n"]
    assert n == 0


async def test_propose_invalid_ceiling_rejected_422(client):
    r = await client.post("/risk/config/strategies/london_breakout/propose",
                          json={"overrides": {"risk_pct": 0.9}})
    assert r.status_code == 422, r.text
    assert any("melebihi batas global" in e
               for e in r.json()["detail"]["errors"])
    async with db.pool().connection() as conn:
        n = (await (await conn.execute(
            "SELECT COUNT(*) AS n FROM strategy_risk_override_requests")).fetchone())["n"]
    assert n == 0


async def test_full_approval_flow_applies_override_with_audit(client_2fa):
    proposed = await client_2fa.post(
        "/risk/config/strategies/london_breakout/propose",
        json={"overrides": {"risk_pct": 0.3, "max_positions": 2,
                            "be_trigger_r": 0.8},
              "note": "turunkan risk London Breakout"})
    assert proposed.status_code == 201, proposed.text
    req = proposed.json()["request"]
    assert req["status"] == "PROPOSED" and req["requested_by"] == "tester"

    # Belum berlaku: config efektif masih global.
    panel = (await client_2fa.get(
        "/risk/config/strategies/london_breakout")).json()
    assert panel["effective"]["risk_pct"] == 0.5
    assert panel["pending"]["id"] == req["id"]

    decided = await client_2fa.post(
        f"/risk/config/requests/{req['id']}/decision",
        json={"decision": "APPROVED", "note": "disetujui owner"})
    assert decided.status_code == 200, decided.text
    out = decided.json()
    assert out["status"] == "APPROVED" and out["decided_by"] == "tester"
    assert out["applied_at"] is not None
    assert out["effective"]["values"]["risk_pct"] == 0.3

    row = await _override_row()
    assert row["overrides"] == {"risk_pct": 0.3, "max_positions": 2,
                                "be_trigger_r": 0.8}
    assert row["updated_by"] == "tester"

    panel = (await client_2fa.get(
        "/risk/config/strategies/london_breakout")).json()
    assert panel["effective"]["risk_pct"] == 0.3
    assert panel["sources"]["risk_pct"] == "override"
    assert panel["sources"]["daily_loss_limit"] == "global"
    assert panel["pending"] is None

    async with db.pool().connection() as conn:
        audit = await (await conn.execute(
            "SELECT actor, action, object, details FROM audit_log "
            "WHERE action = 'RISK_OVERRIDE_APPLIED'")).fetchall()
    assert len(audit) == 1
    assert audit[0]["actor"] == "tester"
    assert audit[0]["object"] == "strategy:london_breakout"
    assert audit[0]["details"]["previous"] == {}
    assert audit[0]["details"]["overrides"]["risk_pct"] == 0.3


async def test_decide_requires_2fa(client):
    proposed = await client.post(
        "/risk/config/strategies/london_breakout/propose",
        json={"overrides": {"risk_pct": 0.3}})
    req_id = proposed.json()["request"]["id"]
    r = await client.post(f"/risk/config/requests/{req_id}/decision",
                          json={"decision": "APPROVED"})
    assert r.status_code == 403
    assert "2FA" in r.json()["detail"]
    assert await _override_row() is None


async def test_decide_requires_owner(client_2fa):
    other = await _make_user("admin2", "admin2pass", "admin")
    try:
        secret = (await other.post("/auth/2fa/setup")).json()["secret"]
        from app import totp
        import time
        assert (await other.post(
            "/auth/2fa/enable",
            json={"code": totp.totp_at(secret)})).status_code == 200
        assert (await other.post(
            "/auth/2fa/challenge",
            json={"code": totp.totp_at(secret, time.time() + 30)})).status_code == 200
        proposed = await client_2fa.post(
            "/risk/config/strategies/london_breakout/propose",
            json={"overrides": {"risk_pct": 0.3}})
        req_id = proposed.json()["request"]["id"]
        r = await other.post(f"/risk/config/requests/{req_id}/decision",
                             json={"decision": "APPROVED"})
        assert r.status_code == 403
        assert "owner" in r.json()["detail"]
    finally:
        await other.aclose()
    assert await _override_row() is None


async def test_approve_revalidates_ceiling_after_global_tightens(client_2fa):
    proposed = await client_2fa.post(
        "/risk/config/strategies/london_breakout/propose",
        json={"overrides": {"risk_pct": 0.3}})
    req_id = proposed.json()["request"]["id"]
    await db.set_setting("risk_per_trade_pct", 0.2)   # ceiling mengetat
    r = await client_2fa.post(f"/risk/config/requests/{req_id}/decision",
                              json={"decision": "APPROVED"})
    assert r.status_code == 409, r.text
    assert any("melebihi batas global" in e
               for e in r.json()["detail"]["errors"])
    assert await _override_row() is None                # tidak diterapkan
    panel = (await client_2fa.get(
        "/risk/config/strategies/london_breakout")).json()
    assert panel["effective"]["risk_pct"] == 0.2


async def test_reject_keeps_global_and_logs(client_2fa):
    proposed = await client_2fa.post(
        "/risk/config/strategies/london_breakout/propose",
        json={"overrides": {"risk_pct": 0.3}})
    req_id = proposed.json()["request"]["id"]
    r = await client_2fa.post(f"/risk/config/requests/{req_id}/decision",
                              json={"decision": "REJECTED", "note": "belum perlu"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "REJECTED"
    assert await _override_row() is None
    async with db.pool().connection() as conn:
        actions = [row["action"] for row in await (await conn.execute(
            "SELECT action FROM audit_log WHERE action LIKE 'RISK_%%' "
            "ORDER BY id")).fetchall()]
    assert actions == ["RISK_OVERRIDE_REJECTED"]


async def test_new_proposal_supersedes_pending(client_2fa):
    first = (await client_2fa.post(
        "/risk/config/strategies/london_breakout/propose",
        json={"overrides": {"risk_pct": 0.4}})).json()["request"]
    second = (await client_2fa.post(
        "/risk/config/strategies/london_breakout/propose",
        json={"overrides": {"risk_pct": 0.3}})).json()["request"]
    async with db.pool().connection() as conn:
        row = await (await conn.execute(
            "SELECT status FROM strategy_risk_override_requests WHERE id = %s",
            (first["id"],))).fetchone()
    assert row["status"] == "SUPERSEDED"
    # usulan lama tidak bisa di-approve lagi
    r = await client_2fa.post(f"/risk/config/requests/{first['id']}/decision",
                              json={"decision": "APPROVED"})
    assert r.status_code == 409
    assert await _override_row() is None
    # usulan terbaru masih PROPOSED
    assert second["status"] == "PROPOSED"


# ================================================== integrasi: titik pakai

async def test_gate_max_positions_per_strategy(client, tick_2000):
    await _set_override_direct("london_breakout", {"max_positions": 2})
    await _seed_position("london_breakout")
    await _seed_position("london_breakout")
    r = await client.post("/orders", json=_order_body(),
                          headers={"x-csrf-token": await _csrf(client)})
    assert r.status_code == 422, r.text
    reasons = r.json()["rejected_reasons"]
    assert any("max positions reached" in x for x in reasons), reasons

    # override lebih longgar (masih <= global) -> order lolos
    await _set_override_direct("london_breakout", {"max_positions": 3})
    r = await client.post("/orders", json=_order_body(),
                          headers={"x-csrf-token": await _csrf(client)})
    assert r.status_code == 201, r.text


async def test_gate_max_positions_global_applies_without_override(client, tick_2000):
    """Tanpa override, ceiling global (5) tetap berlaku untuk strategi."""
    for _ in range(5):
        await _seed_position("london_breakout")
    r = await client.post("/orders", json=_order_body(),
                          headers={"x-csrf-token": await _csrf(client)})
    assert r.status_code == 422, r.text
    assert any("max positions reached" in x
               for x in r.json()["rejected_reasons"])


async def test_gate_daily_loss_limit_per_strategy(client, tick_2000):
    await _set_override_direct("london_breakout", {"daily_loss_limit": 50})
    await _seed_position("london_breakout", status="CLOSED", profit=-60.0)
    r = await client.post("/orders", json=_order_body(),
                          headers={"x-csrf-token": await _csrf(client)})
    assert r.status_code == 422, r.text
    reasons = r.json()["rejected_reasons"]
    assert any("daily loss limit reached" in x for x in reasons), reasons
    # pelanggaran per-strategy bukan drawdown akun: tidak halt global
    settings = await db.get_settings()
    assert not settings.get("halted")
    # strategi lain tidak terpengaruh rugi strategi ini
    r2 = await client.post("/orders", json=_order_body(strategy="mean_reversion"),
                           headers={"x-csrf-token": await _csrf(client)})
    assert r2.status_code == 201, r2.text


async def test_lot_sizing_uses_effective_strategy_risk_pct(client, tick_2000):
    await db.set_setting("llm_auto_lot", {"enabled": True})
    await db.set_setting("llm_risk", {"calendar_blackout": {"enabled": False}})
    await _set_override_direct("llm", {"risk_pct": 0.25})
    r = await client.post(
        "/orders",
        json=_order_body(strategy="llm", volume=0.05, sl=1990.0, tp=2010.0),
        headers={"x-csrf-token": await _csrf(client)})
    assert r.status_code == 201, r.text
    order = r.json()
    detail = (await client.get(f"/orders/{order['id']}")).json()
    auto = next(e for e in detail["events"]
                if e["to_status"] == "RISK_PASS")["payload"]["auto_lot"]
    assert auto["risk_pct"] == 0.25
    assert auto["risk_pct_source"] == "override"
    assert auto["lot"] is not None and auto["raw_lot"] > 0


async def test_lot_sizing_clamps_stale_override_to_global(client, tick_2000):
    """Override tersimpan 0.9 (di atas global 0.5) tidak boleh dipakai."""
    await db.set_setting("llm_auto_lot", {"enabled": True})
    await db.set_setting("llm_risk", {"calendar_blackout": {"enabled": False}})
    await _set_override_direct("llm", {"risk_pct": 0.9})
    r = await client.post(
        "/orders",
        json=_order_body(strategy="llm", volume=0.05, sl=1990.0, tp=2010.0),
        headers={"x-csrf-token": await _csrf(client)})
    order = r.json()
    detail = (await client.get(f"/orders/{order['id']}")).json()
    auto = next(e for e in detail["events"]
                if e["to_status"] == "RISK_PASS")["payload"]["auto_lot"]
    assert auto["risk_pct"] == 0.5
    assert auto["risk_pct_source"] == "override_capped"


async def test_auto_sl_uses_strategy_override_be_trigger(_clean_db):
    """BE trigger 0.5R (override) memicu BE walau global 1.0R belum tercapai."""
    await db.set_setting("auto_sl", {"enabled": True})
    await _set_override_direct("llm", {"be_trigger_r": 0.5})
    async with db.pool().connection() as conn:
        order = await (await conn.execute(
            "INSERT INTO orders (symbol, side, volume, sl, tp, strategy, status) "
            "VALUES ('XAUUSD', 'BUY', 0.01, 1995, 2010, 'llm', 'FILLED') "
            "RETURNING id")).fetchone()
        await conn.execute(
            "INSERT INTO positions (ticket, order_id, symbol, side, volume, "
            "open_price, sl, tp, profit, status) "
            "VALUES (990001, %s, 'XAUUSD', 'BUY', 0.01, 2000, 1995, 2010, 3, 'OPEN')",
            (order["id"],))
    market.update_tick("XAUUSD", bid=2003.0, ask=2003.3)   # +0.6R
    summary = await auto_sl.run_cycle()
    assert summary["positions"] == 1
    assert summary["modified"] == 1
    async with db.pool().connection() as conn:
        cmd = await (await conn.execute(
            "SELECT payload FROM bridge_commands ORDER BY id DESC LIMIT 1")).fetchone()
        event = await (await conn.execute(
            "SELECT payload FROM order_events WHERE to_status = 'AUTO_SL_MODIFY' "
            "ORDER BY id DESC LIMIT 1")).fetchone()
    assert cmd["payload"]["reason"] == "auto_break_even"
    assert cmd["payload"]["sl"] == pytest.approx(2000.30)
    assert event["payload"]["strategy"] == "llm"
    assert event["payload"]["risk_source"] == "override"
