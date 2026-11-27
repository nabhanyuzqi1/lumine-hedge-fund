"""Audit `/llm-agent/decisions` wajib menyimpan evidence per peran (t_e086d30a).

Temuan verifikasi 26 Nov 2026 08:46 WIB: siklus nyata (cycle 9f5f2d0b) mengirim
`evidence` + `evidence_missing` di body POST, tetapi baris `order_events`
(`AGENT_HOLD`) tidak memuat keduanya, karena `AgentDecisionBody` tidak punya
field itu sehingga Pydantic membuangnya diam-diam.

Akibatnya audit tidak bisa membuktikan keputusan mana yang didukung 4 specialist
dan mana yang berjalan terdegradasi (mis. macro timeout) — justru bukti yang
dipakai untuk menilai apakah synthesizer memutuskan di atas angka null.

Tes ini menguji PERSISTENSI (baca ulang baris DB), bukan hanya isi body klien.
"""
from __future__ import annotations

import json

import pytest
from httpx import ASGITransport, AsyncClient

from app import auth, db
from app.llm_agent_loop import PROMPT_VERSION
from app.main import app


@pytest.fixture
async def agent_client(user):
    """Client ter-login sebagai role 'agent' (service fund2-llm-agent)."""
    async with db.pool().connection() as conn:
        await conn.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (%s, %s, 'agent')",
            ("svc-llm-agent-audit", auth.hash_password("***")),
        )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post("/auth/login",
                            json={"username": "svc-llm-agent-audit", "password": "***"})
        assert resp.status_code == 200, resp.text
        c.headers["x-csrf-token"] = resp.json()["csrf_token"]
        yield c


def _body(**overrides) -> dict:
    body = {
        "symbol": "XAUUSD",
        "kind": "hold",
        "reasoning": "R:R 0.79 di bawah syarat 1.5, entry 3556.31 ditolak",
        "confidence": 0.55,
        "model": "lucif",
        "prompt_version": PROMPT_VERSION,
        "cycle_id": "cycle-audit-evidence-001",
    }
    body.update(overrides)
    return body


async def _last_decision(cycle_id: str) -> dict:
    async with db.pool().connection() as conn:
        row = await (await conn.execute(
            "SELECT decision FROM order_events WHERE left(to_status, 6) = 'AGENT_' "
            "AND decision->>'cycle_id' = %s ORDER BY id DESC LIMIT 1",
            (cycle_id,),
        )).fetchone()
    assert row is not None, "baris order_events tidak tercatat"
    decision = row["decision"]
    return decision if isinstance(decision, dict) else json.loads(decision)


async def test_decision_audit_persists_evidence(agent_client):
    evidence = {
        "technical": {"state": "ok", "model": "lucif-claude", "latency_ms": 3412,
                      "error": None},
        "macro": {"state": "timeout", "model": "lucif-flash", "latency_ms": 45000,
                  "error": "timeout > 45s"},
        "sentiment": {"state": "ok", "model": "lucif-flash", "latency_ms": 3426,
                      "error": None},
        "portfolio": {"state": "ok", "model": "lucif-flash", "latency_ms": 2949,
                      "error": None},
    }
    r = await agent_client.post("/llm-agent/decisions", json=_body(
        cycle_id="cycle-audit-evidence-001",
        evidence=evidence,
        evidence_missing=["macro"],
    ))
    assert r.status_code == 200, r.text
    assert r.json()["to_status"] == "AGENT_HOLD"

    stored = await _last_decision("cycle-audit-evidence-001")
    assert set(stored["evidence"]) == {"technical", "macro", "sentiment", "portfolio"}
    assert stored["evidence"]["macro"]["state"] == "timeout"
    assert stored["evidence"]["technical"]["model"] == "lucif-claude"
    assert stored["evidence_missing"] == ["macro"]


async def test_decision_audit_without_evidence_stays_clean(agent_client):
    """Keputusan non-pipeline (mis. kind=invalid) tidak wajib membawa evidence."""
    r = await agent_client.post("/llm-agent/decisions", json=_body(
        cycle_id="cycle-audit-evidence-002",
        kind="invalid",
        reasoning="Snapshot tidak lengkap, tidak ada order dikirim",
        evidence=None,
    ))
    assert r.status_code == 200, r.text
    stored = await _last_decision("cycle-audit-evidence-002")
    assert "evidence" not in stored
    assert "evidence_missing" not in stored
    assert stored["symbol"] == "XAUUSD"
