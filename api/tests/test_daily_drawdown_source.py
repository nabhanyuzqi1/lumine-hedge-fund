"""AUDIT-A2: auto-halt drawdown harian HANYA dari persen di halaman Ops.

Keputusan owner 25 Nov 2026 (dikonfirmasi Director): SATU sumber parameter
drawdown = PERSEN (`kill_switch_triggers.daily_drawdown_pct`). Field profil
`max_daily_drawdown` (USD) boleh tetap ada sebagai informasi, tetapi TIDAK
boleh memicu halt/blokir.

Bukti bug yang ditutup (data live 25 Nov 2026):
- breaker LLM auto-pause "drawdown harian 1.88% > 1.5%" (default lama) padahal
  owner menyetel 10% di Ops;
- `api/app/risk.py` memicu halt dari -100 USD walau Ops disetel 10%
  (kill_switch_events 25/11 18:20 ACTIVATE source=auto:daily_drawdown_risk_gate).

Isi test:
1. unit gate (tanpa DB): pct=3 + rugi -4% -> halt; pct=10 + rugi -4% -> lolos;
   field USD yang ketat diabaikan; batas 0/N detect; default & "dimatikan".
2. unit helper bersama: rumus %, saldo acuan, ambang dari kunci yang SAMA
   untuk gate, breaker LLM, dan DEFAULT_TRIGGERS kill-switch.
3. integrasi DB (API in-process): ubah pct saat runtime -> gate membaca nilai
   baru tanpa proses dijalankan ulang, dan auto-halt tercatat di
   kill_switch_events dengan source auto:daily_drawdown_risk_gate.
"""
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app import db, drawdown, kill_switch, llm_risk
from app.main import app
from app.risk import RiskContext, risk_gate

BASE_ORDER = {
    "symbol": "XAUUSD",
    "side": "BUY",
    "volume": 0.10,
    "sl": 1998.00,
    "tp": 2005.00,
}

START = 10000.0  # saldo acuan: 1% = 100 USD, 4% = 400 USD


def _settings(**over) -> dict:
    s = {
        "max_volume": 1.0,
        # field profil USD sengaja ketat: tidak boleh berpengaruh lagi
        "max_daily_drawdown": 100.0,
        "max_spread": 0.50,
        "max_orders_per_min": 10,
        "halted": False,
        "kill_switch": False,
        "allowed_symbols": ["XAUUSD"],
        "risk_per_trade_pct": 0.5,
        "daily_start_balance": START,
    }
    s.update(over)
    return s


def _gate(settings: dict, daily_pnl: float):
    return risk_gate(BASE_ORDER, RiskContext(
        settings=settings, bid=1999.85, ask=2000.15, tick_age_s=0.1,
        daily_pnl=daily_pnl, orders_last_minute=0))


# ======================================================== unit: helper bersama

def test_helper_pct_from_pnl():
    assert drawdown.pct_from_pnl(-400.0, START) == pytest.approx(4.0)
    assert drawdown.pct_from_pnl(0.0, START) == 0.0
    assert drawdown.pct_from_pnl(250.0, START) == 0.0  # profit bukan drawdown
    assert drawdown.pct_from_pnl(-400.0, 0) == 0.0     # pembagi nol aman


def test_helper_start_balance_fallbacks():
    assert drawdown.start_balance({"daily_start_balance": 9733.86}) == 9733.86
    assert drawdown.start_balance({"initial_balance": 5000.0}) == 5000.0
    assert drawdown.start_balance({}) == drawdown.DEFAULT_START_BALANCE


def test_helper_limit_pct_semantics():
    # absen -> default A6
    assert drawdown.limit_pct({}) == drawdown.DEFAULT_DAILY_DRAWDOWN_PCT
    # nilai Ops dipakai apa adanya
    assert drawdown.limit_pct(
        {"kill_switch_triggers": {"daily_drawdown_pct": 10.0}}) == 10.0
    # None eksplisit -> trigger dimatikan (semantik kill_switch.get_triggers)
    assert drawdown.limit_pct(
        {"kill_switch_triggers": {"daily_drawdown_pct": None}}) is None
    # nilai rusak -> fallback default (proteksi tetap hidup)
    assert drawdown.limit_pct(
        {"kill_switch_triggers": {"daily_drawdown_pct": "bukan-angka"}}
    ) == drawdown.DEFAULT_DAILY_DRAWDOWN_PCT


def test_semua_pemicu_auto_memakai_kunci_dan_default_yang_sama():
    """Gate, breaker LLM, dan kill-switch: satu kunci, satu default."""
    assert (kill_switch.DEFAULT_TRIGGERS["daily_drawdown_pct"]
            == drawdown.DEFAULT_DAILY_DRAWDOWN_PCT)

    # absen key -> breaker memakai default A6 yang sama, bukan 1.5% sendiri
    assert llm_risk.get_llm_risk({})["drawdown_pause_pct"] == \
        drawdown.DEFAULT_DAILY_DRAWDOWN_PCT

    # nilai Ops -> breaker ikut (bukan ambang terpisah)
    cfg = llm_risk.get_llm_risk(
        {"llm_risk": {"drawdown_pause_pct": 1.5},
         "kill_switch_triggers": {"daily_drawdown_pct": 10.0}})
    assert cfg["drawdown_pause_pct"] == 10.0

    # None di Ops -> breaker drawdown dimatikan total
    cfg = llm_risk.get_llm_risk(
        {"kill_switch_triggers": {"daily_drawdown_pct": None}})
    assert cfg["drawdown_pause_pct"] is None


