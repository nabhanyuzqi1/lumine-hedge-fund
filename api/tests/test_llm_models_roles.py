"""Override model PER PERAN lewat API + evidence siklus terakhir (t_0ff73490).

Yang dijaga di sini:
- `PUT /llm-agent/models` menyimpan dict `roles` apa adanya (bukan dibuang),
  dan `GET` mengembalikan `roles_saved` yang sama.
- String kosong menghapus override (kembali ke bawaan sistem / global).
- Peran tak dikenal dan nama model tidak valid ditolak 422, bukan diabaikan.
- `last_cycle` diambil dari evidence AGENT_EVIDENCE (role + model yang
  BENAR-BENAR dipakai), sehingga UI bisa membedakan pilihan dari kenyataan.
"""
from __future__ import annotations

import json

import pytest

from app import db, llm_models


@pytest.fixture(autouse=True)
async def _reset_llm_models(_clean_db):
    """Settings `llm_models` tidak ikut TRUNCATE conftest: reset eksplisit.

    Tanpa ini override dari test sebelumnya bocor ke test berikutnya dan
    kegagalan terlihat seperti bug (assert {'macro': ...} == {}).
    """
    async def _clear():
        async with db.pool().connection() as conn:
            await conn.execute("DELETE FROM settings WHERE key = %s", (llm_models.SETTING_KEY,))

    await _clear()
    yield
    await _clear()


async def _get_models(client):
    r = await client.get("/llm-agent/models")
    assert r.status_code == 200, r.text
    return r.json()


async def _put_models(client, body: dict):
    return await client.put("/llm-agent/models", json=body)


async def _insert_evidence(cycle_id: str, role: str, model: str, state: str = "ok") -> None:
    decision = {
        "kind": "evidence",
        "reasoning": f"evidence {role}",
        "confidence": 0.5,
        "model": model,
        "prompt_version": "2.1.0-evidence",
        "role": role,
        "state": state,
        "symbol": "XAUUSD",
        "latency_ms": 1234,
    }
    async with db.pool().connection() as conn:
        await conn.execute(
            """
            INSERT INTO order_events (order_id, from_status, to_status, payload, decision)
            VALUES (NULL, NULL, 'AGENT_EVIDENCE', %s, %s)
            """,
            (json.dumps({"cycle_id": cycle_id, "role": role}), json.dumps(decision)),
        )


async def test_get_models_exposes_roles_contract(client):
    body = await _get_models(client)
    assert body["role_keys"] == list(llm_models.ROLE_KEYS)
    assert body["role_keys"] == ["technical", "macro", "sentiment", "portfolio"]
    # Belum ada override tersimpan di DB test yang bersih.
    assert body["roles_saved"] == {}
    # Bawaan sistem: technical sudah punya rekomendasi model, peran lain tidak.
    assert body["role_defaults"] == {"technical": "lucif-claude"}
    assert body["effective"]["roles"]["technical"] == "lucif-claude"
    assert "macro" not in body["role_defaults"]
    assert body["last_cycle"] is None


async def test_put_roles_persisted_and_read_back(client_2fa):
    r = await _put_models(client_2fa, {"roles": {"technical": "lucif-claude"}})
    assert r.status_code == 200, r.text
    assert r.json()["roles_saved"] == {"technical": "lucif-claude"}

    body = await _get_models(client_2fa)
    assert body["roles_saved"] == {"technical": "lucif-claude"}
    assert body["effective"]["roles"]["technical"] == "lucif-claude"
    # Peran lain tetap ikut model specialist global.
    assert body["effective"]["specialist"] == "lucif-flash"
    assert "macro" not in body["roles_saved"]
    assert "macro" not in body["effective"]["roles"]


async def test_put_roles_keeps_global_settings(client_2fa):
    r = await _put_models(
        client_2fa,
        {
            "specialist": "lucif",
            "synth": "lucif-claude",
            "fallback": "lucif-flash",
            "roles": {"macro": "lucif-claude"},
        },
    )
    assert r.status_code == 200, r.text
    body = await _get_models(client_2fa)
    assert body["effective"]["specialist"] == "lucif"
    assert body["effective"]["synth"] == "lucif-claude"
    assert body["roles_saved"] == {"macro": "lucif-claude"}
    assert body["effective"]["roles"]["macro"] == "lucif-claude"


async def test_empty_string_removes_override(client_2fa):
    r = await _put_models(client_2fa, {"roles": {"technical": "lucif-claude"}})
    assert r.status_code == 200, r.text
    r = await _put_models(client_2fa, {"roles": {"technical": ""}})
    assert r.status_code == 200, r.text
    assert r.json()["roles_saved"] == {}

    body = await _get_models(client_2fa)
    assert body["roles_saved"] == {}
    # technical kembali ke bawaan sistem (bukan hilang sama sekali).
    assert body["effective"]["roles"]["technical"] == llm_models.DEFAULT_ROLE_MODELS["technical"]


async def test_unknown_role_rejected(client_2fa):
    r = await _put_models(client_2fa, {"roles": {"technikal": "lucif-claude"}})
    assert r.status_code == 422, r.text
    assert "peran tidak dikenal" in r.text


async def test_invalid_model_name_rejected(client_2fa):
    r = await _put_models(client_2fa, {"roles": {"macro": "nama model aneh!"}})
    assert r.status_code == 422, r.text
    body = await _get_models(client_2fa)
    assert body["roles_saved"] == {}


async def test_last_cycle_models_from_evidence(client):
    await _insert_evidence("cyc-roles-1", "portfolio", "lucif-flash")
    await _insert_evidence("cyc-roles-1", "technical", "lucif-claude")
    await _insert_evidence("cyc-roles-1", "macro", "lucif-flash")
    await _insert_evidence("cyc-roles-1", "sentiment", "lucif-flash")

    body = await _get_models(client)
    cycle = body["last_cycle"]
    assert cycle["cycle_id"] == "cyc-roles-1"
    assert cycle["symbol"] == "XAUUSD"
    assert cycle["roles"]["technical"]["model"] == "lucif-claude"
    assert cycle["roles"]["macro"]["model"] == "lucif-flash"
    assert cycle["roles"]["sentiment"]["model"] == "lucif-flash"
    assert cycle["roles"]["portfolio"]["model"] == "lucif-flash"
    assert cycle["roles"]["technical"]["state"] == "ok"
    assert cycle["roles"]["technical"]["latency_ms"] == 1234.0


async def test_last_cycle_uses_most_recent_cycle(client):
    await _insert_evidence("cyc-old", "technical", "lucif-flash")
    await _insert_evidence("cyc-new", "technical", "lucif-claude")
    body = await _get_models(client)
    assert body["last_cycle"]["cycle_id"] == "cyc-new"
    assert body["last_cycle"]["roles"]["technical"]["model"] == "lucif-claude"
