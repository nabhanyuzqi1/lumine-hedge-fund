"""Kartu t_dc104883 (SEC-GUARD): `PUT /kill-switch/triggers` tunduk pada aturan
yang sama dengan `PUT /admin/risk-settings`.

Tiga celah yang ditutup:

1. Jalur Ops lama tidak memakai validator bersama, sehingga DD 500% / 0 detik
   bisa tersimpan tanpa ditolak UI Guardrail.
2. `password` opsional: sesi 2FA saja cukup menulis guardrail tanpa re-auth.
3. Tidak ada penanda deprecated: satu perubahan punya dua bentuk jejak audit.

Semua nilai di sini ditulis lewat endpoint API (database test sekali-pakai
conftest); tidak menyentuh DB staging/live.
"""
from __future__ import annotations

import logging

import pytest
from httpx import ASGITransport, AsyncClient

from app import db
from app.guardrail_ranges import (
    TRIGGER_RANGES,
    GuardrailRangeError,
    validate_trigger_updates,
)
from app.kill_switch import DEFAULT_TRIGGERS, MODES
from app.main import app


async def _stored_triggers() -> dict:
    return (await db.get_settings()).get("kill_switch_triggers") or {}


async def _events(action: str) -> list[dict]:
    async with db.pool().connection() as conn:
        rows = await (await conn.execute(
            "SELECT action, mode, strategy, source, actor, reason, details "
            "FROM kill_switch_events WHERE action = %s ORDER BY id",
            (action,),
        )).fetchall()
    return [
        {"action": r["action"], "mode": r["mode"], "strategy": r["strategy"],
         "source": r["source"], "actor": r["actor"], "reason": r["reason"],
         "details": r["details"]}
        for r in rows
    ]


# ── unit: satu validator bersama, rentang t_dc104883 ───────────────────────

def test_ranges_match_card_spec():
    assert TRIGGER_RANGES == {
        "daily_drawdown_pct": (0.1, 50.0),
        "total_drawdown_pct": (0.1, 80.0),
        "consecutive_failed_orders": (1, 1000),
        "ea_offline_seconds": (1.0, 3600.0),
        "ea_offline_halt_seconds": (1.0, 86400.0),
        "check_interval_seconds": (5.0, 3600.0),
    }
    # Nilai policy owner §I harus berada di dalam rentang supaya kanal resmi
    # tidak pernah menolak angka final.
    policy = {
        "daily_drawdown_pct": 3.0,
        "total_drawdown_pct": 8.0,
        "consecutive_failed_orders": 3,
        "ea_offline_seconds": 6.0,
        "ea_offline_halt_seconds": 60.0,
        "check_interval_seconds": 5.0,
    }
    assert validate_trigger_updates(dict(policy)) == policy


@pytest.mark.parametrize("field,lo,hi", [
    ("daily_drawdown_pct", 0.1, 50.0),
    ("total_drawdown_pct", 0.1, 80.0),
    ("consecutive_failed_orders", 1, 1000),
    ("ea_offline_seconds", 1.0, 3600.0),
    ("ea_offline_halt_seconds", 1.0, 86400.0),
    ("check_interval_seconds", 5.0, 3600.0),
])
def test_field_boundaries(field, lo, hi):
    assert validate_trigger_updates({field: lo})[field] == lo
    assert validate_trigger_updates({field: hi})[field] == hi
    for bad in (lo - 0.01, hi + 0.01, 0, -1):
        with pytest.raises(GuardrailRangeError):
            validate_trigger_updates({field: bad})


def test_all_bad_fields_reported_per_field():
    try:
        validate_trigger_updates({
            "daily_drawdown_pct": 500,
            "ea_offline_seconds": 0,
            "check_interval_seconds": 1.0,
        })
    except GuardrailRangeError as exc:
        msg = str(exc)
        assert "daily_drawdown_pct" in msg
        assert "ea_offline_seconds" in msg
        assert "check_interval_seconds" in msg
        assert msg.count(";") == 2, msg
    else:
        pytest.fail("nilai di luar rentang harus ditolak")


def test_modes_validated_by_the_same_function():
    out = validate_trigger_updates({"modes": {"ea_offline": "GLOBAL_HALT"}},
                                   allowed_modes=set(MODES))
    assert out == {"modes": {"ea_offline": "GLOBAL_HALT"}}
    with pytest.raises(GuardrailRangeError, match="MODE_ANEH"):
        validate_trigger_updates({"modes": {"ea_offline": "MODE_ANEH"}},
                                 allowed_modes=set(MODES))


# ── API (a): jalur Ops menolak nilai di luar rentang, tidak menulis ────────

@pytest.mark.asyncio
async def test_ops_path_rejects_out_of_range_and_writes_nothing(client_2fa):
    before = await _stored_triggers()
    for patch in (
        {"daily_drawdown_pct": 500},
        {"total_drawdown_pct": 0.01},
        {"consecutive_failed_orders": 999999},
        {"ea_offline_seconds": 0},
        {"ea_offline_halt_seconds": 200000},
        {"check_interval_seconds": 1.0},
    ):
        r = await client_2fa.put("/kill-switch/triggers",
                                 json={"password": "testpass", **patch})
        assert r.status_code == 422, r.text
        assert list(patch)[0] in r.text, "pesan 422 harus menyebut field"
    assert await _stored_triggers() == before, "tolakan 422 tidak boleh menulis"


