"""Test LLM agent v2 (FUND2-LLM-B1, t_9f36a70a; lanjutan t_2a751a6c).

Cakupan: enum kind baru (cut/sl/be/tp/layer) + prompt v2.0.0, endpoint
/llm-agent/cycle + /llm-agent/modify, layer via POST /orders intent=layer,
anti-spam dua lapis (loop pre-check + gate API), gate modify, dan migrasi
l012 (tabel llm_introspections append-only).
"""
from __future__ import annotations

import asyncio
import json
import uuid
from pathlib import Path
from unittest.mock import patch

import httpx
import psycopg
import pytest
from httpx import ASGITransport, AsyncClient

from app import db, llm_context_extras, market
from app.llm_agent_loop import (
    PROMPT_VERSION,
    SYSTEM_PROMPT,
    _collect_context,
    _post_cycle,
    _submit_decision,
)
from app.llm_risk import (
    DEFAULT_LLM_AGENT_V2,
    get_llm_agent_v2,
    layer_gate_reason,
    llm_open_positions,
    modify_gate_reason,
    new_order_block_reason,
)
from app.main import app
from app.risk import DEFAULT_LLM_RISK


@pytest.fixture(autouse=True)
def _mock_calendar(monkeypatch):
    """Kalender difake ok/tanpa event (pola test_llm_risk.py) supaya POST
    /orders strategy llm tidak memukul feed kalender live."""

    async def _fake_calendar(now_utc=None):
        return {"status": "ok", "source": "test", "as_of": None, "events": []}

    monkeypatch.setattr(llm_context_extras, "fetch_calendar", _fake_calendar)


@pytest.fixture(autouse=True)
async def _reset_llm_settings(_clean_db):
    """Reset state LLM antar-test (settings tidak di-TRUNCATE _clean_db)."""
    await db.set_setting("llm_risk", dict(DEFAULT_LLM_RISK))
    await db.set_setting("llm_agent_pause", None)
    await db.set_setting("llm_breaker_ack", None)
    yield
    await db.set_setting("llm_agent_pause", None)
    await db.set_setting("llm_breaker_ack", None)


async def _set_llm_risk(**kw):
    settings = await db.get_settings()
    cfg = dict(settings.get("llm_risk") or {})
    cfg.update(kw)
    await db.set_setting("llm_risk", cfg)


async def _unleash_rate_limit():
    """Longgarkan rate limit/cooldown/breaker untuk test yang kirim banyak order."""
    await _set_llm_risk(cooldown_s=0, max_orders_per_min=10, max_orders_per_day=20,
                        consecutive_failed_pause=999)


@pytest.fixture
async def agent_client(user):
    """Client ter-login sebagai role 'agent' (service fund2-llm-agent)."""
    from app import auth

    async with db.pool().connection() as conn:
        await conn.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (%s, %s, 'agent')",
            ("svc-llm-agent-v2", auth.hash_password("***")),
        )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post("/auth/login",
                            json={"username": "svc-llm-agent-v2", "password": "***"})
        assert resp.status_code == 200, resp.text
        c.headers["x-csrf-token"] = resp.json()["csrf_token"]
        yield c


async def _open_llm_position(ticket, *, side="BUY", volume=0.10, sl=1999.0,
                             tp=2010.0, open_price=2000.0):
    """Order strategy 'llm' FILLED + posisi OPEN yang menempel (positions↔orders).

    SL default 1999 (jarak 1 dari entry) supaya worst-case loss posisi tidak
    menembus gate konsentrasi portofolio (1% equity) pada test layer/anti-spam.
    """
    async with db.pool().connection() as conn:
        row = await (await conn.execute(
            "INSERT INTO orders (symbol, side, volume, sl, tp, strategy, status) "
            "VALUES ('XAUUSD', %s, %s, %s, %s, 'llm', 'FILLED') RETURNING id",
            (side, volume, sl, tp),
        )).fetchone()
        await conn.execute(
            "INSERT INTO positions (ticket, order_id, symbol, side, volume, "
            "open_price, sl, tp, profit, status) "
            "VALUES (%s, %s, 'XAUUSD', %s, %s, %s, %s, %s, 0, 'OPEN')",
            (ticket, row["id"], side, volume, open_price, sl, tp),
        )
        return str(row["id"])


async def _insert_plain_order():
    """Order kosong untuk test audit /decisions yang butuh order_id valid."""
    async with db.pool().connection() as conn:
        row = await (await conn.execute(
            "INSERT INTO orders (symbol, side, volume, sl, tp, strategy, status) "
            "VALUES ('XAUUSD', 'BUY', 0.01, 1990, 2010, 'llm', 'FILLED') "
            "RETURNING id",
        )).fetchone()
        return str(row["id"])


def _order_body(**overrides):
    body = {"symbol": "XAUUSD", "side": "BUY", "volume": 0.01,
            "sl": 1998.0, "tp": 2005.0, "strategy": "llm"}
    body.update(overrides)
    return body


def _modify_body(**overrides):
    body = {"symbol": "XAUUSD", "kind": "sl", "sl": 1999.0,
            "reasoning": "geser SL ke arah harga", "confidence": 0.8,
            "model": "test-model", "prompt_version": PROMPT_VERSION,
            "cycle_id": "testcycle-modify-01"}
    body.update(overrides)
    return body


# ---------------------------------------------------------------- D1: prompt
def test_prompt_version_is_2():
    # 2.4.0-facts-quality: level S/R deterministik + spread/ATR + proxy dollar.
    assert PROMPT_VERSION == "2.4.0-facts-quality"


def test_system_prompt_defines_all_kinds():
    low = SYSTEM_PROMPT.lower()
    for kind in ("order", "cut", "hold", "sl", "be", "tp", "layer"):
        assert f'"{kind}"' in low, f"kind {kind} harus ada di SYSTEM_PROMPT"


def test_system_prompt_binds_antispam_rule():
    low = SYSTEM_PROMPT.lower()
    # Aturan tegas: ada posisi llm OPEN -> dilarang kind=order.
    assert "dilarang kind=order" in low
    assert "llm_positions" in low
    assert "entry_reasoning" in low
    # Aturan lama yang tetap penting.
    assert "json" in low
    assert "instruksi" in low
    assert "data" in low


