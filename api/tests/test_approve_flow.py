"""Alur approve usulan self-improve -> deploy flag enabled (PRD v2.1 P4).

End-to-end dua kanal (tanpa jaringan):
  laporan siklus mingguan -> owner approve via UI/HTTP atau Telegram ->
  deploy: strategies.enabled=true, strategy_approvals OWNER_APPROVE ->
  DEPLOY, deployment_records, settings params ter-audit.

Garis merah (DoD kartu t_f2p4a3): flag `enabled` dan settings param HANYA
berubah lewat decide() owner. HTTP: admin + CSRF + 2FA step-up + username
== settings.owner_username. Telegram: hanya TELEGRAM_OWNER_ID. Role
user/agent, admin non-owner, owner tanpa 2FA, dan pengirim Telegram asing
semuanya ditolak dan flag tidak berubah.
"""
from __future__ import annotations

import json
import time

import pytest
from httpx import ASGITransport, AsyncClient

from app import db, totp
from app.auth import hash_password
from app.main import app
from app.telegram_bot import handle_command

OWNER_TG_ID = 12345
STRANGER_TG_ID = 99999


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def _exec(query, params=()):
    async with db.pool().connection() as conn:
        await conn.execute(query, params)


async def _seed_proposal(proposal_id: str, *, strategy_id: str = "mean_reversion",
                         version: str = "1.2.0") -> None:
    await _exec(
        """INSERT INTO improvement_proposals
               (id, week, title, hypothesis, change, verdict, evidence)
           VALUES (%s, '2026-W48', 'usulan uji alur approve', 'hipotesis uji',
                   %s, 'LULUS', '{}')""",
        (proposal_id,
         json.dumps({"strategy_id": strategy_id, "version": version,
                     "symbol": "XAUUSD", "tf": "M5",
                     "params": {"num_std": 3.0}, "mode": "paper"})),
    )


async def _enabled(strategy_id: str = "mean_reversion"):
    async with db.pool().connection() as conn:
        row = await (await conn.execute(
            "SELECT enabled FROM strategies WHERE strategy_id = %s",
            (strategy_id,))).fetchone()
    return bool(row["enabled"]) if row else None


async def _proposal_status(proposal_id: str) -> str:
    async with db.pool().connection() as conn:
        row = await (await conn.execute(
            "SELECT status FROM improvement_proposals WHERE id = %s",
            (proposal_id,))).fetchone()
    return row["status"] if row else "(tidak ada)"


async def _make_user(username: str, password: str, role: str) -> None:
    await _exec(
        "INSERT INTO users (username, password_hash, role) VALUES (%s, %s, %s)",
        (username, hash_password(password), role))


async def _login(username: str, password: str) -> AsyncClient:
    c = _client()
    r = await c.post("/auth/login", json={"username": username,
                                          "password": password})
    assert r.status_code == 200, r.text
    c.headers["x-csrf-token"] = r.json()["csrf_token"]
    return c


async def _2fa_client(username: str, password: str) -> AsyncClient:
    """Client login + 2FA terdaftar + challenge segar (jendela terbuka)."""
    c = await _login(username, password)
    secret = (await c.post("/auth/2fa/setup")).json()["secret"]
    r = await c.post("/auth/2fa/enable", json={"code": totp.totp_at(secret)})
    assert r.status_code == 200, r.text
    # challenge pakai time-step berikutnya (anti-replay counter, lihat conftest)
    r = await c.post("/auth/2fa/challenge",
                     json={"code": totp.totp_at(secret, time.time() + 30)})
    assert r.status_code == 200, r.text
    return c


@pytest.fixture(autouse=True)
async def approve_env(_clean_db, monkeypatch):
    """Owner username = 'tester' (fixture user conftest) + TG owner id uji.

    Teardown menghapus 'owner_username' lagi: tabel settings tidak di-truncate
    antar test, dan test lain (test_self_improve) mengandalkan default 'admin'.
    """
    await db.set_setting("owner_username", "tester")
    monkeypatch.setattr("app.config.TELEGRAM_BOT_TOKEN", "test-token")
    monkeypatch.setattr("app.config.TELEGRAM_OWNER_ID", str(OWNER_TG_ID))
    yield
    await _exec("DELETE FROM settings WHERE key = 'owner_username'")


