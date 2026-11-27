"""Nilai efektif & whitelist: audit frontend/security 26 Nov 2026.

Kontrak yang dijaga:
1. `llm_risk.max_orders_per_min` tidak boleh lebih longgar dari rate akun.
2. Ambang breaker tidak bisa ditulis lewat kanal `llm_risk` (satu pemilik:
   kill_switch_triggers), jadi permintaan itu ditolak 422, bukan diabaikan.
3. Override risiko auto-lot hanya bisa menurunkan risiko global.
4. `state_machine.transition(set_fields=...)` menolak kolom di luar whitelist
   (nama kolom masuk ke string SQL).
5. `/version` bisa mendeteksi proses API yang lebih tua dari file di disk.
"""
from __future__ import annotations

import asyncio

import pytest

from app import version_info
from app.guardrail_ranges import (
    LLM_RISK_DERIVED_KEYS,
    GuardrailRangeError,
    validate_llm_risk_updates,
)
from app.llm_risk import get_llm_risk
from app.lot_sizing import auto_lot_config
from app.state_machine import SET_FIELD_COLUMNS, InvalidTransition, transition


def test_llm_rate_clamped_to_account_limit():
    cfg = get_llm_risk({"llm_risk": {"max_orders_per_min": 10},
                        "max_orders_per_min": 5})
    assert cfg["max_orders_per_min"] == 5


def test_llm_rate_can_be_tighter_than_account():
    cfg = get_llm_risk({"llm_risk": {"max_orders_per_min": 2},
                        "max_orders_per_min": 5})
    assert cfg["max_orders_per_min"] == 2


def test_llm_rate_ignores_garbage_account_value():
    cfg = get_llm_risk({"llm_risk": {"max_orders_per_min": 7},
                        "max_orders_per_min": "abc"})
    assert cfg["max_orders_per_min"] == 7


def test_derived_keys_are_declared():
    # Guard berikut hanya bermakna bila daftarnya tidak kosong.
    assert {"drawdown_pause_pct", "consecutive_failed_pause",
            "ea_offline_block_s"} <= set(LLM_RISK_DERIVED_KEYS)


@pytest.mark.parametrize("key", sorted(LLM_RISK_DERIVED_KEYS))
def test_breaker_keys_rejected_on_llm_channel(key):
    with pytest.raises(GuardrailRangeError) as exc:
        validate_llm_risk_updates({key: 1})
    assert "kill_switch_triggers" in str(exc.value)


def test_non_breaker_key_still_accepted():
    out = validate_llm_risk_updates({"cooldown_s": 30})
    assert out["cooldown_s"] == 30


def test_auto_lot_effective_risk_uses_stricter_value():
    cfg = auto_lot_config({"llm_auto_lot": {"enabled": True, "risk_pct": 1.0},
                           "risk_per_trade_pct": 0.75})
    assert cfg["risk_pct"] == 1.0            # nilai tersimpan tetap utuh
    assert cfg["global_risk_pct"] == 0.75
    assert cfg["effective_risk_pct"] == pytest.approx(0.75)


def test_auto_lot_override_can_lower_risk():
    cfg = auto_lot_config({"llm_auto_lot": {"enabled": True, "risk_pct": 0.25},
                           "risk_per_trade_pct": 0.75})
    assert cfg["effective_risk_pct"] == pytest.approx(0.25)


def test_set_fields_whitelist_rejects_unknown_column():
    with pytest.raises(InvalidTransition) as exc:
        asyncio.run(transition(None, "x", "NEW", set_fields={"status": "FILLED"}))
    assert "tidak diizinkan" in str(exc.value)


def test_set_fields_whitelist_matches_known_columns():
    assert "ticket" in SET_FIELD_COLUMNS
    assert "status" not in SET_FIELD_COLUMNS


def test_version_info_flags_stale_process(monkeypatch):
    disk = version_info.disk_prompt_version()
    assert disk, "PROMPT_VERSION harus terbaca dari file"
    monkeypatch.setattr(version_info, "_RUNNING_PROMPT_VERSION", "0.0.0-old")
    assert version_info.info()["stale_code"] is True
    monkeypatch.setattr(version_info, "_RUNNING_PROMPT_VERSION", disk)
    assert version_info.info()["stale_code"] is False