async def test_collect_context_enriches_llm_positions(user):
    """D1: konteks memuat posisi llm per simbol (entry/sl/tp/profit/price_now)
    + reasoning entry dari order_events."""
    order_id = await _open_llm_position(770001, sl=1990.0, tp=2010.0, open_price=2000.0)
    async with db.pool().connection() as conn:
        await conn.execute(
            "INSERT INTO order_events (order_id, from_status, to_status, decision) "
            "VALUES (%s, NULL, 'AGENT_ORDER', %s)",
            (order_id, json.dumps({"kind": "order", "reasoning": "breakout entry",
                                   "confidence": 0.7, "model": "m",
                                   "prompt_version": PROMPT_VERSION})),
        )
        await conn.execute(
            "INSERT INTO candles (symbol, timeframe, ts, open, high, low, close) "
            "VALUES ('XAUUSD', 'M5', now() - interval '5 minutes', 1999, 2001, 1998, 2000.5)",
        )
        ctx = await _collect_context(conn)
    block = ctx["symbols"]["XAUUSD"]
    assert block["llm_positions"], "posisi llm harus masuk konteks"
    pos = block["llm_positions"][0]
    assert pos["entry"] == 2000.0
    assert pos["sl"] == 1990.0
    assert pos["tp"] == 2010.0
    assert pos["price_now"] == 2000.5
    assert pos["volume"] == 0.10
    assert pos["entry_reasoning"] == "breakout entry"
    # open_positions tetap memuat posisi (kini dengan sl/tp/is_llm).
    assert block["open_positions"][0]["is_llm"] is True


async def test_collect_context_marks_non_llm_positions(user):
    """Posisi non-llm tidak masuk llm_positions (anti-spam tidak memblock)."""
    async with db.pool().connection() as conn:
        row = await (await conn.execute(
            "INSERT INTO orders (symbol, side, volume, sl, tp, strategy, status) "
            "VALUES ('XAUUSD', 'BUY', 0.10, 1990, 2010, 'manual', 'FILLED') "
            "RETURNING id",
        )).fetchone()
        await conn.execute(
            "INSERT INTO positions (ticket, order_id, symbol, side, volume, "
            "open_price, sl, tp, status) "
            "VALUES (770002, %s, 'XAUUSD', 'BUY', 0.10, 2000, 1990, 2010, 'OPEN')",
            (row["id"],),
        )
        ctx = await _collect_context(conn)
    assert ctx["symbols"]["XAUUSD"]["llm_positions"] == []
    assert len(ctx["symbols"]["XAUUSD"]["open_positions"]) == 1


# ------------------------------------------------- D2: POST /llm-agent/cycle
async def test_cycle_broadcasts_agent_cycle_event(agent_client):
    """POST /cycle broadcast SSE agent_cycle (broadcast-only, tanpa DB)."""
    from app.sse import broadcaster

    q = broadcaster.subscribe()
    try:
        r = await agent_client.post(
            "/llm-agent/cycle",
            json={"cycle_id": "cycle-abc-12345", "phase": "started"},
        )
        assert r.status_code == 200, r.text
        event = q.get_nowait()
        assert event["type"] == "agent_cycle"
        assert event["phase"] == "started"
        assert event["cycle_id"] == "cycle-abc-12345"
    finally:
        broadcaster.unsubscribe(q)


async def test_cycle_error_phase_broadcast_detail(agent_client):
    from app.sse import broadcaster

    q = broadcaster.subscribe()
    try:
        r = await agent_client.post(
            "/llm-agent/cycle",
            json={"cycle_id": "cycle-err-12345", "phase": "error",
                  "detail": "LLM HTTP 502"},
        )
        assert r.status_code == 200, r.text
        event = q.get_nowait()
        assert event["phase"] == "error"
        assert event["detail"] == "LLM HTTP 502"
    finally:
        broadcaster.unsubscribe(q)


async def test_cycle_invalid_phase_422(agent_client):
    r = await agent_client.post(
        "/llm-agent/cycle",
        json={"cycle_id": "cycle-bad-1234", "phase": "bogus"},
    )
    assert r.status_code == 422


async def test_cycle_requires_auth():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.post("/llm-agent/cycle",
                         json={"cycle_id": "cycle-noauth-1", "phase": "started"})
        assert r.status_code == 401


# ----------------------------------------------- D2: POST /llm-agent/modify
async def test_modify_sl_tighten_ok(agent_client, tick_2000):
    """kind=sl: SL long naik (memperketat) -> positions + bridge + audit."""
    await _open_llm_position(770101, sl=1990.0, tp=2010.0)
    r = await agent_client.post("/llm-agent/modify", json=_modify_body(sl=1996.0))
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["sl"] == 1996.0
    assert data["tp"] == 2010.0  # tp tidak berubah
    async with db.pool().connection() as conn:
        pos = await (await conn.execute(
            "SELECT sl, tp FROM positions WHERE ticket = 770101")).fetchone()
        assert float(pos["sl"]) == 1996.0 and float(pos["tp"]) == 2010.0
        cmd = await (await conn.execute(
            "SELECT action, payload, status FROM bridge_commands "
            "ORDER BY created_at DESC LIMIT 1")).fetchone()
        assert cmd["action"] == "MODIFY_SL"
        assert cmd["status"] == "QUEUED"
        assert cmd["payload"]["ticket"] == 770101
        assert float(cmd["payload"]["sl"]) == 1996.0
        assert cmd["payload"]["reason"] == "llm_agent_sl"
        ev = await (await conn.execute(
            "SELECT to_status, decision FROM order_events "
            "WHERE to_status = 'AGENT_MODIFY' ORDER BY id DESC LIMIT 1")).fetchone()
        assert ev is not None
        assert ev["decision"]["kind"] == "sl"
        assert ev["decision"]["reasoning"] == "geser SL ke arah harga"
        assert ev["decision"]["model"] == "test-model"
        assert ev["decision"]["prompt_version"] == PROMPT_VERSION


