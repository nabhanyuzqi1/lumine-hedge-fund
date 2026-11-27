"""Risk gate & circuit breaker agent LLM (t_f2llm2).

Cakupan: rate limit LLM ketat (2/min, 20/hari) + cooldown, circuit
breaker (3 FAILED beruntun / drawdown harian > 1.5% -> pause + alert),
resume hanya owner (admin+2FA), kill-switch menolak order LLM, gate
umum tetap berlaku (SL wajib), dan simulasi runaway.
"""
from __future__ import annotations

import asyncio

import pytest
from httpx import ASGITransport, AsyncClient, HTTPStatusError, Request, Response

from app import db, kill_switch, llm_context_extras, market
from app.llm_risk import evaluate_llm_breaker, llm_order_stats
from app.main import app
from app.risk import DEFAULT_LLM_RISK, RiskContext, risk_gate

# Referensi fetch_calendar ASLI (sebelum fixture autouse mem-patch) untuk
# test fail-closed yang mengekspos chain _get_block sungguhan.
_REAL_FETCH_CALENDAR = llm_context_extras.fetch_calendar


def _ctx(**kw):
    """RiskContext untuk order LLM (pola test_risk.py) + field LLM."""
    settings = {
        "max_volume": 0.1, "max_daily_drawdown": 100.0, "max_spread": 0.50,
        "max_orders_per_min": 10, "halted": False, "kill_switch": False,
        "allowed_symbols": ["XAUUSD"],
        "symbol_specs": {"XAUUSD": {
            "contract_size": 100.0, "sl_min_usd": 0.50, "sl_max_usd": 50.0,
            "vol_max_lot": 1.0, "spread_abs_max_usd": 0.50,
        }},
        "exposure_max_usd": 107370.0, "risk_per_trade_pct": 0.5,
        "daily_start_balance": 10000.0, "llm_risk": {},
    }
    for key, value in kw.items():
        if key in settings:
            settings[key] = value
    defaults = dict(settings=settings, bid=1999.85, ask=2000.15, tick_age_s=0.1,
                    daily_pnl=0.0, orders_last_minute=0, is_llm=True)
    ctx_kw = {k: v for k, v in kw.items() if k not in settings}
    defaults.update(ctx_kw)
    return RiskContext(**defaults)


@pytest.fixture(autouse=True)
def _mock_calendar(monkeypatch):
    """Kalender difake ok/tanpa event untuk semua test di file ini.

    Gate blackout LLM aktif by default; tanpa mock, POST /orders strategy
    'llm' memukul feed kalender live (nfs.faireconomy.media), dan 429 dari
    feed -> fail-closed -> order yang mengharapkan 201 jadi 422
    (regresi terbukti di review t_d9e6b2a3). Test khusus calendar di
    test_llm_calendar_blackout.py punya mock sendiri.
    """

    async def _fake_calendar(now_utc=None):
        return {"status": "ok", "source": "test", "as_of": None, "events": []}

    monkeypatch.setattr(llm_context_extras, "fetch_calendar", _fake_calendar)


@pytest.fixture(autouse=True)
async def _reset_llm_settings(_clean_db):
    """Reset state LLM sebelum/sesudah tiap test.

    Tabel settings tidak di-TRUNCATE oleh _clean_db (bridge_token dan
    default lain harus bertahan), jadi settings khusus LLM di-reset di
    sini agar satu test tidak membawa pause/override ke test berikutnya.
    """
    await db.set_setting("llm_risk", dict(DEFAULT_LLM_RISK))
    await db.set_setting("llm_agent_pause", None)
    await db.set_setting("llm_breaker_ack", None)
    await db.set_setting("kill_switch_triggers", None)
    yield
    await db.set_setting("llm_agent_pause", None)
    await db.set_setting("llm_breaker_ack", None)
    await db.set_setting("kill_switch_triggers", None)