# =========================================================== unit: risk gate

def test_gate_halts_when_pct_breached():
    """(a) pct=3% + rugi 4% -> halt=True."""
    d = _gate(_settings(kill_switch_triggers={"daily_drawdown_pct": 3.0}),
              daily_pnl=-0.04 * START)
    assert not d.ok
    assert d.halt is True
    assert any("daily drawdown" in r for r in d.reasons), d.reasons
    assert any("3.0%" in r for r in d.reasons), d.reasons


def test_gate_allows_when_below_pct():
    """(b) pct=10% + rugi 4% -> tidak halt."""
    d = _gate(_settings(kill_switch_triggers={"daily_drawdown_pct": 10.0}),
              daily_pnl=-0.04 * START)
    assert d.ok, d.reasons
    assert d.halt is False
    assert not any("daily drawdown" in r for r in d.reasons)


def test_gate_ignores_usd_profile_field():
    """Field USD 1 USD tidak lagi memicu halt (bug -100 USD)."""
    d = _gate(_settings(max_daily_drawdown=1.0,
                        kill_switch_triggers={"daily_drawdown_pct": 10.0}),
              daily_pnl=-400.0)
    assert d.ok, d.reasons
    assert d.halt is False


def test_gate_boundary_exact_limit_halts():
    """Tepat di ambang -> halt (sama dengan evaluator kill-switch: >=)."""
    d = _gate(_settings(kill_switch_triggers={"daily_drawdown_pct": 4.0}),
              daily_pnl=-400.0)
    assert d.halt is True


def test_gate_default_pct_when_trigger_absent():
    d = _gate(_settings(), daily_pnl=-0.035 * START)  # 3,5% >= default 3%
    assert d.halt is True


def test_gate_drawdown_trigger_disabled_by_none():
    d = _gate(_settings(kill_switch_triggers={"daily_drawdown_pct": None}),
              daily_pnl=-5000.0)
    assert d.halt is False


# ================================================= integrasi DB: runtime nilai

@pytest.fixture(autouse=True)
async def _dd_env(_clean_db):
    await db.set_setting("daily_start_balance", START)
    await db.set_setting("max_tick_age_s", 3.0)
    await db.set_setting("kill_switch_triggers", {"daily_drawdown_pct": 10.0})
    yield


async def _csrf(client) -> str:
    return (await client.get("/auth/me")).json()["csrf_token"]


def _order_body(**over) -> dict:
    body = {"symbol": "XAUUSD", "side": "BUY", "volume": 0.1,
            "sl": 1998.0, "tp": 2010.0, "strategy": "manual"}
    body.update(over)
    return body


_TICKET = [9100]


async def _seed_closed_loss(profit: float) -> None:
    _TICKET[0] += 1
    async with db.pool().connection() as conn:
        await conn.execute(
            "INSERT INTO positions (ticket, symbol, side, volume, open_price, "
            "close_price, profit, status, close_time) "
            "VALUES (%s, 'XAUUSD', 'BUY', 0.01, 2000, 1990, %s, 'CLOSED', now())",
            (_TICKET[0], profit),
        )


async def test_runtime_pct_change_read_by_gate_without_restart(client, tick_2000):
    """(c) ubah pct saat runtime -> gate baca nilai baru, proses tidak restart."""
    for _ in range(4):  # -400 USD = 4% dari saldo awal 10.000
        await _seed_closed_loss(-100.0)

    # Ops 10% -> rugi 4% masih lolos (order diterima)
    r = await client.post("/orders", json=_order_body(),
                          headers={"x-csrf-token": await _csrf(client)})
    assert r.status_code == 201, r.text

    # Owner mengetatkan ke 3% lewat kanal Ops (settings) - proses SAMA
    await db.set_setting("kill_switch_triggers", {"daily_drawdown_pct": 3.0})

    r2 = await client.post("/orders", json=_order_body(),
                           headers={"x-csrf-token": await _csrf(client)})
    assert r2.status_code == 422, r2.text
    reasons = r2.json()["rejected_reasons"]
    assert any("daily drawdown" in x and "3.0%" in x for x in reasons), reasons

    # auto-halt menyala lewat jalur yang sama dan tercatat di audit
    state = await kill_switch.get_state()
    assert state["active"] is True
    assert state["mode"] == "GLOBAL_HALT"
    assert state["source"] == "auto:daily_drawdown_risk_gate"
    async with db.pool().connection() as conn:
        row = await (await conn.execute(
            "SELECT action, source, reason FROM kill_switch_events "
            "WHERE source = 'auto:daily_drawdown_risk_gate' "
            "ORDER BY id DESC LIMIT 1")).fetchone()
    assert row is not None, "auto-halt harus tercatat di kill_switch_events"
    assert row["action"] == "ACTIVATE"
    assert "daily drawdown" in row["reason"]


async def test_runtime_relax_after_breach_never_halted(client, tick_2000):
    """Nilai longgar dari Ops tidak pernah memicu halt walau USD profil ketat."""
    await db.set_setting("max_daily_drawdown", 1.0)  # profil USD, harus diabaikan
    await db.set_setting("kill_switch_triggers", {"daily_drawdown_pct": 10.0})
    for _ in range(4):
        await _seed_closed_loss(-100.0)
    r = await client.post("/orders", json=_order_body(),
                          headers={"x-csrf-token": await _csrf(client)})
    assert r.status_code == 201, r.text
    state = await kill_switch.get_state()
    assert state["active"] is False