async def test_modify_be_to_breakeven_ok(agent_client, tick_2000):
    """kind=be: SL ke entry + buffer (long) -> diterima."""
    from app import market

    await _open_llm_position(770102, open_price=2000.0, sl=1990.0)
    # Harga sudah berjalan ke atas BE (2000.5): SL BE tetap di bawah harga.
    market.update_tick("XAUUSD", bid=2001.0, ask=2001.3)
    r = await agent_client.post(
        "/llm-agent/modify", json=_modify_body(kind="be", sl=2000.5))
    assert r.status_code == 200, r.text
    assert r.json()["sl"] == 2000.5


async def test_modify_sl_loosen_rejected(agent_client, tick_2000):
    """SL long turun (melonggarkan) -> ditolak gate tighten."""
    await _open_llm_position(770103, sl=1996.0)
    r = await agent_client.post("/llm-agent/modify", json=_modify_body(sl=1993.0))
    assert r.status_code == 422, r.text
    assert "tighten" in r.json()["detail"]


async def test_modify_sl_crosses_price_rejected(agent_client, tick_2000):
    """SL long >= harga sekarang (langsung trigger) -> ditolak."""
    await _open_llm_position(770104, sl=1990.0)
    r = await agent_client.post("/llm-agent/modify", json=_modify_body(sl=1999.9))
    assert r.status_code == 422, r.text
    assert "harga sekarang" in r.json()["detail"]


async def test_modify_tp_cross_price_rejected(agent_client, tick_2000):
    """kind=tp: TP long di bawah harga sekarang (melintasi) -> ditolak."""
    await _open_llm_position(770105, tp=2010.0)
    r = await agent_client.post(
        "/llm-agent/modify", json=_modify_body(kind="tp", tp=1999.0, sl=None))
    assert r.status_code == 422, r.text
    assert "modify_tp_cross" in r.json()["detail"]


async def test_modify_tp_ok(agent_client, tick_2000):
    await _open_llm_position(770106, tp=2010.0)
    r = await agent_client.post(
        "/llm-agent/modify", json=_modify_body(kind="tp", tp=2008.0, sl=None))
    assert r.status_code == 200, r.text
    async with db.pool().connection() as conn:
        pos = await (await conn.execute(
            "SELECT sl, tp FROM positions WHERE ticket = 770106")).fetchone()
        assert float(pos["tp"]) == 2008.0
        assert pos["sl"] is None or float(pos["sl"]) == 1999.0


async def test_modify_no_position_404(agent_client, tick_2000):
    r = await agent_client.post("/llm-agent/modify", json=_modify_body(sl=1996.0))
    assert r.status_code == 404, r.text


async def test_modify_wrong_side_of_market_rejected(agent_client, tick_2000):
    """Short: SL di atas harga harus tetap > ask; SL 1999 <= ask 2000.15 -> tolak."""
    await _open_llm_position(770107, side="SELL", open_price=2000.0, sl=2010.0)
    r = await agent_client.post("/llm-agent/modify", json=_modify_body(sl=2005.0))
    assert r.status_code == 200, r.text  # short SL turun 2010 -> 2005 = memperketat
    r = await agent_client.post("/llm-agent/modify", json=_modify_body(sl=1999.0))
    assert r.status_code == 422, r.text
    assert "harga sekarang" in r.json()["detail"]


async def test_modify_field_mismatch_422(agent_client, tick_2000):
    """Kontrak ketik: kind=sl tidak boleh membawa tp (dan sebaliknya)."""
    await _open_llm_position(770108)
    r = await agent_client.post(
        "/llm-agent/modify", json=_modify_body(sl=1996.0, tp=2008.0))
    assert r.status_code == 422
    r = await agent_client.post(
        "/llm-agent/modify", json=_modify_body(kind="tp", tp=2008.0, sl=1996.0))
    assert r.status_code == 422
    r = await agent_client.post(
        "/llm-agent/modify", json=_modify_body(kind="bogus"))
    assert r.status_code == 422


async def test_modify_without_tick_fail_closed(agent_client):
    """Tick tidak terbaca -> gate modify fail-closed (422), bukan menebak."""
    await _open_llm_position(770109)
    r = await agent_client.post("/llm-agent/modify", json=_modify_body(sl=1996.0))
    assert r.status_code == 422, r.text
    assert "fail-closed" in r.json()["detail"]


async def test_modify_non_llm_position_404(agent_client, tick_2000):
    """Posisi strategy manual bukan urusan agent -> dianggap tidak ada."""
    async with db.pool().connection() as conn:
        row = await (await conn.execute(
            "INSERT INTO orders (symbol, side, volume, sl, tp, strategy, status) "
            "VALUES ('XAUUSD', 'BUY', 0.10, 1990, 2010, 'manual', 'FILLED') "
            "RETURNING id")).fetchone()
        await conn.execute(
            "INSERT INTO positions (ticket, order_id, symbol, side, volume, "
            "open_price, sl, tp, status) "
            "VALUES (770110, %s, 'XAUUSD', 'BUY', 0.10, 2000, 1990, 2010, 'OPEN')",
            (row["id"],),
        )
    r = await agent_client.post("/llm-agent/modify", json=_modify_body(sl=1996.0))
    assert r.status_code == 404, r.text


# --------------------------------------- D2: /decisions menerima kind baru
def _decision_body(**overrides):
    body = {"symbol": "XAUUSD", "kind": "cut", "reasoning": "exit",
            "confidence": 0.7, "model": "test-model",
            "prompt_version": PROMPT_VERSION, "cycle_id": "testcycle-dec-001"}
    body.update(overrides)
    return body


async def test_decisions_cut_maps_to_agent_close(agent_client):
    order_id = await _insert_plain_order()
    r = await agent_client.post("/llm-agent/decisions",
                                json=_decision_body(kind="cut", order_id=order_id))
    assert r.status_code == 200, r.text
    assert r.json()["to_status"] == "AGENT_CLOSE"