# ---------------------------------------------------------------- gate umum tetap berlaku
def test_llm_order_still_requires_sl_gate():
    """Order LLM melewati gate yang sama: SL wajib (G1) — level pure gate."""
    d = risk_gate(_order(sl=None), _ctx())
    assert not d.ok
    assert any("SL" in x for x in d.reasons)


def test_llm_order_passes_gate_when_within_limits():
    d = risk_gate(_order(), _ctx())
    assert d.ok, d.reasons


def test_partial_symbol_spec_fails_closed():
    """Spec parsial (key risk hilang) -> tidak bisa dibaca -> ditolak, bukan 500."""
    from app.risk import symbol_spec

    assert symbol_spec("XAUUSD", {"symbol_specs": {"XAUUSD": {
        "contract_size": 100.0}}}) is None
    d = risk_gate(_order(), _ctx(symbol_specs={"XAUUSD": {"contract_size": 100.0}}))
    assert not d.ok
    assert any("no risk spec" in x for x in d.reasons)


async def _tick():
    market.update_tick("XAUUSD", bid=1999.85, ask=2000.15)


async def _set_llm_risk(**kw):
    settings = await db.get_settings()
    cfg = dict(settings.get("llm_risk") or {})
    cfg.update(kw)
    await db.set_setting("llm_risk", cfg)


async def _events(action=None):
    async with db.pool().connection() as conn:
        if action:
            rows = await conn.execute(
                "SELECT action FROM kill_switch_events WHERE action = %s", (action,))
        else:
            rows = await conn.execute("SELECT action FROM kill_switch_events")
        return [r["action"] for r in await rows.fetchall()]


def _order(**kw):
    body = {"symbol": "XAUUSD", "side": "BUY", "volume": 0.01,
            "sl": 1998.0, "tp": 2005.0, "strategy": "llm"}
    body.update(kw)
    return body


@pytest.fixture
async def agent_client(user):
    """Client ter-login sebagai role 'agent' (service fund2-llm-agent)."""
    from app import auth

    async with db.pool().connection() as conn:
        await conn.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (%s, %s, 'agent')",
            ("svc-llm-agent", auth.hash_password("agentpass")),
        )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post("/auth/login",
                            json={"username": "svc-llm-agent", "password": "agentpass"})
        assert resp.status_code == 200, resp.text
        c.headers["x-csrf-token"] = resp.json()["csrf_token"]
        yield c


# ---------------------------------------------------------------- gate umum tetap berlaku
async def test_llm_order_still_requires_sl(client):
    """Order LLM melewati gate yang sama: SL wajib (G1) — level API (schema)."""
    await _tick()
    body = _order()
    body.pop("sl")
    r = await client.post("/orders", json=body)
    assert r.status_code == 422, r.text


async def test_ea_offline_blocks_llm_order(client, monkeypatch):
    """EA offline > ea_offline_block_s -> order LLM ditolak."""
    await _tick()
    monkeypatch.setattr(kill_switch, "ea_last_seen_age_s", lambda: 120.0)
    r = await client.post("/orders", json=_order())
    assert r.status_code == 422, r.text
    assert any("EA offline" in x for x in r.json()["rejected_reasons"])


# ---------------------------------------------------------------- rate limit LLM
async def test_runaway_burst_limited_to_2_per_minute(client):
    """Simulasi runaway: 10 order LLM bertubi-tubi -> hanya 2 diterima.

    Breaker dimatikan (consecutive_failed_pause besar) agar aserti
    presisi alasan penolakan: semuanya LLM order rate limit.
    """
    await _tick()
    await _set_llm_risk(max_orders_per_min=2, max_orders_per_day=20, cooldown_s=0,
                        consecutive_failed_pause=999)
    accepted = 0
    for _ in range(10):
        r = await client.post("/orders", json=_order())
        if r.status_code == 201:
            accepted += 1
        else:
            assert r.status_code == 422, r.text
            assert any("LLM order rate limit" in x
                       for x in r.json()["rejected_reasons"])
    assert accepted == 2


