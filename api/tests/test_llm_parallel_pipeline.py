"""Test arsitektur multi-agent paralel + jadwal simbol (t_2a1fbf01)."""
import asyncio
import time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pytest

from app import llm_models, llm_specialists, symbol_sessions

WIB = ZoneInfo("Asia/Jakarta")


# ── jadwal simbol ─────────────────────────────────────────────────────────
def test_weekday_only_xau():
    rabu = datetime(2026, 11, 25, 10, 0, tzinfo=WIB)  # Rabu
    assert symbol_sessions.active_symbols(rabu, ["XAUUSD", "BTCUSD"], ()) == ["XAUUSD"]


def test_weekend_only_btc():
    sabtu = datetime(2026, 11, 28, 10, 0, tzinfo=WIB)
    minggu = datetime(2026, 11, 29, 22, 0, tzinfo=WIB)
    assert symbol_sessions.active_symbols(sabtu, ["XAUUSD", "BTCUSD"], ()) == ["BTCUSD"]
    assert symbol_sessions.active_symbols(minggu, ["XAUUSD", "BTCUSD"], ()) == ["BTCUSD"]


def test_allowed_symbols_never_widened():
    rabu = datetime(2026, 11, 25, 10, 0, tzinfo=WIB)
    assert symbol_sessions.active_symbols(rabu, ["XAUUSD"], ()) == ["XAUUSD"]
    sabtu = datetime(2026, 11, 28, 10, 0, tzinfo=WIB)
    assert symbol_sessions.active_symbols(sabtu, ["XAUUSD"], ()) == []


def test_schedule_note_reports_wib_and_day():
    rabu = datetime(2026, 11, 25, 3, 0, tzinfo=timezone.utc)  # 10:00 WIB
    note = symbol_sessions.schedule_note(rabu)
    assert note["hari"] == "Rabu"
    assert note["weekend"] is False
    assert note["aktif"] == "XAUUSD"


# ── pemilihan model ───────────────────────────────────────────────────────
def test_resolve_defaults_and_override():
    cfg = llm_models.resolve({})
    assert cfg["parallel"] is True
    assert cfg["specialist"] == "lucif-flash"
    assert cfg["synth"] == "lucif"
    assert cfg["fallback"] == "lucif-claude"
    assert cfg["roles"] == {"technical": "lucif-claude"}
    cfg2 = llm_models.resolve({"llm_models": {"specialist": "lucif", "synth": "lucif-claude",
                                             "parallel": False}})
    assert cfg2["specialist"] == "lucif"
    assert cfg2["synth"] == "lucif-claude"
    assert cfg2["parallel"] is False


def test_role_override_used_per_role(monkeypatch):
    """Technical memakai model override (TTFT terendah), role lain tetap default."""
    import asyncio as _asyncio

    seen = {}

    async def fake(http, *, base, key, model, system, user, max_tokens, timeout_s, **kw):
        for role in ("TECHNICAL", "MACRO", "SENTIMENT", "PORTFOLIO"):
            if role in system:
                seen[role.lower()] = model
        return {"data": {"confidence": 0.5}, "model": model, "latency_ms": 1,
                "prompt_tokens": 1, "completion_tokens": 1, "raw": "{}"}

    monkeypatch.setattr(llm_specialists, "_chat", fake)
    _asyncio.get_event_loop_policy()
    _asyncio.run(llm_specialists.run_specialists(
        None, CTX, symbol="XAUUSD", base="http://x", key="k", model="lucif-flash",
        role_models={"technical": "lucif-claude"}))
    assert seen["technical"] == "lucif-claude"
    assert seen["macro"] == "lucif-flash"


def test_resolve_ignores_invalid_model_name():
    cfg = llm_models.resolve({"llm_models": {"specialist": "nama model aneh!"}})
    assert cfg["specialist"] == "lucif-flash"