async def test_decisions_close_alias_still_works(agent_client):
    """Perilaku lama tidak berubah: kind=close tetap alias cut -> AGENT_CLOSE."""
    order_id = await _insert_plain_order()
    r = await agent_client.post("/llm-agent/decisions",
                                json=_decision_body(kind="close", order_id=order_id))
    assert r.status_code == 200, r.text
    assert r.json()["to_status"] == "AGENT_CLOSE"


async def test_decisions_modify_kinds_map_to_agent_modify(agent_client):
    for kind in ("sl", "be", "tp"):
        r = await agent_client.post(
            "/llm-agent/decisions",
            json=_decision_body(kind=kind, reasoning=f"ubah {kind}"))
        assert r.status_code == 200, r.text
        assert r.json()["to_status"] == "AGENT_MODIFY"


async def test_decisions_layer_requires_order_id(agent_client):
    r = await agent_client.post("/llm-agent/decisions",
                                json=_decision_body(kind="layer"))
    assert r.status_code == 422


async def test_decisions_layer_maps_to_agent_layer(agent_client):
    order_id = await _insert_plain_order()
    r = await agent_client.post("/llm-agent/decisions",
                                json=_decision_body(kind="layer", order_id=order_id))
    assert r.status_code == 200, r.text
    assert r.json()["to_status"] == "AGENT_LAYER"


async def test_decisions_modify_kinds_reject_order_id(agent_client):
    order_id = await _insert_plain_order()
    r = await agent_client.post(
        "/llm-agent/decisions",
        json=_decision_body(kind="sl", order_id=order_id, reasoning="x"))
    assert r.status_code == 422


async def test_decisions_cut_requires_order_id(agent_client):
    r = await agent_client.post("/llm-agent/decisions",
                                json=_decision_body(kind="cut"))
    assert r.status_code == 422


async def test_decisions_old_kinds_unchanged(agent_client):
    """kind lama: order (butuh order_id), hold, invalid - perilaku sama."""
    r = await agent_client.post("/llm-agent/decisions",
                                json=_decision_body(kind="hold"))
    assert r.status_code == 200
    assert r.json()["to_status"] == "AGENT_HOLD"
    r = await agent_client.post("/llm-agent/decisions",
                                json=_decision_body(kind="order"))
    assert r.status_code == 422
    r = await agent_client.post(
        "/llm-agent/decisions", json=_decision_body(kind="tidakada"))
    assert r.status_code == 422


# ------------------------------ D2 butir 3 + D4: intent=layer di POST /orders
async def test_layer_intent_role_guard(client, tick_2000):
    """Role lain (admin, strategy manual) yang mengirim intent -> 422."""
    r = await client.post("/orders", json=_order_body(strategy="manual", intent="layer"))
    assert r.status_code == 422, r.text


async def test_layer_intent_bad_value_422(agent_client, tick_2000):
    r = await agent_client.post("/orders", json=_order_body(intent="bogus"))
    assert r.status_code == 422


async def test_layer_intent_from_llm_strategy_ok(client, tick_2000):
    """Strategy llm tanpa role agent pun dihormati intent-nya (is_llm)."""
    await _unleash_rate_limit()
    await _open_llm_position(770120, volume=0.10)
    r = await client.post("/orders", json=_order_body(strategy="llm", intent="layer",
                                                      volume=0.05, sl=1996.0))
    assert r.status_code == 201, r.text
    assert r.json()["status"] == "RISK_PASS"


# ------------------------------------------------- D3: routing di loop agent
def _llm_result(kind: str, **decision) -> dict:
    d = {"kind": kind, "symbol": "XAUUSD", "reasoning": "alasan",
         "confidence": 0.6, "model": "test-model"}
    d.update(decision)
    return {"decision": d, "raw_content": "{}", "model": "test-model",
            "prompt_tokens": 10, "completion_tokens": 5, "latency_ms": 11}


async def _capture_posts(**responses):
    """Rekam semua http.post (url, json); balas sesuai peta responses."""
    calls: list[dict] = []

    async def fake_post(url, **kwargs):
        calls.append({"url": url, **kwargs})
        for suffix, (status, payload) in responses.items():
            if url.endswith(suffix):
                return httpx.Response(status, json=payload,
                                      request=httpx.Request("POST", url))
        return httpx.Response(200, json={"ok": True}, request=httpx.Request("POST", url))

    return calls, fake_post


async def test_loop_remaps_order_to_hold_when_position_open(user, client):
    """Anti-spam lapisan 1: kind=order saat ada posisi llm OPEN di konteks
    -> remap ke hold, TIDAK POST /orders, audit membawa alasan anti_spam."""
    auth = {"csrf": client.headers["x-csrf-token"], "cookies": client.cookies}
    ctx = {"symbols": {"XAUUSD": {"llm_positions": [
        {"ticket": 1, "side": "BUY", "volume": 0.1, "entry": 2000.0,
         "sl": 1990.0, "tp": 2010.0, "profit": 1.0, "price_now": 2001.0},
    ]}}}
    calls, fake_post = await _capture_posts()
    with patch.object(httpx.AsyncClient, "post", side_effect=fake_post):
        await _submit_decision(httpx.AsyncClient(), auth, "cycle-antispam-1",
                               _llm_result("order", side="BUY", volume=0.01,
                                           sl=1998.0, tp=2005.0), ctx)
    assert [c["url"].rsplit("/", 1)[-1] for c in calls] == ["decisions"]
    audit = calls[0]["json"]
    assert audit["kind"] == "hold"
    assert "anti_spam" in audit["reasoning"]
    assert audit["order_id"] is None


async def test_loop_allows_order_when_no_position(user, client):
    """Tanpa posisi llm: kind=order tetap POST /orders (perilaku lama)."""
    auth = {"csrf": client.headers["x-csrf-token"], "cookies": client.cookies}
    calls, fake_post = await _capture_posts(
        **{"/orders": (201, {"id": "1234abcd-1234-5678-9012-abcdef123456"})})
    with patch.object(httpx.AsyncClient, "post", side_effect=fake_post):
        await _submit_decision(httpx.AsyncClient(), auth, "cycle-order-v2-1",
                               _llm_result("order", side="BUY", volume=0.01,
                                           sl=1998.0, tp=2005.0), _ctx_stops())
    assert calls[0]["url"].endswith("/orders")
    assert "intent" not in calls[0]["json"]
    assert calls[1]["json"]["kind"] == "order"