async def test_runaway_burst_trips_breaker(client):
    """Simulasi runaway dengan breaker default: burst dibatasi 2/min DAN
    agent otomatis di-pause setelah 3 penolakan beruntun."""
    await _tick()
    await _set_llm_risk(cooldown_s=0)
    accepted = 0
    rate_limited = paused = 0
    for _ in range(10):
        r = await client.post("/orders", json=_order())
        if r.status_code == 201:
            accepted += 1
        else:
            reasons = r.json()["rejected_reasons"]
            rate_limited += any("LLM order rate limit" in x for x in reasons)
            paused += any("LLM agent paused" in x for x in reasons)
    assert accepted == 2
    # Rate limit menahan burst; breaker TIDAK menyala karena penolakan gate
    # risiko bukan kegagalan eksekusi (lihat test_three_failed_...).
    assert rate_limited >= 1
    assert paused == 0
    settings = await db.get_settings()
    assert (settings.get("llm_agent_pause") or {}).get("active") is not True


async def test_daily_limit_rejects_order(client):
    await _tick()
    await _set_llm_risk(max_orders_per_min=10, max_orders_per_day=3, cooldown_s=0,
                        consecutive_failed_pause=999)
    for _ in range(3):
        r = await client.post("/orders", json=_order())
        assert r.status_code == 201, r.text
    r = await client.post("/orders", json=_order())
    assert r.status_code == 422, r.text
    assert any("LLM daily order limit" in x
               for x in r.json()["rejected_reasons"])


async def test_cooldown_after_accepted_order(client):
    await _tick()
    await _set_llm_risk(max_orders_per_min=10, max_orders_per_day=20, cooldown_s=300,
                        consecutive_failed_pause=999)
    r = await client.post("/orders", json=_order())
    assert r.status_code == 201, r.text
    r = await client.post("/orders", json=_order())
    assert r.status_code == 422, r.text
    assert any("LLM cooldown active" in x
               for x in r.json()["rejected_reasons"])


async def test_calendar_feed_429_fails_closed_llm_only(client, monkeypatch, tmp_path):
    """Feed kalender HTTP 429 -> order LLM 422 dgn alasan
    calendar_unavailable (fail-closed); order manual (strategy != llm)
    tidak dievaluasi gate-nya dan tetap 201."""

    async def _boom(now_utc, http):
        raise HTTPStatusError(
            "Client error '429 Too Many Requests'",
            request=Request("GET", "https://nfs.faireconomy.media/ff_calendar_thisweek.json"),
            response=Response(429),
        )

    # 429 di level raw fetcher: kontrak _get_block = tidak pernah raise,
    # error dikonversi jadi envelope status 'unavailable' -> fail-closed.
    # Cache disk harus diisolasi: tanpa ini blok "stale" hasil pemakaian nyata
    # dipakai ulang sehingga 429 tidak terbaca sebagai unavailable (test flaky
    # tergantung isi ~/.cache mesin).
    monkeypatch.setattr(llm_context_extras, "_CACHE_DIR",
                        str(tmp_path / "extras-cache"))
    monkeypatch.setattr(llm_context_extras, "_fetch_calendar", _boom)
    monkeypatch.setattr(llm_context_extras, "_CACHE",
                        {k: v for k, v in llm_context_extras._CACHE.items()
                         if k != "calendar"})
    # pakai fetch_calendar asli (fixture autouse mem-patch dgn versi fake)
    monkeypatch.setattr(llm_context_extras, "fetch_calendar",
                        _REAL_FETCH_CALENDAR)
    await _tick()
    r = await client.post("/orders", json=_order())
    assert r.status_code == 422, r.text
    assert any("calendar_unavailable" in x for x in r.json()["rejected_reasons"])
    # order manual (role admin, strategy bukan llm) tidak lolos gate kalender
    r = await client.post("/orders", json=_order(strategy="manual"))
    assert r.status_code == 201, r.text