@pytest.mark.asyncio
async def test_ops_path_accepts_extreme_but_in_range_value(client_2fa):
    """Batas rentang boleh dipakai (validasi, bukan policy): 50% masih 422-free
    di unit, tapi API tetap 422 di atas 50 dan nilai policy tetap valid."""
    r = await client_2fa.put("/kill-switch/triggers",
                             json={"password": "testpass", "daily_drawdown_pct": 3.0})
    assert r.status_code == 200, r.text
    assert r.json()["triggers"]["daily_drawdown_pct"] == 3.0


# ── API (b): kedua kanal menghasilkan event berbentuk identik ──────────────

@pytest.mark.asyncio
async def test_both_channels_produce_identical_triggers_updated_events(client_2fa):
    patch = {"daily_drawdown_pct": 3.0, "total_drawdown_pct": 8.0}
    r1 = await client_2fa.put("/kill-switch/triggers",
                              json={"password": "testpass", **patch})
    assert r1.status_code == 200, r1.text
    r2 = await client_2fa.put("/admin/risk-settings",
                              json={"password": "testpass",
                                    "kill_switch_triggers": patch})
    assert r2.status_code == 200, r2.text

    events = await _events("TRIGGERS_UPDATED")
    legacy, admin = events[-2], events[-1]
    # Bentuk identik: field event sama, details {updates, previous}, nullable
    # mode/strategy sama-sama NULL.
    assert set(legacy) == set(admin)
    assert legacy["mode"] is None and admin["mode"] is None
    assert legacy["strategy"] is None and admin["strategy"] is None
    assert set(legacy["details"]) == {"updates", "previous"}
    assert set(admin["details"]) == {"updates", "previous"}
    assert legacy["details"]["updates"] == patch == admin["details"]["updates"]
    assert legacy["actor"] == admin["actor"] == "tester"
    # previous = nilai lama per key yang diubah (from -> to), bukan seluruh objek.
    for ev in (legacy, admin):
        assert set(ev["details"]["previous"]) == set(patch)
        assert ev["details"]["previous"]["daily_drawdown_pct"] == \
            DEFAULT_TRIGGERS["daily_drawdown_pct"]
    # Kanal asal tetap terbaca tanpa mengubah bentuk.
    assert admin["source"] == "dashboard:guardrail"
    assert legacy["source"] == "dashboard:ops-legacy"


# ── API (c): password salah di jalur Ops -> 403 + audit penolakan ──────────

@pytest.mark.asyncio
async def test_ops_path_wrong_password_rejected_and_audited(client_2fa):
    before = await _stored_triggers()
    r = await client_2fa.put("/kill-switch/triggers",
                             json={"password": "salah", "daily_drawdown_pct": 3.0})
    assert r.status_code == 403, r.text
    assert await _stored_triggers() == before
    async with db.pool().connection() as conn:
        rows = await (await conn.execute(
            "SELECT count(*) AS n FROM audit_log WHERE action = 'RISK_SETTINGS_REJECTED' "
            "AND object = 'kill_switch_triggers'",
        )).fetchall()
    assert rows[0]["n"] >= 1


# ── API (d): tanpa password -> 422 (tidak ada pengecualian sesi user) ──────

@pytest.mark.asyncio
async def test_ops_path_requires_password_even_with_active_2fa(client_2fa):
    """Sesi 2FA saja tidak cukup: endpoint ini hanya menerima sesi user, jadi
    tanpa password tidak boleh menulis guardrail (kartu t_dc104883 #2)."""
    before = await _stored_triggers()
    r = await client_2fa.put("/kill-switch/triggers",
                             json={"daily_drawdown_pct": 3.0})
    assert r.status_code == 422, r.text
    assert "password" in r.text
    assert await _stored_triggers() == before


# ── API (e): endpoint lama ditandai deprecated + log warning ───────────────

def test_openapi_marks_legacy_triggers_endpoint_deprecated():
    schema = app.openapi()
    put = schema["paths"]["/kill-switch/triggers"]["put"]
    assert put.get("deprecated") is True
    admin = schema["paths"]["/admin/risk-settings"]["put"]
    assert admin.get("deprecated", False) is False


@pytest.mark.asyncio
async def test_usage_of_legacy_endpoint_logs_warning(client_2fa, caplog):
    with caplog.at_level(logging.WARNING, logger="app.routes"):
        r = await client_2fa.put(
            "/kill-switch/triggers",
            json={"password": "testpass", "ea_offline_halt_seconds": 60.0})
    assert r.status_code == 200, r.text
    assert any(
        "kill-switch/triggers" in rec.getMessage() and "DEPRECATED" in rec.getMessage()
        for rec in caplog.records
    ), caplog.text