async def test_loop_routes_modify_for_sl(user, client):
    """kind=sl -> POST /llm-agent/modify (bukan /orders)."""
    auth = {"csrf": client.headers["x-csrf-token"], "cookies": client.cookies}
    calls, fake_post = await _capture_posts()
    with patch.object(httpx.AsyncClient, "post", side_effect=fake_post):
        await _submit_decision(httpx.AsyncClient(), auth, "cycle-sl-v2-1",
                               _llm_result("sl", sl=1996.0), _ctx_stops())
    assert calls[0]["url"].endswith("/llm-agent/modify")
    body = calls[0]["json"]
    assert body["kind"] == "sl" and body["sl"] == 1996.0 and body["tp"] is None
    assert body["prompt_version"] == PROMPT_VERSION
    # Keputusan tetap ter-audit (AGENT_MODIFY, tanpa order_id).
    assert calls[1]["url"].endswith("/decisions")
    assert calls[1]["json"]["kind"] == "sl"
    assert calls[1]["json"]["order_id"] is None


async def test_loop_routes_modify_for_be_and_tp(user, client):
    auth = {"csrf": client.headers["x-csrf-token"], "cookies": client.cookies}
    for kind, field, value in (("be", "sl", 2000.5), ("tp", "tp", 2008.0)):
        calls, fake_post = await _capture_posts()
        with patch.object(httpx.AsyncClient, "post", side_effect=fake_post):
            await _submit_decision(httpx.AsyncClient(), auth, f"cycle-{kind}-v2",
                                   _llm_result(kind, **{field: value}), _ctx_stops())
        assert calls[0]["url"].endswith("/llm-agent/modify")
        assert calls[0]["json"]["kind"] == kind


async def test_loop_modify_rejected_becomes_invalid(user, client):
    """Modify ditolak API -> audit kind=invalid dgn alasan (pola close lama)."""
    auth = {"csrf": client.headers["x-csrf-token"], "cookies": client.cookies}
    calls, fake_post = await _capture_posts(
        **{"/llm-agent/modify": (422, {"detail": "modify_sl_tighten: ..."})})
    with patch.object(httpx.AsyncClient, "post", side_effect=fake_post):
        await _submit_decision(httpx.AsyncClient(), auth, "cycle-sl-rej-1",
                               _llm_result("sl", sl=1000.0), _ctx_stops())
    assert calls[-1]["url"].endswith("/decisions")
    assert calls[-1]["json"]["kind"] == "invalid"
    assert "modify rejected" in calls[-1]["json"]["reasoning"]


async def test_loop_routes_layer_with_intent(user, client):
    """kind=layer -> POST /orders dengan intent=layer, audit kind=layer."""
    auth = {"csrf": client.headers["x-csrf-token"], "cookies": client.cookies}
    calls, fake_post = await _capture_posts(
        **{"/orders": (201, {"id": "1234abcd-1234-5678-9012-abcdef123456"})})
    with patch.object(httpx.AsyncClient, "post", side_effect=fake_post):
        await _submit_decision(httpx.AsyncClient(), auth, "cycle-layer-v2-1",
                               _llm_result("layer", side="BUY", volume=0.05,
                                           sl=1996.0, tp=2008.0), _ctx_stops())
    assert calls[0]["url"].endswith("/orders")
    assert calls[0]["json"]["intent"] == "layer"
    assert calls[0]["json"]["strategy"] == "llm"
    assert calls[1]["url"].endswith("/decisions")
    assert calls[1]["json"]["kind"] == "layer"
    assert calls[1]["json"]["order_id"] == "1234abcd-1234-5678-9012-abcdef123456"


async def test_loop_cut_uses_close_path(user, client):
    """kind=cut (dan alias close) -> jalur close existing."""
    auth = {"csrf": client.headers["x-csrf-token"], "cookies": client.cookies}
    for kind in ("cut", "close"):
        calls, fake_post = await _capture_posts(
            **{"/llm-agent/close": (200, {"close_order_ids": ["aaaa-bbbb-cccc-dddd"]})})
        with patch.object(httpx.AsyncClient, "post", side_effect=fake_post):
            await _submit_decision(httpx.AsyncClient(), auth, f"cycle-{kind}-v2",
                                   _llm_result(kind), _ctx_stops())
        assert calls[0]["url"].endswith("/llm-agent/close")
        assert calls[1]["url"].endswith("/decisions")
        assert calls[1]["json"]["kind"] == kind
        assert calls[1]["json"]["order_id"] == "aaaa-bbbb-cccc-dddd"


# ------------------------------------------------- D3: SSE cycle per siklus
async def test_post_cycle_never_raises(user, client):
    """auth None / HTTP error / exception -> tidak pernah raise."""
    with patch.object(httpx.AsyncClient, "post",
                      side_effect=httpx.ConnectError("boom")):
        await _post_cycle(httpx.AsyncClient(), {"csrf": "x", "cookies": {}},
                          "cycle-evt-1", "started")  # tidak raise
    await _post_cycle(httpx.AsyncClient(), None, "cycle-evt-2", "error")  # auth None