async def test_close_orders_do_not_consume_quota(user):
    """Order CLOSE (penutupan posisi) tidak dihitung rate limit."""
    async with db.pool().connection() as conn:
        for _ in range(25):
            await conn.execute(
                "INSERT INTO orders (symbol, side, volume, strategy, action, status) "
                "VALUES ('XAUUSD', 'BUY', 0.01, 'llm', 'CLOSE', 'FILLED')")
        stats = await llm_order_stats(conn, await db.get_settings())
    assert stats["last_minute"] == 0
    assert stats["today"] == 0


# ---------------------------------------------------------------- circuit breaker
async def test_three_failed_pauses_agent_and_alerts(client, monkeypatch):
    """3 order LLM FAILED beruntun -> agent di-pause + alert Telegram."""
    await _tick()
    alerts = []

    async def fake_notify(msg):
        alerts.append(msg)

    # breaker meng-import notify_owner langsung dari telegram_bot
    monkeypatch.setattr("app.telegram_bot.notify_owner", fake_notify)
    await _set_llm_risk(consecutive_failed_pause=3)
    # Kegagalan EKSEKUSI (bukan penolakan gate) yang harus memicu breaker:
    # penolakan gate risiko berarti gate bekerja, bukan agent rusak.
    async with db.pool().connection() as conn:
        async with conn.cursor() as cur:
            for _ in range(3):
                await cur.execute(
                    "INSERT INTO orders (symbol, side, volume, strategy, status, "
                    "fail_reason, created_at) VALUES ('XAUUSD', 'BUY', 0.01, 'llm', "
                    "'FAILED', 'bridge: EA tidak menjawab', now()) "
                    "RETURNING id")
                order_id = (await cur.fetchone())["id"]
                await cur.execute(
                    "INSERT INTO order_events (order_id, from_status, to_status, payload) "
                    "VALUES (%s, 'RISK_PASS', 'FAILED', %s)",
                    (order_id, '{"fail": {"stage": "execution", "code": "bridge", '
                               '"message": "EA tidak menjawab"}}'))
    await evaluate_llm_breaker(notify=True)

    settings = await db.get_settings()
    pause = settings.get("llm_agent_pause")
    assert pause and pause["active"] is True
    assert "FAILED" in pause["reason"]
    assert "AGENT_PAUSE" in await _events("AGENT_PAUSE")
    assert alerts and "LLM AGENT PAUSED" in alerts[0]

    # order berikutnya ditolak karena agent di-pause
    r = await client.post("/orders", json=_order())
    assert r.status_code == 422, r.text
    assert any("LLM agent paused" in x for x in r.json()["rejected_reasons"])


async def test_drawdown_over_1_5_pct_pauses_agent(user):
    """Drawdown hari ini >= ambang Ops -> breaker pause agent.

    AUDIT-A2: ambang dibaca dari kill_switch_triggers.daily_drawdown_pct
    (bukan default terpisah 1.5% di kode breaker).
    """
    await db.set_setting("daily_start_balance", 10000)
    await db.set_setting("kill_switch_triggers", {"daily_drawdown_pct": 1.5})
    async with db.pool().connection() as conn:
        await conn.execute(
            "INSERT INTO positions (ticket, symbol, side, volume, open_price, "
            "close_price, profit, status, close_time) "
            "VALUES (9001, 'XAUUSD', 'BUY', 1.0, 2000, 1980, -200, 'CLOSED', now())")
        fired = await evaluate_llm_breaker(conn=conn)
    assert any(f["trigger"] == "daily_drawdown" for f in fired)
    settings = await db.get_settings()
    assert settings["llm_agent_pause"]["active"] is True
    assert "AGENT_PAUSE" in await _events("AGENT_PAUSE")


