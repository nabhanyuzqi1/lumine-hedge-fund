"""Endpoint baca halaman admin Guardrail Risiko (kartu t_2d1f6d33).

Halaman UI admin butuh dua bacaan yang belum ada:
  - GET /admin/risk-settings  : nilai guardrail inti AKTIF + rentang validasi
  - GET /admin/settings-audit : riwayat perubahan dari trigger settings_audit

Plus satu penguatan: PUT /kill-switch/triggers menerima `password` dan
menolak perubahan bila password salah (UI admin selalu mengirimnya).

Semua read-only kecuali poin ketiga; tidak ada default yang diubah.
"""
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app import db
from app.main import app


@pytest.mark.asyncio
async def test_read_risk_settings_active_values(client):
    """Nilai yang dikembalikan = yang benar-benar ditegakkan (tabel settings)."""
    await db.set_setting("max_spread", 0.42)
    r = await client.get("/admin/risk-settings")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["values"]["max_spread"] == 0.42
    assert set(body["values"]) == {
        "max_volume", "max_orders_per_min", "max_daily_drawdown",
        "max_spread", "max_tick_age_s",
    }
    # Rentang kewajaran ikut dikirim supaya form tidak menebak batas.
    assert body["ranges"]["max_volume"] == {"min": 0.01, "max": 100.0}
    assert body["ranges"]["max_orders_per_min"] == {"min": 1, "max": 600}
    # Defaults hanya referensi; tidak menimpa nilai aktif.
    assert body["defaults"]["max_volume"] == 0.10
    assert body["owner_decision"] == "KEPUTUSAN_OWNER.md §I"


@pytest.mark.asyncio
async def test_read_risk_settings_requires_admin(client):
    """Tanpa sesi: 401. Sesi role non-admin ditolak 403 (require_admin)."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as anon:
        r = await anon.get("/admin/risk-settings")
    assert r.status_code == 401

    async with db.pool().connection() as conn:
        from app.auth import hash_password
        await conn.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (%s, %s, 'user')",
            ("biasa", hash_password("testpass")),
        )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        login = await c.post("/auth/login", json={"username": "biasa", "password": "testpass"})
        assert login.status_code == 200, login.text
        c.headers["x-csrf-token"] = login.json()["csrf_token"]
        r = await c.get("/admin/risk-settings")
        r2 = await c.get("/admin/settings-audit")
    assert r.status_code == 403
    assert r2.status_code == 403


@pytest.mark.asyncio
async def test_settings_audit_lists_guardrail_changes(client_2fa):
    """Simpan guardrail -> baris settings_audit (old -> new) terbaca endpoint."""
    before = (await db.get_settings())["max_tick_age_s"]
    r = await client_2fa.put(
        "/admin/risk-settings", json={"password": "testpass", "max_tick_age_s": 2.5})
    assert r.status_code == 200, r.text

    r = await client_2fa.get("/admin/settings-audit?limit=20")
    assert r.status_code == 200, r.text
    body = r.json()
    assert "max_tick_age_s" in body["keys"]
    rows = [x for x in body["rows"] if x["key"] == "max_tick_age_s"]
    assert rows, "perubahan guardrail wajib muncul di settings_audit"
    assert rows[0]["new_value"] == 2.5
    assert rows[0]["old_value"] == before
    assert rows[0]["changed_by"] == "tester", \
        "aktor perubahan harus username admin, bukan role koneksi DB"


@pytest.mark.asyncio
async def test_settings_audit_limit_capped(client):
    r = await client.get("/admin/settings-audit?limit=9999")
    assert r.status_code == 200
    # Tidak ada error; endpoint membatasi sendiri ke 200 (tidak membocorkan
    # seluruh riwayat sekaligus). Bentuk respons tetap sama.
    assert set(r.json()) == {"keys", "rows"}


@pytest.mark.asyncio
async def test_triggers_wrong_password_rejected(client_2fa):
    """Password salah -> 403, nilai TIDAK berubah, penolakan ter-audit."""
    triggers_before = (await client_2fa.get("/kill-switch")).json()["triggers"]
    r = await client_2fa.put(
        "/kill-switch/triggers",
        json={"password": "salah", "ea_offline_halt_seconds": 45.0},
    )
    assert r.status_code == 403, r.text
    assert r.json()["detail"] == "password salah"
    triggers_after = (await client_2fa.get("/kill-switch")).json()["triggers"]
    assert triggers_after["ea_offline_halt_seconds"] == triggers_before["ea_offline_halt_seconds"]
    async with db.pool().connection() as conn:
        rows = await (await conn.execute(
            "select count(*) as n from audit_log where action = 'RISK_SETTINGS_REJECTED' "
            "and object = 'kill_switch_triggers'"
        )).fetchall()
    assert rows[0]["n"] >= 1


@pytest.mark.asyncio
async def test_triggers_with_password_saved_and_audited(client_2fa):
    """Password benar -> tersimpan + settings_audit mencatat kill_switch_triggers."""
    r = await client_2fa.put(
        "/kill-switch/triggers",
        json={"password": "testpass", "ea_offline_halt_seconds": 45.0},
    )
    assert r.status_code == 200, r.text
    assert r.json()["triggers"]["ea_offline_halt_seconds"] == 45.0
    async with db.pool().connection() as conn:
        rows = await (await conn.execute(
            "select old_value, new_value from settings_audit "
            "where key = 'kill_switch_triggers' order by id desc limit 1"
        )).fetchall()
    assert rows, "perubahan auto-trigger wajib tercatat di settings_audit"
    assert rows[0]["new_value"]["ea_offline_halt_seconds"] == 45.0
    # A12 (6 s, tanda offline) tidak ikut berubah.
    assert rows[0]["new_value"]["ea_offline_seconds"] == 6.0


@pytest.mark.asyncio
async def test_triggers_without_password_rejected(client_2fa):
    """kartu t_dc104883: password WAJIB di jalur Ops ini, seperti jalur admin.

    Kompatibilitas lama (2FA saja, tanpa password) dihapus: endpoint ini hanya
    menerima sesi user, dan sesi user tidak boleh menulis guardrail tanpa
    verifikasi ulang password. Tanpa password -> 422, tidak ada yang berubah.
    """
    triggers_before = (await client_2fa.get("/kill-switch")).json()["triggers"]
    r = await client_2fa.put(
        "/kill-switch/triggers", json={"check_interval_seconds": 7.0})
    assert r.status_code == 422, r.text
    assert "password" in r.text
    triggers_after = (await client_2fa.get("/kill-switch")).json()["triggers"]
    assert triggers_after == triggers_before


@pytest.mark.asyncio
async def test_triggers_empty_body_rejected(client_2fa):
    r = await client_2fa.put("/kill-switch/triggers", json={"password": "testpass"})
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_triggers_password_requires_2fa(client):
    """Password benar pun tidak cukup tanpa step-up 2FA sesi."""
    r = await client.put(
        "/kill-switch/triggers", json={"password": "testpass", "ea_offline_halt_seconds": 45.0})
    assert r.status_code in (401, 403)