async def test_agent_loop_posts_cycle_events(monkeypatch, user):
    """Loop mengirim cycle event started; error siklus mengirim error."""
    from app import llm_agent_loop as loop_mod

    stop = asyncio.Event()
    events: list[str] = []

    class _DummyConn:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

    class _DummyPool:
        def connection(self):
            return _DummyConn()

    class _StubDB:
        async def init_pool(self):
            pass

        async def close_pool(self):
            pass

        def pool(self):
            return _DummyPool()

        async def get_settings(self):
            return {"kill_switch": False, "llm_agent_pause": None, "halted": False}

        async def settings_snapshot(self, conn):
            # run_cycle membaca setelan dari koneksi yang sudah dipegang.
            return {"kill_switch": False, "llm_agent_pause": None, "halted": False}

    async def fake_login(http):
        return {"csrf": "x", "cookies": {}}

    async def fake_call_llm(http, ctx, model=None, budget=None, deadline=None):
        return {"decision": {"kind": "hold"}, "raw_content": "",
                "model": "m", "prompt_tokens": 0, "completion_tokens": 0,
                "latency_ms": 0}

    async def fake_preflight(http, auth, cycle_id, symbols):
        # t_afd7fe4e: gate selalu lolos di test ini (fokusnya event siklus).
        return {"ok": True, "allowed": list(symbols), "blocked": [], "reason": None}

    async def fake_submit(http, auth, cycle_id, llm_result, ctx):
        stop.set()

    async def fake_collect(conn, **kwargs):  # extras=/now= dari run_cycle
        return _ctx_stops()

    async def fake_post_cycle(http, auth, cycle_id, phase, detail=None):
        events.append(phase)

    monkeypatch.setattr(loop_mod, "db", _StubDB())
    monkeypatch.setattr(loop_mod, "_login", fake_login)
    monkeypatch.setattr(loop_mod, "_call_llm", fake_call_llm)
    monkeypatch.setattr(loop_mod, "_submit_decision", fake_submit)
    monkeypatch.setattr(loop_mod, "_collect_context", fake_collect)
    monkeypatch.setattr(loop_mod, "_post_cycle", fake_post_cycle)
    monkeypatch.setattr(loop_mod, "_preflight", fake_preflight)
    # t_2a1fbf01: tes ini menguji event siklus, bukan pipeline; patok ke jalur
    # satu-prompt supaya fake `_call_llm` yang dipakai (pipeline paralel punya
    # tes sendiri di test_llm_parallel_pipeline.py).
    monkeypatch.setattr(loop_mod.llm_models, "resolve", lambda settings: {
        "parallel": False, "specialist": "m", "synth": "m", "fallback": "m"})
    await asyncio.wait_for(loop_mod.agent_loop(stop), timeout=10)
    assert events == ["started"]


async def test_agent_loop_posts_error_event_on_failure(monkeypatch, user):
    """Exception di siklus -> event error terkirim, siklus tidak mati."""
    from app import llm_agent_loop as loop_mod

    stop = asyncio.Event()
    events: list[str] = []

    class _DummyConn:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

    class _DummyPool:
        def connection(self):
            return _DummyConn()

    class _StubDB:
        async def init_pool(self):
            pass

        async def close_pool(self):
            pass

        def pool(self):
            return _DummyPool()

        async def get_settings(self):
            return {"kill_switch": False, "llm_agent_pause": None, "halted": False}

    async def fake_login(http):
        return {"csrf": "x", "cookies": {}}

    async def fake_collect(conn, **kwargs):  # extras=/now= dari run_cycle
        stop.set()
        raise RuntimeError("LLM meledak")

    async def fake_post_cycle(http, auth, cycle_id, phase, detail=None):
        events.append(phase)

    async def fake_preflight(http, auth, cycle_id, symbols):
        return {"ok": True, "allowed": list(symbols), "blocked": [], "reason": None}

    monkeypatch.setattr(loop_mod, "db", _StubDB())
    monkeypatch.setattr(loop_mod, "_login", fake_login)
    monkeypatch.setattr(loop_mod, "_collect_context", fake_collect)
    monkeypatch.setattr(loop_mod, "_post_cycle", fake_post_cycle)
    monkeypatch.setattr(loop_mod, "_preflight", fake_preflight)
    await asyncio.wait_for(loop_mod.agent_loop(stop), timeout=10)
    assert events == ["started", "error"]


# ------------------------------------------------- D4: gate deterministik
def _pos(ticket, side="BUY", volume=0.10, sl=1990.0):
    return {"ticket": ticket, "symbol": "XAUUSD", "side": side, "volume": volume,
            "open_price": 2000.0, "sl": sl, "tp": 2010.0, "profit": 0.0}


def test_new_order_block_reason_gate():
    cfg = dict(DEFAULT_LLM_AGENT_V2)
    assert new_order_block_reason([], cfg, "XAUUSD") is None
    reason = new_order_block_reason([_pos(1)], cfg, "XAUUSD")
    assert reason and "llm_position_exists" in reason
    # Owner bisa mematikan via settings.
    off = dict(cfg, block_new_order_with_position=False)
    assert new_order_block_reason([_pos(1)], off, "XAUUSD") is None


def test_layer_gate_reason_rules():
    cfg = dict(DEFAULT_LLM_AGENT_V2)  # max_layers=2, ratio=1.0
    # Tanpa posisi: layer = leg pertama biasa.
    assert layer_gate_reason([], cfg, "XAUUSD", "BUY", 0.10) is None
    # Searah + volume <= leg pertama + belum max -> lolos.
    assert layer_gate_reason([_pos(1, volume=0.10)], cfg, "XAUUSD", "BUY", 0.10) is None
    # Beda arah -> tolak.
    reason = layer_gate_reason([_pos(1, side="BUY")], cfg, "XAUUSD", "SELL", 0.01)
    assert reason and "layer_side_mismatch" in reason
    # Volume melebihi leg pertama -> tolak.
    reason = layer_gate_reason([_pos(1, volume=0.10)], cfg, "XAUUSD", "BUY", 0.11)
    assert reason and "layer_volume" in reason
    # max_layers tercapai -> tolak.
    reason = layer_gate_reason([_pos(1), _pos(2)], cfg, "XAUUSD", "BUY", 0.01)
    assert reason and "layer_max" in reason
    # Ratio bisa dilonggarkan via settings (merge parsial).
    loose = dict(cfg, layer_volume_ratio_max=2.0)
    assert layer_gate_reason([_pos(1, volume=0.05)], loose, "XAUUSD", "BUY", 0.10) is None