async def test_paused_agent_cannot_order(client):
    await db.set_setting(
        "llm_agent_pause",
        {"active": True, "reason": "unit test", "source": "auto:llm_breaker",
         "actor": "auto", "activated_at": "2026-01-01T00:00:00+00:00"})
    await _tick()
    r = await client.post("/orders", json=_order())
    assert r.status_code == 422, r.text
    assert any("LLM agent paused" in x for x in r.json()["rejected_reasons"])


# ---------------------------------------------------------------- resume owner-only
async def test_resume_requires_2fa(client, agent_client):
    """Admin tanpa 2FA dan role agent sama-sama ditolak (403)."""
    r = await client.post("/llm-agent/resume")
    assert r.status_code == 403, r.text
    r = await agent_client.post("/llm-agent/resume")
    assert r.status_code == 403, r.text


async def test_resume_owner_2fa_clears_pause(client_2fa):
    await db.set_setting(
        "llm_agent_pause",
        {"active": True, "reason": "unit test", "source": "auto:llm_breaker",
         "actor": "auto", "activated_at": "2026-01-01T00:00:00+00:00"})
    r = await client_2fa.post("/llm-agent/resume")
    assert r.status_code == 200, r.text
    assert r.json()["pause"]["active"] is False
    settings = await db.get_settings()
    assert not settings["llm_agent_pause"]["active"]
    assert "AGENT_RESUME" in await _events("AGENT_RESUME")
    # marker ack di-set agar streak FAILED lama tidak langsung memicu pause ulang
    ack = settings.get("llm_breaker_ack")
    assert ack and ack.get("failed_streak_after")
    # AUDIT-A: event resume menyimpan ambang efektif saat event tercatat
    async with db.pool().connection() as conn:
        rows = await conn.execute(
            "SELECT details FROM kill_switch_events WHERE action = 'AGENT_RESUME' "
            "ORDER BY id DESC LIMIT 1")
        ev = await rows.fetchone()
    assert (ev["details"].get("thresholds") or {}).get(
        "drawdown_pause_pct") == DEFAULT_LLM_RISK["drawdown_pause_pct"]


async def test_resume_event_records_transition_reason(client_2fa):
    """AGENT_RESUME mencatat alasan TRANSISI, bukan salinan alasan pause.

    Kasus historis: History menampilkan "AGENT_RESUME ... drawdown harian
    1.88% > 1.5%" (alasan PAUSE) untuk resume oleh owner. Event resume wajib
    menyebut aktor + kondisi saat resume; alasan pause lama tetap utuh di
    details.previous/previous_reason.
    """
    pause_reason = "drawdown harian 1.88% > 1.5%"
    await db.set_setting(
        "llm_agent_pause",
        {"active": True, "reason": pause_reason, "source": "auto:llm_breaker",
         "actor": "auto", "activated_at": "2026-01-01T00:00:00+00:00"})
    r = await client_2fa.post("/llm-agent/resume")
    assert r.status_code == 200, r.text

    async with db.pool().connection() as conn:
        rows = await conn.execute(
            "SELECT * FROM kill_switch_events WHERE action = 'AGENT_RESUME' "
            "ORDER BY id DESC LIMIT 1")
        ev = await rows.fetchone()
    assert ev["reason"] != pause_reason
    assert "resume manual oleh owner" in ev["reason"]
    assert "(tester)" in ev["reason"]
    assert "drawdown harian saat ini" in ev["reason"]
    assert ev["actor"] == "tester"
    assert ev["source"] == "dashboard"
    assert ev["details"]["previous"]["reason"] == pause_reason
    assert ev["details"]["previous_reason"] == pause_reason
    assert ev["details"]["resume_reason"] == ev["reason"]
    assert ev["details"]["from"]["agent_status"] == "PAUSED"
    assert ev["details"]["to"]["agent_status"] == "ACTIVE"
    assert ev["details"]["conditions"]["daily_drawdown_pct"] is not None


