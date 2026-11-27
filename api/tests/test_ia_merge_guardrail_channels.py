"""Satu kanal tulis guardrail (kartu t_f412fd48).

Menguji pemisahan IA Guardrail / Ops / Strategy Lab dari sisi backend:

1. `PUT /kill-switch/triggers` (jalur lama, dipakai Ops sebelum kartu ini)
   memakai validasi rentang yang SAMA dengan `PUT /admin/risk-settings`.
   Sebelumnya jalur ini tanpa validasi: DD 500% tersimpan.
2. `PUT /admin/risk-settings` adalah satu-satunya kanal tulis untuk
   auto-trigger, llm_risk, llm_auto_lot, dan interval siklus agent LLM.
3. Nilai yang tersimpan benar-benar dipakai: GET /admin/risk-settings,
   GET /kill-switch, dan GET /llm-agent/config membaca nilai aktif.
4. Nilai di luar rentang wajar ditolak 422 tanpa menulis apa pun.

Catatan: perubahan settings di test ini memakai database test sekali-pakai
(conftest) dan tidak menyentuh DB staging/live.
"""
from __future__ import annotations

import pytest

from app import db
from app.guardrail_ranges import (
    GuardrailRangeError,
    effective_interval_s,
    validate_auto_lot_updates,
    validate_interval_s,
    validate_llm_risk_updates,
    validate_trigger_updates,
)


# ── unit: fungsi validasi bersama ──────────────────────────────────────────

def test_validate_trigger_rejects_absurd_drawdown():
    with pytest.raises(GuardrailRangeError):
        validate_trigger_updates({"daily_drawdown_pct": 500})
    with pytest.raises(GuardrailRangeError):
        validate_trigger_updates({"total_drawdown_pct": 0})
    with pytest.raises(GuardrailRangeError):
        validate_trigger_updates({"payload_aneh": 1})
    # nilai wajar lolos apa adanya
    assert validate_trigger_updates({"daily_drawdown_pct": 3}) == {
        "daily_drawdown_pct": 3.0}


def test_validate_trigger_integer_and_bool_fields():
    with pytest.raises(GuardrailRangeError):
        validate_trigger_updates({"consecutive_failed_orders": 2.5})
    assert validate_trigger_updates({"consecutive_failed_orders": 3}) == {
        "consecutive_failed_orders": 3}
    with pytest.raises(GuardrailRangeError):
        # bool bukan angka: True tidak boleh lolos sebagai 1
        validate_trigger_updates({"ea_offline_seconds": True})
    assert validate_trigger_updates({"ea_offline_requires_positions": False}) == {
        "ea_offline_requires_positions": False}


def test_validate_llm_risk_and_auto_lot():
    out = validate_llm_risk_updates({"max_orders_per_min": 2, "max_layers": 2})
    assert out == {"max_orders_per_min": 2, "max_layers": 2}
    with pytest.raises(GuardrailRangeError):
        validate_llm_risk_updates({"drawdown_pause_pct": 60})
    with pytest.raises(GuardrailRangeError):
        validate_llm_risk_updates({"key_karangan": 1})
    with pytest.raises(GuardrailRangeError):
        validate_llm_risk_updates({"block_new_order_with_position": "ya"})
    assert validate_auto_lot_updates({"enabled": True}) == {"enabled": True}
    with pytest.raises(GuardrailRangeError):
        validate_auto_lot_updates({"enabled": "on"})
    with pytest.raises(GuardrailRangeError):
        validate_auto_lot_updates({"risk_pct": 9})


def test_validate_interval_floor_30s():
    assert validate_interval_s(30) == 30.0
    assert validate_interval_s(900) == 900.0
    for bad in (10, 29.9, 0, -5, "300"):
        with pytest.raises(GuardrailRangeError):
            validate_interval_s(bad)
    # fallback env + floor
    assert effective_interval_s({}) >= 30.0
    assert effective_interval_s({"llm_interval_s": 45}) == 45.0


# ── API: jalur tulis Ops lama kini divalidasi ──────────────────────────────

@pytest.mark.asyncio
async def test_legacy_kill_switch_triggers_endpoint_rejects_out_of_range(client_2fa):
    r = await client_2fa.put(
        "/kill-switch/triggers",
        json={"password": "testpass", "daily_drawdown_pct": 500},
    )
    assert r.status_code == 422, r.text
    assert "daily_drawdown_pct" in r.text
    # tidak ada yang tersimpan
    settings = await db.get_settings()
    stored = settings.get("kill_switch_triggers") or {}
    assert stored.get("daily_drawdown_pct") in (None, 3.0)


