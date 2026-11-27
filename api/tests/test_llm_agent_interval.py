"""Interval siklus agent LLM bisa diatur owner via UI (AUDIT-E, t_bb927ec7).

Yang dijaga di sini:
- Sumber nilai: settings `llm_agent_interval_s` (kanonik) -> `llm_interval_s`
  (alias lama) -> env `LLM_INTERVAL_S` -> default 300 s, beserta `source`
  yang dilaporkan.
- Clamp: di bawah 30 s -> 30; di atas 86400 s -> 86400. Baris settings lama
  atau env yang salah ketik tidak boleh mematikan agent.
- `PUT /llm-agent/interval`: wajib step-up 2FA (tanpa 2FA -> 403), menolak
  30..86400 di luar batas dengan 422, menulis settings, dan ter-audit dua
  lapis (audit_log CONFIG_CHANGED + settings_audit trigger).
- Loop agent membaca interval TIAP siklus: mengubah settings di antara siklus
  langsung mengubah delay siklus berikutnya (hot-reload, tanpa restart).
"""
from __future__ import annotations

import asyncio
import json

import pytest

from app import config, db, guardrail_ranges as gr, llm_agent_loop, llm_introspection
from app.state_machine import fetchall, fetchone


def _no_env(monkeypatch):
    """Pastikan env LLM_INTERVAL_S tidak bocor ke test (sumber = default)."""
    monkeypatch.delenv("LLM_INTERVAL_S", raising=False)
    monkeypatch.setattr(config, "_file_env", {})


# ── sumber + clamp ─────────────────────────────────────────────────────────

def test_canonical_settings_key_wins(monkeypatch):
    _no_env(monkeypatch)
    assert gr.effective_interval({"llm_agent_interval_s": 45}) == (45.0, "settings")
    # key kanonik menang atas alias lama
    assert gr.effective_interval(
        {"llm_agent_interval_s": 60, "llm_interval_s": 900}) == (60.0, "settings")


def test_legacy_settings_key_still_readable(monkeypatch):
    _no_env(monkeypatch)
    assert gr.effective_interval({"llm_interval_s": 120}) == (120.0, "settings")


def test_absent_key_defaults_to_300(monkeypatch):
    _no_env(monkeypatch)
    assert gr.effective_interval({}) == (300.0, "default")
    # NULL/string kosong di settings berarti "tidak diatur", bukan 0 detik.
    assert gr.effective_interval({"llm_agent_interval_s": None}) == (300.0, "default")
    assert gr.effective_interval({"llm_agent_interval_s": ""}) == (300.0, "default")


def test_clamp_low_and_high(monkeypatch):
    _no_env(monkeypatch)
    assert gr.effective_interval({"llm_agent_interval_s": 29}) == (30.0, "settings")
    assert gr.effective_interval({"llm_agent_interval_s": 1}) == (30.0, "settings")
    assert gr.effective_interval({"llm_agent_interval_s": 90000}) == (86400.0, "settings")
    # nilai rusak di settings jatuh ke sumber berikutnya, bukan 0
    assert gr.effective_interval({"llm_agent_interval_s": "bukan-angka"}) == (300.0, "default")


def test_env_fallback_only_when_key_absent(monkeypatch):
    monkeypatch.setenv("LLM_INTERVAL_S", "450")
    monkeypatch.setattr(config, "_file_env", {})
    assert gr.effective_interval({}) == (450.0, "env")
    # env juga di-clamp
    monkeypatch.setenv("LLM_INTERVAL_S", "0")
    assert gr.effective_interval({}) == (30.0, "env")
    # key settings hadir -> env tidak dipakai
    monkeypatch.setenv("LLM_INTERVAL_S", "450")
    assert gr.effective_interval({"llm_agent_interval_s": 600}) == (600.0, "settings")


def test_validate_interval_rejects_out_of_range():
    assert gr.validate_interval_s(30) == 30.0
    assert gr.validate_interval_s(86400) == 86400.0
    for bad in (29, 90000, 0, -5):
        with pytest.raises(gr.GuardrailRangeError):
            gr.validate_interval_s(bad)


# ── endpoint ───────────────────────────────────────────────────────────────

async def _audit_rows():
    async with db.pool().connection() as conn:
        return await fetchall(
            conn,
            "SELECT action, object, details FROM audit_log "
            "WHERE object = 'llm_agent_interval' ORDER BY id DESC",
        )


async def test_put_interval_requires_2fa(client):
    """Admin tanpa step-up 2FA ditolak 403 dan tidak ada yang tertulis."""
    r = await client.put("/llm-agent/interval", json={"interval_s": 600})
    assert r.status_code == 403, r.text
    settings = await db.get_settings()
    assert settings.get("llm_agent_interval_s") is None
    assert await _audit_rows() == []


async def test_put_interval_out_of_range_is_422(client_2fa):
    before = await db.get_settings()
    for bad in (29, 90000, 0, -10):
        r = await client_2fa.put("/llm-agent/interval", json={"interval_s": bad})
        assert r.status_code == 422, f"{bad}: {r.text}"
    after = await db.get_settings()
    assert after.get("llm_agent_interval_s") == before.get("llm_agent_interval_s")
    assert await _audit_rows() == []