async def test_pause_event_records_trigger_reason_and_transition(client):
    """AGENT_PAUSE: reason = pemicu breaker, details from/to eksplisit."""
    await db.set_setting("llm_agent_pause", {"active": False})
    await db.set_setting("daily_start_balance", 10000)
    # AUDIT-A2: ambang drawdown hanya dari kunci Ops (default 3%, bukan
    # 1.5% lama) -> tetapkan eksplisit supaya rugi 2% tetap memicu.
    await db.set_setting("kill_switch_triggers", {"daily_drawdown_pct": 1.5})
    async with db.pool().connection() as conn:
        await conn.execute(
            "INSERT INTO positions (ticket, symbol, side, volume, open_price, "
            "close_price, profit, status, close_time) "
            "VALUES (9101, 'XAUUSD', 'BUY', 1.0, 2000, 1980, -200, 'CLOSED', now())")
        fired = await evaluate_llm_breaker(conn=conn)
        rows = await conn.execute(
            "SELECT * FROM kill_switch_events WHERE action = 'AGENT_PAUSE' "
            "ORDER BY id DESC LIMIT 1")
        ev = await rows.fetchone()
    assert fired
    assert "drawdown harian" in ev["reason"]
    assert ev["actor"] == "auto"
    assert ev["details"]["from"]["agent_status"] == "ACTIVE"
    assert ev["details"]["to"]["agent_status"] == "PAUSED"
    assert ev["details"]["previous"]["active"] is False


async def test_status_endpoint_reports_pause_and_quota(client):
    await _tick()
    r = await client.get("/llm-agent/status")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["pause"]["active"] is False
    assert data["llm_risk"]["max_orders_per_min"] == 2
    assert data["llm_risk"]["max_orders_per_day"] == 20
    assert "last_minute" in data["stats"]
    assert "failed_streak" in data["stats"]
    assert "daily_drawdown_pct" in data


# ---------------------------------------------------------------- kill-switch: agent berhenti
def _stub_db(settings_holder):
    class StubDB:
        async def init_pool(self):
            pass

        async def close_pool(self):
            pass

        def pool(self):
            raise AssertionError("pool tidak boleh dipakai saat blocked")

        async def get_settings(self):
            settings_holder["calls"] += 1
            settings_holder["stop"].set()
            return settings_holder["settings"]

    return StubDB()


async def _run_loop_once(monkeypatch, settings):
    from app import llm_agent_loop as loop_mod

    stop = asyncio.Event()
    holder = {"calls": 0, "stop": stop, "settings": settings}
    calls = {"login": 0, "llm": 0}

    async def fake_login(http):
        calls["login"] += 1
        return {"csrf": "x", "cookies": {}}

    async def fake_call_llm(http, ctx):
        calls["llm"] += 1
        return {"decision": {"kind": "hold"}, "raw_content": "",
                "model": "m", "prompt_tokens": 0, "completion_tokens": 0,
                "latency_ms": 0}

    monkeypatch.setattr(loop_mod, "db", _stub_db(holder))
    monkeypatch.setattr(loop_mod, "_login", fake_login)
    monkeypatch.setattr(loop_mod, "_call_llm", fake_call_llm)
    await asyncio.wait_for(loop_mod.agent_loop(stop), timeout=10)
    return calls


async def test_agent_loop_skips_when_kill_switch_active(monkeypatch, user):
    """Kill-switch aktif -> agent tidak login, tidak panggil LLM, tidak order."""
    calls = await _run_loop_once(monkeypatch, {
        "kill_switch": True, "llm_agent_pause": None, "halted": False,
        "llm_risk": {}})
    assert calls["login"] == 0
    assert calls["llm"] == 0


async def test_agent_loop_skips_when_paused(monkeypatch, user):
    """Agent di-pause breaker -> siklus di-skip penuh."""
    calls = await _run_loop_once(monkeypatch, {
        "kill_switch": False,
        "llm_agent_pause": {"active": True, "reason": "unit test",
                            "source": "auto:llm_breaker", "actor": "auto",
                            "activated_at": "2026-01-01T00:00:00+00:00"},
        "halted": False, "llm_risk": {}})
    assert calls["login"] == 0
    assert calls["llm"] == 0