# ── UI/HTTP: owner approve -> deploy flag enabled ---------------------------
async def test_http_e2e_owner_approve_lalu_deploy_flag_enabled(client_2fa):
    await _seed_proposal("p4-http-1")
    assert await _enabled() is None  # strategi belum terdaftar/enabled

    listed = await client_2fa.get("/improve/proposals")
    assert listed.status_code == 200, listed.text
    assert any(p["id"] == "p4-http-1" and p["status"] == "PROPOSED"
               for p in listed.json()["proposals"])

    decided = await client_2fa.post(
        "/improve/proposals/p4-http-1/decision",
        json={"decision": "APPROVED", "rationale": "lulus kriteria + cek manual"})
    assert decided.status_code == 200, decided.text
    body = decided.json()
    assert body["status"] == "DEPLOYED"
    assert body["strategy"] == "mean_reversion" and body["version"] == "1.2.0"

    assert await _enabled() is True  # flag enabled kini true
    assert await _proposal_status("p4-http-1") == "DEPLOYED"
    async with db.pool().connection() as conn:
        version = await (await conn.execute(
            "SELECT id FROM strategy_versions WHERE strategy_id = 'mean_reversion' "
            "AND version = '1.2.0'")).fetchone()
        assert version is not None
        stages = [r["stage"] for r in await (await conn.execute(
            "SELECT stage FROM strategy_approvals WHERE strategy_version_id = %s "
            "ORDER BY id", (version["id"],))).fetchall()]
        dep = await (await conn.execute(
            "SELECT deployed_by FROM deployment_records "
            "WHERE service = 'fund2-strategy-mean_reversion'")).fetchone()
        params = await (await conn.execute(
            "SELECT value FROM settings WHERE key = 'strategy_params_mean_reversion'"
        )).fetchone()
    assert stages == ["OWNER_APPROVE", "DEPLOY"]
    assert dep["deployed_by"] == "tester"
    assert params["value"]["num_std"] == 3.0

    # keputusan kedua ditolak (append-only: satu usulan satu keputusan)
    again = await client_2fa.post(
        "/improve/proposals/p4-http-1/decision", json={"decision": "REJECTED"})
    assert again.status_code == 409, again.text
    assert await _enabled() is True  # flag tidak berubah oleh keputusan kedua


# ── Telegram: owner approve -> deploy; asing diabaikan ----------------------
async def test_telegram_e2e_owner_approve_lalu_deploy_flag_enabled():
    await _seed_proposal("p4-tg-1")

    listed = await handle_command("/proposals", chat_id=1, sender_id=OWNER_TG_ID)
    assert listed is not None and "p4-tg-1" in listed and "PROPOSED" in listed

    reply = await handle_command("/approve p4-tg-1 setuju via telegram",
                                 chat_id=1, sender_id=OWNER_TG_ID)
    assert reply is not None and "APPROVED" in reply and "DEPLOYED" in reply
    assert await _enabled() is True
    assert await _proposal_status("p4-tg-1") == "DEPLOYED"
    async with db.pool().connection() as conn:
        reviewer = await (await conn.execute(
            "SELECT reviewer FROM improvement_proposals WHERE id = 'p4-tg-1'"
        )).fetchone()
        stages = [r["stage"] for r in await (await conn.execute(
            "SELECT stage FROM strategy_approvals ORDER BY id")).fetchall()]
    assert reviewer["reviewer"] == f"tg:{OWNER_TG_ID}"
    assert stages == ["OWNER_APPROVE", "DEPLOY"]


async def test_telegram_non_owner_diabaikan_flag_tetap():
    await _seed_proposal("p4-tg-2")
    for text in ("/approve p4-tg-2", "/reject p4-tg-2", "/proposals"):
        assert await handle_command(text, chat_id=1,
                                    sender_id=STRANGER_TG_ID) is None
    assert await _proposal_status("p4-tg-2") == "PROPOSED"
    assert await _enabled() is None
    async with db.pool().connection() as conn:
        n = (await (await conn.execute(
            "SELECT count(*) AS n FROM strategy_approvals")).fetchone())["n"]
    assert n == 0


