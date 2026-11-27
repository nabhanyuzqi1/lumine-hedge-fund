"""Role guard test (temuan F-1 QA t_f2llm3): role agent tidak bisa ubah controls.

t_4651d431: role 'qa' (driver QA latensi) diizinkan KHUSUS untuk flatten
kill-switch (dengan 2FA), karena driver QA wajib login pakai user QA khusus.
Keputusan owner 25 Nov 2026 (t_7c070c31): release kill-switch TIDAK lagi
diizinkan untuk role qa -- hanya admin/owner ber-2FA via dashboard.
"""
from __future__ import annotations

import time

import pytest
from httpx import AsyncClient, ASGITransport

from app import auth, db, kill_switch
from app.main import app


async def _agent_client(user):
    """Client ter-login sebagai role 'agent' (service fund2-llm-agent)."""
    async with db.pool().connection() as conn:
        row = await conn.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (%s, %s, 'agent') RETURNING id",
            ("svc-llm-agent", auth.hash_password("agentpass")),
        )
        created = await row.fetchone()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post("/auth/login", json={"username": "svc-llm-agent", "password": "agentpass"})
        assert resp.status_code == 200, resp.text
        csrf = resp.json()["csrf_token"]
        c.headers["x-csrf-token"] = csrf
        yield c


@pytest.fixture
async def agent_client(user):
    async for c in _agent_client(user):
        yield c


async def _role_client(username: str, role: str, password: str):
    """Client ter-login sebagai role berapa pun (pola _agent_client)."""
    async with db.pool().connection() as conn:
        row = await conn.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (%s, %s, %s) RETURNING id",
            (username, auth.hash_password(password), role),
        )
        await row.fetchone()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post("/auth/login", json={"username": username, "password": password})
        assert resp.status_code == 200, resp.text
        c.headers["x-csrf-token"] = resp.json()["csrf_token"]
        yield c


@pytest.fixture
async def qa_client(user):
    """Client ter-login sebagai role 'qa' (driver QA latensi, t_4651d431)."""
    async for c in _role_client("svc-qa-driver", "qa", "qapass"):
        yield c


@pytest.fixture
async def qa_client_2fa(qa_client):
    """Client role 'qa' dengan 2FA terdaftar + challenge aktif."""
    from app import totp

    secret = (await qa_client.post("/auth/2fa/setup")).json()["secret"]
    r = await qa_client.post("/auth/2fa/enable", json={"code": totp.totp_at(secret)})
    assert r.status_code == 200, r.text
    # challenge pakai time-step BERIKUTNYA (anti-replay counter, pola client_2fa)
    r = await qa_client.post(
        "/auth/2fa/challenge", json={"code": totp.totp_at(secret, time.time() + 30)})
    assert r.status_code == 200, r.text
    yield qa_client


async def _insert_position(ticket, *, side="BUY", volume=0.10, profit=0.0, status="OPEN"):
    async with db.pool().connection() as conn:
        await conn.execute(
            """
            INSERT INTO positions (ticket, symbol, side, volume, open_price, profit, status)
            VALUES (%s, 'XAUUSD', %s, %s, 2000.0, %s, %s)
            """,
            (ticket, side, volume, profit, status),
        )


async def test_agent_cannot_activate_kill_switch(agent_client):
    resp = await agent_client.post("/kill-switch", json={"mode": "STOP_NEW_ORDERS"})
    assert resp.status_code == 403, resp.text


async def test_agent_cannot_release_kill_switch(agent_client):
    resp = await agent_client.post("/kill-switch/release", json={"checklist_ack": True})
    assert resp.status_code == 403


async def test_agent_cannot_flatten(agent_client):
    resp = await agent_client.post("/kill-switch/flatten", json={"confirm": True})
    assert resp.status_code == 403


async def test_agent_cannot_update_triggers(agent_client):
    resp = await agent_client.put("/kill-switch/triggers", json={"daily_drawdown_pct": 99.0})
    assert resp.status_code == 403


async def test_agent_cannot_change_strategy_mode(agent_client):
    resp = await agent_client.post("/strategies/london_breakout/mode", json={"mode": "live"})
    assert resp.status_code == 403


async def test_agent_can_read_kill_switch(agent_client):
    resp = await agent_client.get("/kill-switch")
    assert resp.status_code == 200, resp.text


async def test_agent_can_read_positions(agent_client):
    resp = await agent_client.get("/positions")
    assert resp.status_code == 200


async def test_agent_can_post_order_goes_through_risk_gate(agent_client, tick_2000):
    """Role agent boleh POST /orders (tetap melewati risk gate penuh)."""
    resp = await agent_client.post(
        "/orders",
        json={"symbol": "XAUUSD", "side": "BUY", "volume": 0.01, "sl": 1998.0, "tp": 2005.0},
    )
    assert resp.status_code == 201, resp.text
    order = resp.json()
    assert order["status"] == "RISK_PASS"
    # audit keputusan menempel pada order (G1 butir 3)
    resp = await agent_client.post(
        "/llm-agent/decisions",
        json={
            "symbol": "XAUUSD",
            "kind": "order",
            "reasoning": "uji role agent",
            "confidence": 0.8,
            "model": "test-model",
            "prompt_version": "1.0.0",
            "cycle_id": "test-cycle-001",
            "order_id": order["id"],
        },
    )
    assert resp.status_code == 200, resp.text