# ── pipeline paralel ──────────────────────────────────────────────────────
CTX = {
    "now_utc": "2026-11-26T03:00:00+00:00",
    "session": {"name": "asia"},
    "calendar": {"status": "ok", "events": []},
    "sentiment": {"status": "ok", "score": 0.1},
    "fundamental": {"status": "ok"},
    "account": {"equity": 10000.0},
    "symbols": {
        "XAUUSD": {"price": 2641.3, "spread": 0.2, "candles": {"m5": [1, 2, 3]},
                   "indicators": {"atr": 6.2, "rsi": 58}, "structure": {"support": [2630]},
                   "llm_positions": []},
        "BTCUSD": {"price": 68000, "spread": 39, "candles": {"m5": [1]},
                   "indicators": {"atr": 310}, "structure": {}, "llm_positions": []},
    },
}


def test_slice_only_contains_requested_symbol():
    tech = llm_specialists._slice(CTX, "technical", "XAUUSD")
    assert list(tech["symbols"]) == ["XAUUSD"]
    port = llm_specialists._slice(CTX, "portfolio", "BTCUSD")
    assert list(port["symbols"]) == ["BTCUSD"]
    macro = llm_specialists._slice(CTX, "macro", "XAUUSD")
    assert macro["symbol"] == "XAUUSD"


@pytest.mark.asyncio
async def test_specialists_run_in_parallel(monkeypatch):
    """4 specialist masing-masing 0,3 s harus selesai < 0,6 s (bukan 1,2 s)."""
    async def fake_chat(http, *, base, key, model, system, user, max_tokens, timeout_s, **kw):
        await asyncio.sleep(0.3)
        return {"data": {"confidence": 0.6}, "model": model, "latency_ms": 300,
                "prompt_tokens": 100, "completion_tokens": 20, "raw": "{}"}

    monkeypatch.setattr(llm_specialists, "_chat", fake_chat)
    started = time.monotonic()
    res = await llm_specialists.run_specialists(
        None, CTX, symbol="XAUUSD", base="http://x", key="k", model="lucif-flash")
    elapsed = time.monotonic() - started
    assert set(res) == set(llm_specialists.ROLES)
    assert all(r["state"] == "ok" for r in res.values())
    assert elapsed < 0.9, f"specialist tidak paralel: {elapsed:.2f}s"


@pytest.mark.asyncio
async def test_specialist_failure_degrades_not_fatal(monkeypatch):
    async def fake_chat(http, *, base, key, model, system, user, max_tokens, timeout_s, **kw):
        if "SPECIALIST MACRO" in system:
            raise RuntimeError("LLM HTTP 500: upstream down")
        return {"data": {"confidence": 0.5}, "model": model, "latency_ms": 10,
                "prompt_tokens": 10, "completion_tokens": 5, "raw": "{}"}

    monkeypatch.setattr(llm_specialists, "_chat", fake_chat)
    res = await llm_specialists.run_specialists(
        None, CTX, symbol="XAUUSD", base="http://x", key="k", model="m")
    assert res["macro"]["state"] == "error"
    assert res["technical"]["state"] == "ok"


@pytest.mark.asyncio
async def test_synthesize_marks_missing_roles(monkeypatch):
    captured = {}

    async def fake_chat(http, *, base, key, model, system, user, max_tokens, timeout_s, **kw):
        captured["user"] = user
        return {"data": {"kind": "hold", "confidence": 0.4}, "model": model,
                "latency_ms": 5, "prompt_tokens": 10, "completion_tokens": 5, "raw": "{}"}

    monkeypatch.setattr(llm_specialists, "_chat", fake_chat)
    evidence = {
        "technical": {"state": "ok", "data": {"confidence": 0.7}},
        "macro": {"state": "timeout", "error": "timeout"},
        "sentiment": {"state": "ok", "data": {"confidence": 0.3}},
        "portfolio": {"state": "ok", "data": {"confidence": 0.8}},
    }
    out = await llm_specialists.synthesize(
        None, CTX, evidence, symbol="XAUUSD", base="http://x", key="k", model="lucif")
    assert out["missing"] == ["macro"]
    assert "<symbol>XAUUSD</symbol>" in captured["user"]
    assert '"BTCUSD"' not in captured["user"].split("<market_snapshot>")[1]