async def test_telegram_reject_tidak_mengubah_flag_enabled():
    await _seed_proposal("p4-tg-3")
    reply = await handle_command("/reject p4-tg-3 evidence tidak cukup",
                                 chat_id=1, sender_id=OWNER_TG_ID)
    assert reply is not None and "REJECTED" in reply
    assert await _proposal_status("p4-tg-3") == "REJECTED"
    assert await _enabled() is None


async def test_telegram_approve_tidak_dikenal_dan_sudah_diputuskan():
    await _seed_proposal("p4-tg-4")
    reply = await handle_command("/approve tidak-ada", chat_id=1,
                                 sender_id=OWNER_TG_ID)
    assert reply is not None and "tidak ditemukan" in reply
    assert await _proposal_status("p4-tg-4") == "PROPOSED"

    first = await handle_command("/approve p4-tg-4", chat_id=1,
                                 sender_id=OWNER_TG_ID)
    assert first is not None and "DEPLOYED" in first
    again = await handle_command("/approve p4-tg-4", chat_id=1,
                                 sender_id=OWNER_TG_ID)
    assert again is not None and "sudah diputuskan" in again
    assert await _enabled() is True  # deploy pertama tetap berlaku


async def test_telegram_tanpa_argumen_dan_owner_belum_diset():
    await _seed_proposal("p4-tg-5")
    reply = await handle_command("/approve", chat_id=1, sender_id=OWNER_TG_ID)
    assert reply is not None and "Gunakan:" in reply
    assert await _proposal_status("p4-tg-5") == "PROPOSED"


# ── non-owner tidak bisa mengubah flag enabled (semua lapisan HTTP) ---------
async def test_http_non_owner_dan_tanpa_2fa_ditolak_flag_tetap(client, user):
    await _seed_proposal("p4-sec-1")

    # 1) anonim tanpa sesi -> 401
    async with _client() as anon:
        r = await anon.post("/improve/proposals/p4-sec-1/decision",
                            json={"decision": "APPROVED"})
        assert r.status_code == 401, r.text
        r = await anon.get("/improve/proposals")
        assert r.status_code == 401, r.text

    # 2) role 'user' dengan sesi + CSRF + 2FA sah -> 403 (bukan owner/admin)
    await _make_user("budi", "budipass", "user")
    c = await _2fa_client("budi", "budipass")
    r = await c.post("/improve/proposals/p4-sec-1/decision",
                     json={"decision": "APPROVED"})
    assert r.status_code == 403, r.text
    # kontrol mode strategi juga admin-only (PRD v2.2 §18)
    r = await c.post("/strategies/mean_reversion/mode", json={"mode": "live"})
    assert r.status_code == 403, r.text
    await c.aclose()

    # 3) role 'agent' (kredensial LLM read-only) + 2FA sah -> 403
    await _make_user("f2llm", "agentpass", "agent")
    c = await _2fa_client("f2llm", "agentpass")
    r = await c.post("/improve/proposals/p4-sec-1/decision",
                     json={"decision": "APPROVED"})
    assert r.status_code == 403, r.text
    await c.aclose()

    # 4) admin lain (bukan owner_username) + 2FA sah -> 403.
    #    Catatan desain: endpoint mode strategi memang dibuka untuk role
    #    admin (PRD v2.2 §18), tapi flag deploy `enabled` TIDAK bisa diubah
    #    admin lain - hanya lewat keputusan owner yang tercatat.
    await _make_user("admin2", "admin2pass", "admin")
    c = await _2fa_client("admin2", "admin2pass")
    r = await c.post("/improve/proposals/p4-sec-1/decision",
                     json={"decision": "APPROVED"})
    assert r.status_code == 403, r.text
    await c.aclose()

    # 5) owner sendiri tanpa step-up 2FA -> 403
    r = await client.post("/improve/proposals/p4-sec-1/decision",
                          json={"decision": "APPROVED"})
    assert r.status_code == 403, r.text

    # flag enabled tetap tidak pernah berubah, tidak ada jejak approve
    assert await _proposal_status("p4-sec-1") == "PROPOSED"
    assert await _enabled() is None
    async with db.pool().connection() as conn:
        n_approvals = (await (await conn.execute(
            "SELECT count(*) AS n FROM strategy_approvals")).fetchone())["n"]
        n_deploys = (await (await conn.execute(
            "SELECT count(*) AS n FROM deployment_records")).fetchone())["n"]
    assert n_approvals == 0 and n_deploys == 0