async def test_kill_switch_rejects_llm_order_at_api(client):
    """Lapisan kedua: API juga menolak order LLM saat kill-switch aktif."""
    await _tick()
    await db.set_setting("kill_switch", True)
    r = await client.post("/orders", json=_order())
    assert r.status_code == 422, r.text
    assert any("kill-switch" in x.lower() for x in r.json()["rejected_reasons"])


# ── Breaker mengikuti Risk Ops (kill_switch_triggers) ──────────────────────

def test_breaker_thresholds_follow_kill_switch_triggers():
    """Ambang breaker agent LLM diturunkan dari Risk Ops (kill_switch_triggers).

    Owner menaikkan DD harian ke 10% & total 15% di halaman Ops -> breaker
    agent ikut memakai 10%, bukan lagi default/override lama 1.5%.
    """
    from app.llm_risk import get_llm_risk

    settings = {
        "llm_risk": {"drawdown_pause_pct": 1.5, "consecutive_failed_pause": 3},
        "kill_switch_triggers": {
            "daily_drawdown_pct": 10.0, "total_drawdown_pct": 15.0,
            "ea_offline_seconds": 90, "consecutive_failed_orders": 4,
        },
    }
    cfg = get_llm_risk(settings)
    assert cfg["drawdown_pause_pct"] == 10.0
    assert cfg["consecutive_failed_pause"] == 4
    assert cfg["ea_offline_block_s"] == 90.0
    # Batas non-breaker tidak terpengaruh
    assert cfg["max_orders_per_min"] == DEFAULT_LLM_RISK["max_orders_per_min"]
    assert cfg["max_orders_per_day"] == DEFAULT_LLM_RISK["max_orders_per_day"]
    assert cfg["cooldown_s"] == DEFAULT_LLM_RISK["cooldown_s"]


def test_breaker_ignores_invalid_trigger_values():
    """Trigger Risk Ops tidak valid/absen -> ambang default dipakai (fail-open)."""
    from app.llm_risk import get_llm_risk

    settings = {
        "kill_switch_triggers": {"daily_drawdown_pct": "bukan-angka",
                                 "consecutive_failed_orders": None},
    }
    cfg = get_llm_risk(settings)
    assert cfg["drawdown_pause_pct"] == DEFAULT_LLM_RISK["drawdown_pause_pct"]
    assert cfg["consecutive_failed_pause"] == DEFAULT_LLM_RISK["consecutive_failed_pause"]


def test_breaker_without_triggers_settings_uses_defaults():
    """Tanpa kill_switch_triggers sama sekali -> perilaku lama (default)."""
    from app.llm_risk import get_llm_risk

    cfg = get_llm_risk({"llm_risk": {}})
    assert cfg == DEFAULT_LLM_RISK


# ── Unit _apply_breaker_triggers (AUDIT-A t_7ae3e57a) ──────────────────────

def test_apply_breaker_triggers_valid_override():
    """Override valid dari Risk Ops diterapkan per key (float conversion)."""
    from app.llm_risk import _apply_breaker_triggers

    out = _apply_breaker_triggers(dict(DEFAULT_LLM_RISK), {"kill_switch_triggers": {
        "daily_drawdown_pct": 2.5, "consecutive_failed_orders": 5,
        "ea_offline_seconds": 120}})
    assert out["drawdown_pause_pct"] == 2.5
    assert out["consecutive_failed_pause"] == 5
    assert out["ea_offline_block_s"] == 120.0
    # Key non-breaker tidak tersentuh
    assert out["cooldown_s"] == DEFAULT_LLM_RISK["cooldown_s"]


