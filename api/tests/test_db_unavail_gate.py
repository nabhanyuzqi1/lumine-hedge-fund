"""[AUDIT-SEV t_b827af0c] SEV-2 db_unavailable palsu dari PoolTimeout.

Insiden 26 Nov 2026 01:22 & 01:44 WIB: satu `PoolTimeout: couldn't get a
connection after 10.00 sec` (pool habis karena busy-loop /bridge/poll)
mengaktifkan kill-switch STOP_NEW_ORDERS padahal Postgres sehat (13/100
koneksi). Kill-switch hanya lepas lewat /resume manual -> order diblokir
berjam-jam.

Kontrak yang diuji di sini:
  A. Halt db_unavailable hanya bila (i) probe langsung ke Postgres GAGAL,
     ATAU (ii) >=2 pemeriksaan pool gagal BERTURUT-TURUT. Satu PoolTimeout
     tidak pernah cukup; streak reset begitu ada pemeriksaan sukses.
  B/C. Koneksi pool tidak lagi ditahan selama panggilan HTTP (collect_extras
     makro, LLM) -> tidak ada `idle in transaction` dari siklus agent.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import psycopg
import pytest

from app import config, db, kill_switch
from app import llm_agent_loop, metrics as metrics_mod
from app.metrics import (
    DbUnavailTracker,
    collect_metrics,
    evaluate_sev,
    probe_db_direct,
)

POOL_TIMEOUT_ERR = "PoolTimeout: couldn't get a connection after 10.00 sec"


def healthy() -> dict:
    """Metrics minimal sehat (rule lain di bawah ambang)."""
    return {
        "db": {"available": True, "connections": 10, "max_connections": 100},
        "ea": {"last_seen_age_s": 4.0, "offline_threshold_s": 60},
        "risk": {"unprotected_positions": [], "open_positions": 0,
                 "consecutive_failed": 0, "daily_drawdown_pct": 0.1,
                 "total_drawdown_pct": 0.2},
        "reconciliation": {"mismatch_24h": 0, "orphan_24h": 0,
                           "new": {"mismatch_new": 0, "orphan_new": 0}},
        "audit": {"admin_lockouts_new": 0},
        "latency": {"t0_t2_ms": {"p95": 0.05, "n": 10}},
        "spread": {"XAUUSD": {"p95_1h": 0.30, "p50_1h": 0.20}},
        "feed": {"candles": {"XAUUSD:M5": {"age_s": 60.0}}, "gaps_1h": {}},
        "orders": {"stuck_sent_60s": 0, "failure_rate_24h": 0.0,
                   "terminal_24h": 10, "failed_24h": 0},
        "host": {"disk_root_pct": 50.0, "disk_home_pct": 50.0},
        "backup": {"age_s": 3600.0},
        "strategies": {"runners": {"runner": {"paper_state_age_s": 30.0}}},
    }


def pool_timeout_metrics() -> dict:
    """Pool habis, Postgres masih sehat (probe langsung berhasil)."""
    return {"db": {"available": False, "error": POOL_TIMEOUT_ERR,
                   "probe_ok": True, "probe_error": None}}


def db_dead_metrics() -> dict:
    """Postgres benar-benar tidak dapat dihubungi (probe langsung gagal)."""
    return {"db": {"available": False,
                   "error": "OperationalError: connection failed",
                   "probe_ok": False,
                   "probe_error": "OperationalError: connection refused"}}


def _idle_in_transaction() -> int:
    """Jumlah sesi DB yang `idle in transaction` (koneksi uji, di luar pool)."""
    with psycopg.connect(config.DATABASE_URL, connect_timeout=3) as conn:
        row = conn.execute(
            """
            SELECT count(*) FROM pg_stat_activity
            WHERE datname = current_database()
              AND state = 'idle in transaction'
              AND pid <> pg_backend_pid()
            """
        ).fetchone()
    return int(row[0])


# ---------------------------------------------------------------- A: evaluator

def test_evaluate_sev_pool_timeout_has_no_halt_mode():
    m = healthy()
    m.update(pool_timeout_metrics())
    alerts = evaluate_sev(m)
    assert [a["key"] for a in alerts] == ["db_unavailable"]
    assert alerts[0]["sev"] == 2
    # pool timeout != DB mati -> tidak boleh memblokir order
    assert alerts[0]["action_mode"] is None
    assert "BERHASIL" in alerts[0]["what"]


def test_evaluate_sev_db_dead_has_halt_mode():
    m = healthy()
    m.update(db_dead_metrics())
    a = evaluate_sev(m)[0]
    assert a["action_mode"] == "STOP_NEW_ORDERS"
    assert "GAGAL" in a["what"]


# ---------------------------------------------------------------- A/D: tracker

def test_tracker_single_pool_timeout_does_not_activate():
    tr = DbUnavailTracker(min_streak=2)
    v = tr.observe(pool_timeout_metrics()["db"])
    assert v["activate"] is False
    assert v["streak"] == 1
    assert "transient" in v["reason"]


def test_tracker_streak_resets_on_success():
    tr = DbUnavailTracker(min_streak=2)
    assert tr.observe(pool_timeout_metrics()["db"])["activate"] is False
    v = tr.observe({"available": True})
    assert v["activate"] is False and v["streak"] == 0
    # kegagalan setelah pulih mulai dari 1 lagi -> tidak pernah menumpuk
    v = tr.observe(pool_timeout_metrics()["db"])
    assert v["activate"] is False and v["streak"] == 1


def test_tracker_two_consecutive_pool_timeouts_activate():
    tr = DbUnavailTracker(min_streak=2)
    assert tr.observe(pool_timeout_metrics()["db"])["activate"] is False
    v = tr.observe(pool_timeout_metrics()["db"])
    assert v["activate"] is True and v["streak"] == 2


def test_tracker_probe_failure_activates_on_first_check():
    tr = DbUnavailTracker(min_streak=2)
    v = tr.observe(db_dead_metrics()["db"])
    assert v["activate"] is True and v["streak"] == 1
    assert v["probe_ok"] is False


# ---------------------------------------------------------------- B: probe DB

async def test_probe_db_direct_ok(client):
    probe = await probe_db_direct()
    assert probe["ok"] is True
    assert probe["latency_ms"] is not None and probe["error"] is None


async def test_probe_db_direct_reports_dead_db(client, monkeypatch):
    monkeypatch.setattr(config, "DATABASE_URL",
                        "postgresql://fund2:wrong@127.0.0.1:1/fund2")
    probe = await probe_db_direct(timeout_s=2)
    assert probe["ok"] is False
    assert probe["error"]


async def test_collect_metrics_pool_timeout_probe_ok(client, monkeypatch):
    """PoolTimeout saat collect: probe langsung membuktikan DB sehat."""
    from psycopg_pool import PoolTimeout

    def dead_pool():
        raise PoolTimeout(POOL_TIMEOUT_ERR)

    monkeypatch.setattr(metrics_mod.db, "pool", dead_pool)
    m = await collect_metrics()
    assert m["db"]["available"] is False
    assert m["db"]["probe_ok"] is True
    a = evaluate_sev(m)[0]
    assert a["key"] == "db_unavailable" and a["action_mode"] is None


# ---------------------------------------------------------------- D: watchdog

async def test_sev_watch_single_pool_timeout_no_halt(client, fake_tg, monkeypatch):
    """DoD-D: simulasi PoolTimeout 1x -> kill-switch TIDAK aktif."""
    m_bad = healthy()
    m_bad.update(pool_timeout_metrics())
    state = {"n": 0}

    async def fake_collect(window_s=90.0):
        state["n"] += 1
        # iterasi pertama: pool timeout; sisanya sehat (DB pulih)
        return m_bad if state["n"] == 1 else healthy()

    monkeypatch.setattr(metrics_mod, "collect_metrics", fake_collect)
    monkeypatch.setattr(metrics_mod, "SEV_CHECK_INTERVAL_S", 0.01)
    stop = asyncio.Event()
    task = asyncio.create_task(metrics_mod.sev_watch_loop(stop))
    try:
        await asyncio.sleep(0.2)
        stop.set()
        await asyncio.wait_for(task, timeout=5)
    finally:
        if not task.done():
            task.cancel()
    ks = await kill_switch.get_state()
    assert ks["active"] is False, ks
    assert metrics_mod.DB_UNAVAIL_TRACKER.streak == 0
    sent = " ".join(c["params"].get("text", "") for c in fake_tg)
    # status di pesan Telegram: jelas menyebut halt TIDAK diaktifkan
    assert "TIDAK mengaktifkan" in sent
    assert "Timeout pool bukan bukti database mati" in sent


async def test_sev_watch_two_consecutive_pool_timeouts_halts(client, fake_tg, monkeypatch):
    """DoD-D: 2x berturut-turut -> kill-switch aktif (eskalasi)."""
    m_bad = healthy()
    m_bad.update(pool_timeout_metrics())

    async def fake_collect(window_s=90.0):
        return m_bad

    monkeypatch.setattr(metrics_mod, "collect_metrics", fake_collect)
    monkeypatch.setattr(metrics_mod, "SEV_CHECK_INTERVAL_S", 0.01)
    stop = asyncio.Event()
    task = asyncio.create_task(metrics_mod.sev_watch_loop(stop))
    try:
        await asyncio.sleep(0.2)
        stop.set()
        await asyncio.wait_for(task, timeout=5)
    finally:
        if not task.done():
            task.cancel()
    ks = await kill_switch.get_state()
    assert ks["active"] is True and ks["mode"] == "STOP_NEW_ORDERS", ks
    assert ks["source"] == "auto:sev_db_unavailable"
    assert metrics_mod.DB_UNAVAIL_TRACKER.streak >= 2


async def test_sev_watch_dead_db_halts_on_first_check(client, fake_tg, monkeypatch):
    """DoD-D: DB benar-benar mati -> halt pada pemeriksaan pertama."""
    m_bad = healthy()
    m_bad.update(db_dead_metrics())

    async def fake_collect(window_s=90.0):
        return m_bad

    monkeypatch.setattr(metrics_mod, "collect_metrics", fake_collect)
    # interval besar -> hanya SATU iterasi yang jalan sebelum stop
    monkeypatch.setattr(metrics_mod, "SEV_CHECK_INTERVAL_S", 30.0)
    stop = asyncio.Event()
    task = asyncio.create_task(metrics_mod.sev_watch_loop(stop))
    try:
        await asyncio.sleep(0.2)
        stop.set()
        await asyncio.wait_for(task, timeout=5)
    finally:
        if not task.done():
            task.cancel()
    ks = await kill_switch.get_state()
    assert ks["active"] is True and ks["mode"] == "STOP_NEW_ORDERS", ks
    assert metrics_mod.DB_UNAVAIL_TRACKER.streak == 1


# ---------------------------------------------------------------- C: tz cache

async def test_db_tz_offset_cached_between_cycles(client, monkeypatch):
    """Offset tz tidak berubah tiap siklus -> query hanya sekali (cache)."""
    llm_agent_loop._DB_TZ_CACHE.update({"value": None, "at": 0.0})
    calls = {"n": 0}
    real_fetchone = llm_agent_loop.fetchone

    async def counting_fetchone(conn, sql, params=()):
        if "current_setting" in sql:
            calls["n"] += 1
        return await real_fetchone(conn, sql, params)

    monkeypatch.setattr(llm_agent_loop, "fetchone", counting_fetchone)
    async with db.pool().connection() as conn:
        first = await llm_agent_loop._db_tz_offset_h(conn)
        second = await llm_agent_loop._db_tz_offset_h(conn)
    assert first == second
    assert calls["n"] == 1


# ------------------------------------------------- D: siklus agent tanpa tx

async def test_run_cycle_does_not_hold_connection_during_http(client, monkeypatch):
    """Regresi t_b827af0c: saat collect_extras (HTTP) dan panggilan LLM
    berjalan, tidak boleh ada koneksi yang tertinggal `idle in transaction`."""
    seen: dict = {}
    now = datetime.now(timezone.utc)

    async def fake_extras(now_):
        # HTTP makro: ukur dari koneksi TERPISAH (di luar pool)
        seen["during_extras"] = await asyncio.to_thread(_idle_in_transaction)
        return {}

    async def fake_call_llm(http, ctx, **kwargs):
        seen["during_llm"] = await asyncio.to_thread(_idle_in_transaction)
        return {"kind": "hold", "symbol": None, "side": None, "volume": None,
                "sl": None, "tp": None, "reasoning": "uji", "confidence": 0.0}

    async def noop(*args, **kwargs):
        return None

    monkeypatch.setattr(llm_agent_loop, "_collect_extras_safe", fake_extras)
    monkeypatch.setattr(llm_agent_loop, "_call_llm", fake_call_llm)
    monkeypatch.setattr(llm_agent_loop, "_post_cycle", noop)
    monkeypatch.setattr(llm_agent_loop, "_submit_decision", noop)

    async def fake_preflight(http, auth, cycle_id, symbols):
        # t_afd7fe4e: gate pre-flight wajib dilalui sebelum LLM; tes ini fokus
        # pada koneksi pool, jadi gate dipatok lolos.
        return {"ok": True, "allowed": list(symbols), "blocked": [], "reason": None}

    monkeypatch.setattr(llm_agent_loop, "_preflight", fake_preflight)
    # t_2a1fbf01: default produksi = pipeline paralel (specialist + synthesizer).
    # Tes ini menguji kontrak lama "tidak ada koneksi tertahan saat HTTP", jadi
    # jalur yang dipakai dipatok ke satu-prompt; jalur paralel diuji di
    # test_llm_parallel_pipeline.py.
    monkeypatch.setattr(llm_agent_loop.llm_models, "resolve", lambda settings: {
        "parallel": False, "specialist": "m", "synth": "m", "fallback": "m"})

    ctx = await llm_agent_loop.run_cycle(object(), {"token": "x"}, "cycle-test")
    assert ctx["now_utc"]
    assert seen["during_extras"] == 0, seen
    assert seen["during_llm"] == 0, seen
    # setelah siklus: tidak ada transaksi tertinggal
    assert await asyncio.to_thread(_idle_in_transaction) == 0


async def test_collect_context_uses_provided_extras(client, monkeypatch):
    """Jalur produksi: makro yang sudah diambil di luar blok koneksi dipakai
    apa adanya (collect_extras TIDAK dipanggil lagi di dalam transaksi)."""
    called = {"n": 0}

    async def should_not_be_called(now):
        called["n"] += 1
        raise AssertionError("collect_extras dipanggil di dalam blok koneksi")

    monkeypatch.setattr(llm_agent_loop, "collect_extras", should_not_be_called)
    extras = {name: {"status": "unavailable", "reason": "uji",
                     "fetched_at": "2026-11-26T00:00:00+00:00",
                     "as_of": None, "source": name}
              for name in ("sentiment", "fundamental", "calendar")}
    async with db.pool().connection() as conn:
        ctx = await llm_agent_loop._collect_context(
            conn, extras=extras, now=datetime.now(timezone.utc))
    assert called["n"] == 0
    assert ctx["calendar"]["reason"] == "uji"
    assert set(ctx["symbols"]) == set(llm_agent_loop.SYMBOLS)