@pytest.mark.asyncio
async def test_legacy_kill_switch_triggers_endpoint_still_accepts_sane_value(client_2fa):
    r = await client_2fa.put(
        "/kill-switch/triggers",
        json={"password": "testpass", "consecutive_failed_orders": 3},
    )
    assert r.status_code == 200, r.text
    assert r.json()["triggers"]["consecutive_failed_orders"] == 3


# ── API: kanal admin menulis semua setelan guardrail ──────────────────────

@pytest.mark.asyncio
async def test_admin_risk_settings_writes_triggers_with_audit(client_2fa):
    r = await client_2fa.put(
        "/admin/risk-settings",
        json={"password": "testpass",
              "kill_switch_triggers": {"daily_drawdown_pct": 3,
                                       "total_drawdown_pct": 8}},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["values"]["kill_switch_triggers"]["daily_drawdown_pct"] == 3.0

    ks = await client_2fa.get("/kill-switch")
    assert ks.status_code == 200, ks.text
    trig = ks.json()["triggers"]
    assert trig["daily_drawdown_pct"] == 3.0
    assert trig["total_drawdown_pct"] == 8.0
    # field lain tidak hilang oleh merge parsial
    assert trig["ea_offline_halt_seconds"] is not None
    assert trig["modes"], "modes auto-trigger tidak boleh hilang"

    audit = await client_2fa.get("/admin/settings-audit?limit=20")
    rows = [x for x in audit.json()["rows"] if x["key"] == "kill_switch_triggers"]
    assert rows, "perubahan auto-trigger wajib tercatat di settings_audit"


@pytest.mark.asyncio
async def test_admin_risk_settings_rejects_out_of_range_triggers(client_2fa):
    r = await client_2fa.put(
        "/admin/risk-settings",
        json={"password": "testpass",
              "kill_switch_triggers": {"total_drawdown_pct": 500}},
    )
    assert r.status_code == 422, r.text


@pytest.mark.asyncio
async def test_admin_risk_settings_llm_settings_roundtrip(client_2fa):
    r = await client_2fa.put(
        "/admin/risk-settings",
        json={"password": "testpass",
              "llm_interval_s": 900,
              "llm_auto_lot": {"enabled": True},
              "llm_risk": {"max_orders_per_min": 2, "max_layers": 2}},
    )
    assert r.status_code == 200, r.text

    g = await client_2fa.get("/admin/risk-settings")
    assert g.status_code == 200, g.text
    llm = g.json()["llm"]
    assert llm["interval_s"] == 900.0
    assert llm["auto_lot"]["enabled"] is True
    assert llm["risk"]["max_orders_per_min"] == 2
    assert llm["risk"]["max_layers"] == 2
    # key llm_risk lain tetap ada (merge parsial, bukan replace)
    assert "drawdown_pause_pct" in llm["risk"]

    cfg = await client_2fa.get("/llm-agent/config")
    assert cfg.status_code == 200, cfg.text
    assert cfg.json()["interval_s"] == 900.0
    assert cfg.json()["llm_auto_lot"]["enabled"] is True


@pytest.mark.asyncio
async def test_admin_risk_settings_rejects_bad_llm_values(client_2fa):
    r = await client_2fa.put(
        "/admin/risk-settings",
        json={"password": "testpass", "llm_interval_s": 10},
    )
    assert r.status_code == 422, r.text
    r = await client_2fa.put(
        "/admin/risk-settings",
        json={"password": "testpass", "llm_risk": {"max_orders_per_min": 5000}},
    )
    assert r.status_code == 422, r.text
    r = await client_2fa.put(
        "/admin/risk-settings",
        json={"password": "testpass", "llm_risk": {"field_karangan": 1}},
    )
    assert r.status_code == 422, r.text


@pytest.mark.asyncio
async def test_admin_risk_settings_wrong_password_writes_nothing(client_2fa):
    before = await db.get_settings()
    r = await client_2fa.put(
        "/admin/risk-settings",
        json={"password": "salah", "llm_interval_s": 600},
    )
    assert r.status_code == 403, r.text
    after = await db.get_settings()
    assert before.get("llm_interval_s") == after.get("llm_interval_s")