def test_apply_breaker_triggers_invalid_values_fail_open_per_key():
    """Nilai invalid (string/None/dict) -> key itu fail-open ke default."""
    from app.llm_risk import _apply_breaker_triggers

    out = _apply_breaker_triggers(dict(DEFAULT_LLM_RISK), {"kill_switch_triggers": {
        "daily_drawdown_pct": "bukan-angka", "consecutive_failed_orders": None,
        "ea_offline_seconds": {"rusak": True}}})
    assert out == DEFAULT_LLM_RISK


def test_apply_breaker_triggers_missing_or_non_dict_uses_defaults():
    """kill_switch_triggers absen / None / bukan dict -> default penuh."""
    from app.llm_risk import _apply_breaker_triggers

    base = dict(DEFAULT_LLM_RISK)
    assert _apply_breaker_triggers(dict(base), {}) == base
    assert _apply_breaker_triggers(dict(base), {"kill_switch_triggers": None}) == base
    assert _apply_breaker_triggers(dict(base), {"kill_switch_triggers": "rusak"}) == base


# ── Integrasi E2E: PUT /kill-switch/triggers -> breaker (AUDIT-A) ──────────

async def test_breaker_follows_risk_ops_threshold_e2e(client_2fa):
    """Path E2E penuh: PUT /kill-switch/triggers (daily_drawdown_pct=3.0) ->
    db.get_settings -> evaluate_llm_breaker -> _evaluate_triggers.

    DD 1.88% (kasus historis) di atas default 1.5% tapi di bawah parameter
    Risk Ops 3% -> TIDAK fired. DD > 3% -> fired dengan detail memakai
    parameter (bukan 1.5), dan event AGENT_PAUSE menyimpan details.thresholds
    = cfg efektif saat event tercatat.
    """
    await db.set_setting("daily_start_balance", 10000)
    r = await client_2fa.put("/kill-switch/triggers",
                             json={"password": "testpass", "daily_drawdown_pct": 3.0})
    assert r.status_code == 200, r.text
    assert r.json()["triggers"]["daily_drawdown_pct"] == 3.0

    # DD 1.88%: di bawah parameter 3% -> tidak fired walau > default 1.5%
    async with db.pool().connection() as conn:
        await conn.execute(
            "INSERT INTO positions (ticket, symbol, side, volume, open_price, "
            "close_price, profit, status, close_time) "
            "VALUES (9002, 'XAUUSD', 'BUY', 1.0, 2000, 1981.2, -188, "
            "'CLOSED', now())")
        assert await evaluate_llm_breaker(conn=conn) == []
    settings = await db.get_settings()
    assert not (settings.get("llm_agent_pause") or {}).get("active")

    # Total DD 5.38% > parameter 3% -> fired, detail memakai parameter
    async with db.pool().connection() as conn:
        await conn.execute(
            "INSERT INTO positions (ticket, symbol, side, volume, open_price, "
            "close_price, profit, status, close_time) "
            "VALUES (9003, 'XAUUSD', 'BUY', 1.0, 2000, 1965.0, -350, "
            "'CLOSED', now())")
        fired = await evaluate_llm_breaker(conn=conn)
    dd = next(f for f in fired if f["trigger"] == "daily_drawdown")
    assert "5.38% >= 3.0%" in dd["detail"]
    assert "1.5" not in dd["detail"]
    settings = await db.get_settings()
    assert settings["llm_agent_pause"]["active"] is True

    # Audit trail: threshold efektif tersimpan di details.thresholds
    async with db.pool().connection() as conn:
        rows = await conn.execute(
            "SELECT details FROM kill_switch_events WHERE action = 'AGENT_PAUSE' "
            "ORDER BY id DESC LIMIT 1")
        ev = await rows.fetchone()
    assert (ev["details"].get("thresholds") or {}).get("drawdown_pause_pct") == 3.0
    assert (ev["details"].get("thresholds") or {}).get(
        "consecutive_failed_pause") == DEFAULT_LLM_RISK["consecutive_failed_pause"]