async def test_agent_decision_hold_recorded(agent_client):
    """HOLD tercatat di order_events tanpa order_id (G1 butir 3)."""
    resp = await agent_client.post(
        "/llm-agent/decisions",
        json={
            "symbol": "BTCUSD",
            "kind": "hold",
            "reasoning": "spread lebar",
            "confidence": 0.2,
            "model": "test-model",
            "prompt_version": "1.0.0",
            "cycle_id": "test-cycle-002",
        },
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["to_status"] == "AGENT_HOLD"
    # baca order_events via /orders?orders... verify through DB
    from app import db
    async with db.pool().connection() as conn:
        row = await (await conn.execute(
            "SELECT to_status, decision FROM order_events WHERE to_status='AGENT_HOLD' ORDER BY id DESC LIMIT 1"
        )).fetchone()
    assert row is not None
    assert row["decision"]["kind"] == "hold"
    assert row["decision"]["model"] == "test-model"
    assert row["decision"]["prompt_version"] == "1.0.0"


async def test_agent_decision_order_requires_order_id(agent_client):
    resp = await agent_client.post(
        "/llm-agent/decisions",
        json={"kind": "order", "reasoning": "x", "confidence": 0.5,
              "model": "m", "prompt_version": "1.0.0", "cycle_id": "test-cycle-003"},
    )
    assert resp.status_code == 422


async def test_agent_decision_hold_rejects_order_id(agent_client):
    resp = await agent_client.post(
        "/llm-agent/decisions",
        json={"kind": "hold", "reasoning": "x", "confidence": 0.5,
              "model": "m", "prompt_version": "1.0.0", "cycle_id": "test-cycle-004",
              "order_id": "00000000-0000-0000-0000-000000000000"},
    )
    assert resp.status_code == 422


async def test_agent_decision_invalid_kind(agent_client):
    resp = await agent_client.post(
        "/llm-agent/decisions",
        json={"kind": "boom", "reasoning": "x", "confidence": 0.5,
              "model": "m", "prompt_version": "1.0.0", "cycle_id": "test-cycle-005"},
    )
    assert resp.status_code == 422


async def test_admin_can_still_activate_kill_switch(client):
    """Regresi: role admin (owner/dashboard) tetap bisa kill-switch."""
    resp = await client.post("/kill-switch", json={"mode": "STOP_NEW_ORDERS", "reason": "test"})
    assert resp.status_code == 200, resp.text
    assert (await client.get("/kill-switch")).json()["state"]["active"] is True


# ------------------------------------------------------- role qa (t_4651d431)

async def test_qa_cannot_activate_kill_switch(qa_client):
    """Endpoint kontrol lain tetap admin-only untuk role qa."""
    resp = await qa_client.post("/kill-switch", json={"mode": "STOP_NEW_ORDERS"})
    assert resp.status_code == 403, resp.text


async def test_qa_cannot_update_triggers(qa_client):
    resp = await qa_client.put("/kill-switch/triggers", json={"daily_drawdown_pct": 99.0})
    assert resp.status_code == 403, resp.text


async def test_qa_can_flatten_with_2fa(qa_client_2fa):
    """Driver QA (role 'qa') boleh flatten dengan 2FA, dan order CLOSE-nya
    mencatat username QA di payload event RECEIVED (bahan exclude anomaly)."""
    await _insert_position(601, profit=1.0)
    resp = await qa_client_2fa.post("/kill-switch/flatten", json={"confirm": True})
    assert resp.status_code == 200, resp.text
    assert resp.json()["flatten"]["requested"] == 1
    async with db.pool().connection() as conn:
        row = await (await conn.execute(
            "SELECT payload FROM order_events WHERE to_status = 'RECEIVED' "
            "ORDER BY id DESC LIMIT 1"
        )).fetchone()
    assert row is not None
    assert row["payload"]["username"] == "svc-qa-driver"


async def test_qa_cannot_release_kill_switch(qa_client_2fa):
    """Driver QA dilarang me-release kill-switch (keputusan owner 25 Nov 2026).

    Role 'qa' + 2FA dulu diizinkan me-release; akibatnya driver me-release halt
    tiap ~2 menit -> flapping 34x ACTIVATE / 33x RELEASE + spam Telegram
    (kartu t_7c070c31). Kini release hanya admin/owner ber-2FA via dashboard.
    """
    await kill_switch.activate("STOP_NEW_ORDERS", reason="uji qa",
                               source="test", actor="tester")
    resp = await qa_client_2fa.post("/kill-switch/release", json={"checklist_ack": True})
    assert resp.status_code == 403, resp.text
    assert (await kill_switch.get_state())["active"] is True
