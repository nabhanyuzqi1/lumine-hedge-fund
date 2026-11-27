"""[FUND2-LLM-2 t_862bb6a7] Test wiring konteks makro ke _collect_context.

Offline: collect_extras dimock di namespace app.llm_agent_loop. DB memakai
fixture autouse _clean_db (fund2_test_*), tanpa jaringan.
"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch

from app import db
from app.llm_agent_loop import (
    PROMPT_VERSION,
    SYSTEM_PROMPT,
    _collect_context,
)

NOW = datetime(2026, 11, 24, 12, 0, 0, tzinfo=timezone.utc)

OK_EXTRAS = {
    "sentiment": {
        "status": "ok",
        "fetched_at": NOW.isoformat(),
        "as_of": NOW.isoformat(),
        "fng": {"value": 40, "classification": "Fear"},
    },
    "fundamental": {
        "status": "ok",
        "fetched_at": NOW.isoformat(),
        "as_of": NOW.isoformat(),
        "dxy": {"value": 106.1, "as_of": NOW.isoformat()},
        "yields": {"us10y_pct": 4.3, "as_of": NOW.isoformat(), "source": "yahoo_chart"},
    },
    "calendar": {
        "status": "ok",
        "fetched_at": NOW.isoformat(),
        "as_of": NOW.isoformat(),
        "events": [{"title": "Nonfarm Payrolls", "time_utc": NOW.isoformat(), "impact": "High"}],
        "next_high_impact_utc": NOW.isoformat(),
        "minutes_to_next_high_impact": 30.0,
    },
}

UNAVAILABLE_EXTRAS = {
    "sentiment": {"status": "unavailable", "fetched_at": NOW.isoformat(), "as_of": None,
                  "source": "alternative.me", "error": "HTTPError: 429"},
    "fundamental": {"status": "unavailable", "fetched_at": NOW.isoformat(), "as_of": None,
                    "source": "yahoo_chart", "error": "RuntimeError: semua sumber gagal"},
    "calendar": {"status": "unavailable", "fetched_at": NOW.isoformat(), "as_of": None,
                 "source": "faireconomy.media", "error": "ConnectTimeout: 10s"},
}


def test_prompt_version_is_current():
    """Pin versi prompt: bump versi wajib sadar.

    2.0.0 = multi-TF (e2b4acc); 2.2.0-stops = aturan angka SL/TP + umpan balik
    last_reject; 2.3.0-rolecontracts = kontrak input + enum ketat + aturan
    degradasi per peran (audit 26 Nov 2026); 2.4.0-facts-quality = level S/R
    deterministik, spread/ATR, proxy dollar FRED, pembersih flag portofolio.
    """
    assert PROMPT_VERSION == "2.4.0-facts-quality"


def test_system_prompt_documented_macro_context():
    low = SYSTEM_PROMPT.lower()
    for token in ("fng", "dxy", "us10y", "minutes_to_next_high_impact",
                  "unavailable", "konteks", "proxy", "mengarang"):
        assert token in low, f"SYSTEM_PROMPT tidak menyebut {token!r}"


async def test_collect_context_contains_three_new_blocks():
    """collect_extras ok -> ctx memuat sentiment+fundamental+calendar apa adanya."""
    async with db.pool().connection() as conn:
        with patch("app.llm_agent_loop.collect_extras", return_value=OK_EXTRAS) as mock:
            ctx = await _collect_context(conn)
    assert mock.await_count == 1  # sekali per siklus, bukan per simbol
    for key in ("sentiment", "fundamental", "calendar"):
        assert ctx[key] == OK_EXTRAS[key]
    # Struktur lama tetap utuh.
    assert set(ctx["symbols"]) == {"XAUUSD", "BTCUSD"}
    assert "risk_limits" in ctx
    assert "now_utc" in ctx and "session" in ctx
    assert "kill_switch" in ctx and "halted" in ctx


async def test_collect_context_valid_when_extras_unavailable():
    """Semua blok unavailable -> ctx tetap valid, tiap blok bawa alasan."""
    async with db.pool().connection() as conn:
        with patch("app.llm_agent_loop.collect_extras", return_value=UNAVAILABLE_EXTRAS):
            ctx = await _collect_context(conn)
    for key in ("sentiment", "fundamental", "calendar"):
        assert ctx[key]["status"] == "unavailable"
        assert ctx[key].get("reason"), f"blok {key} unavailable tanpa reason"
    assert set(ctx["symbols"]) == {"XAUUSD", "BTCUSD"}
    assert "risk_limits" in ctx


async def test_collect_context_survives_collect_extras_raise():
    """collect_extras raise (melanggar kontraknya) -> ctx tetap valid, tak crash."""
    async with db.pool().connection() as conn:
        with patch("app.llm_agent_loop.collect_extras", side_effect=RuntimeError("boom")):
            ctx = await _collect_context(conn)
    for key in ("sentiment", "fundamental", "calendar"):
        assert ctx[key]["status"] == "unavailable"
        assert "boom" in ctx[key]["reason"]
    assert set(ctx["symbols"]) == {"XAUUSD", "BTCUSD"}


async def test_collect_context_fills_missing_block_with_reason():
    """collect_extras kehilangan satu blok -> blok itu unavailable + reason."""
    partial = {"sentiment": OK_EXTRAS["sentiment"]}
    async with db.pool().connection() as conn:
        with patch("app.llm_agent_loop.collect_extras", return_value=partial):
            ctx = await _collect_context(conn)
    assert ctx["sentiment"]["status"] == "ok"
    for key in ("fundamental", "calendar"):
        assert ctx[key]["status"] == "unavailable"
        assert ctx[key].get("reason")


async def test_collect_context_normalizes_unavailable_error_to_reason():
    """Blok unavailable tanpa kunci reason -> alasan diambil dari error."""
    raw = {
        "sentiment": {"status": "unavailable", "error": "HTTPError: 503"},
    }
    async with db.pool().connection() as conn:
        with patch("app.llm_agent_loop.collect_extras", return_value=raw):
            ctx = await _collect_context(conn)
    assert ctx["sentiment"]["reason"] == "HTTPError: 503"
    for key in ("fundamental", "calendar"):
        assert ctx[key]["status"] == "unavailable" and ctx[key].get("reason")