def test_modify_gate_reason_rules():
    cfg = dict(DEFAULT_LLM_AGENT_V2)  # tighten only
    pos = _pos(1, side="BUY", sl=1990.0)
    # Tighten long (1990 -> 1996) + di bawah harga -> lolos.
    assert modify_gate_reason(pos, "sl", 1996.0, None,
                              bid=1999.85, ask=2000.15, cfg=cfg) is None
    # Loosen long (1990 -> 1985) -> tolak.
    assert "tighten" in modify_gate_reason(pos, "sl", 1985.0, None,
                                           bid=1999.85, ask=2000.15, cfg=cfg)
    # SL menembus harga sekarang -> tolak.
    assert "harga sekarang" in modify_gate_reason(pos, "sl", 2000.0, None,
                                                  bid=1999.85, ask=2000.15, cfg=cfg)
    # BE long ke entry+buffer -> lolos (masih memperketat dari 1990).
    assert modify_gate_reason(pos, "be", 2000.5, None,
                              bid=2001.0, ask=2001.3, cfg=cfg) is None
    # TP long di bawah harga -> melintasi -> tolak.
    assert "modify_tp_cross" in modify_gate_reason(pos, "tp", None, 1999.0,
                                                   bid=1999.85, ask=2000.15, cfg=cfg)
    # TP long di atas harga -> lolos.
    assert modify_gate_reason(pos, "tp", None, 2008.0,
                              bid=1999.85, ask=2000.15, cfg=cfg) is None
    # Tick hilang -> fail-closed.
    assert "fail-closed" in modify_gate_reason(pos, "sl", 1996.0, None,
                                               bid=None, ask=None, cfg=cfg)
    # modify_sl_only_tighten=False melonggarkan aturan tighten (owner override).
    loose = dict(cfg, modify_sl_only_tighten=False)
    assert modify_gate_reason(pos, "sl", 1985.0, None,
                              bid=1999.85, ask=2000.15, cfg=loose) is None
    # SL lama NULL: boleh pasang SL baru yang sah.
    bare = _pos(2, sl=None)
    assert modify_gate_reason(bare, "sl", 1996.0, None,
                              bid=1999.85, ask=2000.15, cfg=cfg) is None


async def test_llm_open_positions_join(user):
    """Gate query: hanya posisi llm OPEN yang dihitung (join orders)."""
    await _open_llm_position(770130)
    async with db.pool().connection() as conn:
        # Posisi manual tidak ikut.
        row = await (await conn.execute(
            "INSERT INTO orders (symbol, side, volume, sl, tp, strategy, status) "
            "VALUES ('XAUUSD', 'BUY', 0.10, 1990, 2010, 'manual', 'FILLED') "
            "RETURNING id")).fetchone()
        await conn.execute(
            "INSERT INTO positions (ticket, order_id, symbol, side, volume, "
            "open_price, sl, tp, status) "
            "VALUES (770131, %s, 'XAUUSD', 'BUY', 0.10, 2000, 1990, 2010, 'OPEN')",
            (row["id"],),
        )
        pos = await llm_open_positions(conn, "XAUUSD")
    assert len(pos) == 1
    assert pos[0]["ticket"] == 770130


# ----------------------------- D4: anti-spam lapisan 2 di POST /orders (API)
async def test_api_anti_spam_blocks_order_with_position(agent_client, tick_2000):
    """DoD anti-spam di API: ada posisi llm OPEN -> kind=order (POST /orders
    tanpa intent) ditolak FAILED dgn alasan llm_position_exists."""
    await _unleash_rate_limit()
    await _open_llm_position(770140)
    r = await agent_client.post("/orders", json=_order_body())
    assert r.status_code == 422, r.text
    body = r.json()
    assert body["status"] == "FAILED"
    assert any("llm_position_exists" in x for x in body["rejected_reasons"])
    async with db.pool().connection() as conn:
        ev = await (await conn.execute(
            "SELECT payload FROM order_events ORDER BY id DESC LIMIT 1")).fetchone()
    assert ev["payload"]["risk"] == "rejected"


async def test_api_anti_spam_manual_unaffected(client, tick_2000):
    """Order manual (bukan LLM) tetap lolos meski ada posisi llm OPEN."""
    await _open_llm_position(770141)
    r = await client.post("/orders", json=_order_body(strategy="manual"))
    assert r.status_code == 201, r.text
    assert r.json()["status"] == "RISK_PASS"


async def test_api_layer_accepted_then_max_rejected(agent_client, tick_2000):
    """Layer pertama lolos (searah, volume <= leg); layer ketiga kena max_layers."""
    await _unleash_rate_limit()
    await _open_llm_position(770142, volume=0.10)  # leg 1
    r = await agent_client.post(
        "/orders", json=_order_body(intent="layer", volume=0.10, sl=1999.4))
    assert r.status_code == 201, r.text
    assert r.json()["status"] == "RISK_PASS"
    # Simulasikan fill layer-1: order jadi posisi OPEN (di produksi oleh MT5).
    async with db.pool().connection() as conn:
        await conn.execute(
            "INSERT INTO positions (ticket, order_id, symbol, side, volume, "
            "open_price, sl, tp, status) "
            "VALUES (77014201, %s, 'XAUUSD', 'BUY', 0.10, 2000.15, 1999.4, "
            "2010, 'OPEN')", (r.json()["id"],))
    # Layer ke-2: total 2 posisi = max_layers -> tolak.
    r = await agent_client.post(
        "/orders", json=_order_body(intent="layer", volume=0.05, sl=1999.4))
    assert r.status_code == 422, r.text
    assert any("layer_max" in x for x in r.json()["rejected_reasons"])


async def test_api_layer_volume_over_ratio_rejected(agent_client, tick_2000):
    await _unleash_rate_limit()
    await _open_llm_position(770143, volume=0.05)  # leg kecil
    r = await agent_client.post(
        "/orders", json=_order_body(intent="layer", volume=0.10, sl=1996.0))
    assert r.status_code == 422, r.text
    assert any("layer_volume" in x for x in r.json()["rejected_reasons"])


async def test_api_layer_wrong_side_rejected(agent_client, tick_2000):
    await _unleash_rate_limit()
    await _open_llm_position(770144, side="BUY")
    r = await agent_client.post(
        "/orders", json=_order_body(intent="layer", side="SELL", volume=0.05,
                                    sl=2004.0, tp=1996.0))
    assert r.status_code == 422, r.text
    assert any("layer_side_mismatch" in x for x in r.json()["rejected_reasons"])