async def test_put_interval_persists_and_audits(client_2fa):
    r = await client_2fa.put("/llm-agent/interval", json={"interval_s": 600})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["interval_s"] == 600
    assert body["previous"] == 300.0

    settings = await db.get_settings()
    assert settings["llm_agent_interval_s"] == 600
    # dicerminkan ke key lama supaya panel lama menampilkan angka yang sama
    assert settings["llm_interval_s"] == 600.0

    rows = await _audit_rows()
    assert rows, "perubahan interval wajib tercatat di audit_log"
    details = rows[0]["details"]
    if isinstance(details, str):
        details = json.loads(details)
    assert rows[0]["action"] == "CONFIG_CHANGED"
    assert details == {"old": 300.0, "new": 600}

    # lapis kedua: trigger settings_audit mencatat key kanonik + aktornya
    async with db.pool().connection() as conn:
        trail = await fetchall(
            conn,
            "SELECT key, new_value, changed_by FROM settings_audit "
            "WHERE key = 'llm_agent_interval_s' ORDER BY id DESC",
        )
    assert trail, "settings_audit trigger wajib mencatat llm_agent_interval_s"
    assert trail[0]["changed_by"] == "tester"


async def test_put_interval_accepts_boundaries(client_2fa):
    for value in (30, 86400):
        r = await client_2fa.put("/llm-agent/interval", json={"interval_s": value})
        assert r.status_code == 200, f"{value}: {r.text}"
        assert (await db.get_settings())["llm_agent_interval_s"] == value


async def test_status_reports_interval_and_source(client, monkeypatch, _clean_db):
    _no_env(monkeypatch)
    r = await client.get("/llm-agent/status")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["interval_s"] == 300.0
    assert body["source"] == "default"
    assert body["interval_range_s"] == {"min": 30.0, "max": 86400.0}

    await db.set_setting("llm_agent_interval_s", 900)
    body = (await client.get("/llm-agent/status")).json()
    assert body["interval_s"] == 900.0
    assert body["source"] == "settings"


async def test_legacy_write_channel_mirrors_canonical_key(client_2fa):
    """PUT /admin/risk-settings (panel lama) tidak boleh jadi no-op diam-diam."""
    r = await client_2fa.put(
        "/admin/risk-settings",
        json={"password": "testpass", "llm_interval_s": 750},
    )
    assert r.status_code == 200, r.text
    settings = await db.get_settings()
    assert settings["llm_agent_interval_s"] == 750
    assert gr.effective_interval(settings) == (750.0, "settings")


# ── loop: hot-reload tanpa restart ─────────────────────────────────────────

def _patch_loop_io(monkeypatch, waits: list[float], on_wait) -> asyncio.Event:
    """Siapkan agent_loop agar bisa diuji tanpa HTTP/LLM dan tanpa sleep nyata.

    Setiap kali loop menunggu, `on_wait(n, timeout)` dipanggil lalu
    `asyncio.TimeoutError` di-raise supaya loop lanjut ke siklus berikutnya
    (persis perilaku `wait_for` yang kehabisan waktu).
    """
    stop = asyncio.Event()

    async def _noop(*args, **kwargs):
        return None

    monkeypatch.setattr(llm_agent_loop.db, "init_pool", _noop)
    monkeypatch.setattr(llm_agent_loop.db, "close_pool", _noop)
    monkeypatch.setattr(llm_introspection, "run_introspection_tick", _noop)
    monkeypatch.setattr(llm_agent_loop, "JITTER_FRACTION", 0.0)

    async def fake_wait_for(aw, timeout=None):
        if hasattr(aw, "close"):
            aw.close()  # stop.wait() tidak pernah di-await: tutup agar bersih
        waits.append(float(timeout) if timeout is not None else 0.0)
        await on_wait(len(waits))
        raise asyncio.TimeoutError

    monkeypatch.setattr(llm_agent_loop.asyncio, "wait_for", fake_wait_for)
    return stop


async def test_agent_loop_hot_reloads_interval_between_cycles(
    monkeypatch, _clean_db, capsys
):
    """Ubah settings di antara siklus -> delay siklus berikutnya nilai baru."""
    _no_env(monkeypatch)
    # guard aktif: siklus kerja di-skip, loop tetap menghitung interval + delay
    await db.set_setting("kill_switch", True)
    waits: list[float] = []

    async def on_wait(n: int) -> None:
        if n == 1:  # owner mengubah interval saat loop sedang menunggu
            await db.set_setting("llm_agent_interval_s", 120)
        if n >= 2:
            stop.set()

    stop = _patch_loop_io(monkeypatch, waits, on_wait)
    async with asyncio.timeout(30):
        await asyncio.get_running_loop().create_task(llm_agent_loop.agent_loop(stop))

    assert waits[:2] == [300.0, 120.0], waits
    # sumber nilai dilaporkan di log (operator bisa buktikan hot-reload)
    out = capsys.readouterr().err
    assert "interval efektif 300s" in out
    assert "interval efektif 120s" in out


async def test_agent_loop_clamps_settings_interval(monkeypatch, _clean_db):
    """Nilai settings di bawah floor tetap dihormati sebagai 30 s, bukan 5 s."""
    _no_env(monkeypatch)
    await db.set_setting("kill_switch", True)
    await db.set_setting("llm_agent_interval_s", 5)
    waits: list[float] = []

    async def on_wait(n: int) -> None:
        stop.set()

    stop = _patch_loop_io(monkeypatch, waits, on_wait)
    async with asyncio.timeout(30):
        await asyncio.get_running_loop().create_task(llm_agent_loop.agent_loop(stop))

    assert waits[:1] == [30.0], waits