async def test_api_layer_event_records_intent(agent_client, tick_2000):
    """Audit: event RECEIVED order layer membawa llm_intent."""
    await _unleash_rate_limit()
    await _open_llm_position(770145, volume=0.10)
    r = await agent_client.post(
        "/orders", json=_order_body(intent="layer", volume=0.05, sl=1996.0))
    assert r.status_code == 201, r.text
    order_id = r.json()["id"]
    async with db.pool().connection() as conn:
        ev = await (await conn.execute(
            "SELECT payload FROM order_events WHERE order_id = %s AND to_status = 'RISK_PASS'",
            (order_id,))).fetchone()
    assert ev["payload"]["llm_intent"] == "layer"


# ------------------------------------------------- D5: migrasi l012
def _alembic_cfg():
    from alembic.config import Config

    ini = Path(__file__).resolve().parent.parent / "alembic.ini"
    cfg = Config(str(ini))
    cfg.set_main_option("script_location", str(ini.parent / "alembic"))
    cfg.attributes["configure_logger"] = False
    return cfg


async def _table_exists(name: str) -> bool:
    async with db.pool().connection() as conn:
        row = await (await conn.execute(
            "SELECT to_regclass(%s) AS t", (f"public.{name}",))).fetchone()
    return row["t"] is not None


async def test_l012_llm_introspections_schema():
    """DoD migrasi: tabel ada dgn kolom + constraint sesuai spec D5."""
    assert await _table_exists("llm_introspections")
    async with db.pool().connection() as conn:
        cols = await (await conn.execute(
            "SELECT column_name, data_type FROM information_schema.columns "
            "WHERE table_name = 'llm_introspections' ORDER BY column_name")).fetchall()
        names = {c["column_name"] for c in cols}
        assert {"id", "scope", "ref_key", "evidence", "narasi", "model",
                "prompt_version", "created_at"} <= names
    # CHECK scope trade|daily (koneksi terpisah: transaksi abort setelah error).
    async with db.pool().connection() as conn:
        with pytest.raises(psycopg.errors.CheckViolation):
            await conn.execute(
                "INSERT INTO llm_introspections (scope, ref_key) VALUES ('bogus', 'x')")
    # UNIQUE(scope, ref_key)
    key = f"t-{uuid.uuid4().hex[:12]}"
    async with db.pool().connection() as conn:
        await conn.execute(
            "INSERT INTO llm_introspections (scope, ref_key, narasi) "
            "VALUES ('trade', %s, 'pertama')", (key,))
    async with db.pool().connection() as conn:
        with pytest.raises(psycopg.errors.UniqueViolation):
            await conn.execute(
                "INSERT INTO llm_introspections (scope, ref_key) VALUES ('trade', %s)",
                (key,))
    # scope 'daily' dgn ref_key sama boleh (unik per pasangan).
    async with db.pool().connection() as conn:
        await conn.execute(
            "INSERT INTO llm_introspections (scope, ref_key) VALUES ('daily', %s)",
            (key,))


async def test_l012_llm_introspections_append_only():
    """Tabel append-only: UPDATE/DELETE ditolak trigger (pola order_events)."""
    key = f"t-{uuid.uuid4().hex[:12]}"
    async with db.pool().connection() as conn:
        await conn.execute(
            "INSERT INTO llm_introspections (scope, ref_key, narasi) "
            "VALUES ('trade', %s, 'awal')", (key,))
    async with db.pool().connection() as conn:
        with pytest.raises(psycopg.errors.RaiseException, match="append-only"):
            await conn.execute(
                "UPDATE llm_introspections SET narasi = 'diedit' WHERE ref_key = %s",
                (key,))
    async with db.pool().connection() as conn:
        with pytest.raises(psycopg.errors.RaiseException, match="append-only"):
            await conn.execute(
                "DELETE FROM llm_introspections WHERE ref_key = %s", (key,))


async def test_l012_downgrade_upgrade():
    """DoD migrasi: downgrade l012 drop tabel; upgrade head recreasi."""
    from alembic import command

    assert await _table_exists("llm_introspections")
    command.downgrade(_alembic_cfg(), "k011")
    assert not await _table_exists("llm_introspections")
    command.upgrade(_alembic_cfg(), "head")
    assert await _table_exists("llm_introspections")
    # Head dibandingkan dengan head skrip alembic, bukan konstanta: migrasi
    # berikutnya (mis. m013 RISK-D) tidak boleh memecah test ini.
    from alembic.script import ScriptDirectory

    expected_head = ScriptDirectory.from_config(_alembic_cfg()).get_current_head()
    async with db.pool().connection() as conn:
        row = await (await conn.execute(
            "SELECT version_num FROM alembic_version")).fetchone()
    assert row["version_num"] == expected_head
    # Trigger ikut kembali setelah upgrade.
    key = f"t-{uuid.uuid4().hex[:12]}"
    async with db.pool().connection() as conn:
        await conn.execute(
            "INSERT INTO llm_introspections (scope, ref_key) VALUES ('trade', %s)",
            (key,))
        with pytest.raises(psycopg.errors.RaiseException, match="append-only"):
            await conn.execute(
                "DELETE FROM llm_introspections WHERE ref_key = %s", (key,))


def _ctx_stops(price: float = 2000.0, atr_m5: float = 2.0,
               atr_h1: float = 6.0, symbol: str = "XAUUSD") -> dict:
    """Konteks minimal dengan fakta Layer 0 untuk normalisasi SL/TP.

    Sejak commit entry_plan, _submit_decision menolak order yang SL/TP-nya
    tidak bisa divalidasi (tanpa harga/ATR = tidak bisa dinormalisasi).
    """
    return {"symbols": {}, "facts": {"symbols": {symbol: {
        "price": price,
        "timeframes": {"M5": {"atr14": atr_m5}, "H1": {"atr14": atr_h1}},
        "structure": {"sr_nearest_multi_tf": {"support": price - 12,
                                              "resistance": price + 20}},
    }}}}
