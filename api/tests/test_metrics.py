"""Metrics & alerting SEV-1..SEV-4 (PRD v2.2 §20, t_f2v22a10).

Unit: evaluator murni (threshold -> severity -> alert actionable) + escaping
Markdown Telegram. Integration: collect_metrics di test DB + endpoint /metrics.
Tanpa kredensial Telegram produksi (conftest layer 4/5).
"""
from __future__ import annotations

import asyncio

import pytest

from app.metrics import (
    BACKUP_AGE_H,
    CANDLE_STALE_S,
    DB_CONN_PCT,
    DISK_PCT,
    DAILY_DD_WATCH_PCT,
    FAILED_RATE_WATCH,
    SPREAD_ABS_XAUUSD,
    T02_P95_MS,
    _median,
    _pct,
    collect_metrics,
    evaluate_sev,
    format_alert,
)


def healthy() -> dict:
    """Metrics dasar sehat: semua rule di bawah ambang."""
    return {
        "db": {"available": True, "connections": 10, "max_connections": 100},
        "ea": {"last_seen_age_s": 4.0, "offline_threshold_s": 60},
        "risk": {
            "unprotected_positions": [], "open_positions": 0,
            "consecutive_failed": 0, "daily_drawdown_pct": 0.1,
            "total_drawdown_pct": 0.2,
        },
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


def _keys(alerts):
    return [a["key"] for a in alerts]


# ---------------------------------------------------------------- helpers

def test_percentile_and_median():
    assert _pct([], 95) is None
    assert _median([]) is None
    assert _median([3.0, 1.0, 2.0]) == 2.0
    vals = list(range(1, 101))
    assert _pct(vals, 95) == 95
    assert _pct(vals, 50) == 50


# ---------------------------------------------------------------- evaluator: sehat

def test_healthy_no_alerts():
    assert evaluate_sev(healthy()) == []


def test_every_alert_has_actionable_fields():
    """PRD §20: apa, dampak, waktu, tindakan otomatis, langkah manual."""
    m = healthy()
    m["risk"]["unprotected_positions"] = [{"ticket_sym": "XAUUSD BUY 0.02"}]
    for a in evaluate_sev(m):
        assert a["what"] and a["impact"] and a["when"] and a["auto"]
        assert isinstance(a["manual"], list) and a["manual"]


# ---------------------------------------------------------------- SEV-1

def test_sev1_position_without_sl():
    m = healthy()
    m["risk"]["unprotected_positions"] = [
        {"ticket_sym": "XAUUSD BUY 0.02", "open_price": 3600.0}]
    m["risk"]["open_positions"] = 1
    alerts = evaluate_sev(m)
    assert _keys(alerts) == ["posisi_tanpa_sl"]
    assert alerts[0]["sev"] == 1
    assert alerts[0]["action_mode"] == "GLOBAL_HALT"
    assert "TANPA SL" in alerts[0]["what"]


def test_sev1_ledger_mismatch():
    m = healthy()
    m["reconciliation"]["new"]["mismatch_new"] = 1
    m["reconciliation"]["mismatch_24h"] = 1
    alerts = evaluate_sev(m)
    assert _keys(alerts) == ["ledger_mismatch"]
    assert alerts[0]["sev"] == 1 and alerts[0]["action_mode"] == "GLOBAL_HALT"


def test_sev1_unknown_order_orphan():
    m = healthy()
    m["reconciliation"]["new"]["orphan_new"] = 1
    alerts = evaluate_sev(m)
    assert _keys(alerts) == ["order_tak_diketahui"]
    assert alerts[0]["sev"] == 1


def test_sev1_admin_lockout():
    m = healthy()
    m["audit"]["admin_lockouts_new"] = 1
    alerts = evaluate_sev(m)
    assert _keys(alerts) == ["credential_compromise"]
    assert alerts[0]["sev"] == 1 and alerts[0]["action_mode"] == "GLOBAL_HALT"


# ---------------------------------------------------------------- SEV-2

def test_sev2_ea_offline_with_positions():
    m = healthy()
    m["ea"]["last_seen_age_s"] = 145.0
    m["risk"]["open_positions"] = 2
    alerts = evaluate_sev(m)
    assert _keys(alerts) == ["ea_offline"]
    assert alerts[0]["sev"] == 2
    assert alerts[0]["action_mode"] == "GLOBAL_HALT"


def test_sev3_ea_offline_without_positions():
    m = healthy()
    m["ea"]["last_seen_age_s"] = 145.0
    alerts = evaluate_sev(m)
    assert _keys(alerts) == ["ea_offline_tanpa_posisi"]
    assert alerts[0]["sev"] == 3 and alerts[0]["action_mode"] is None


def test_sev2_repeated_execution_failures():
    m = healthy()
    m["risk"]["consecutive_failed"] = 4
    alerts = evaluate_sev(m)
    assert _keys(alerts) == ["repeated_execution_failures"]
    assert alerts[0]["sev"] == 2
    assert alerts[0]["action_mode"] == "STOP_NEW_ORDERS"


def test_sev2_db_unavailable_short_circuits():
    m = healthy()
    m["db"] = {"available": False, "error": "OperationalError: koneksi"}
    alerts = evaluate_sev(m)
    assert _keys(alerts) == ["db_unavailable"]
    assert alerts[0]["sev"] == 2
    # rule lain tidak dinilai tanpa DB
    m["risk"]["unprotected_positions"] = [{"ticket_sym": "x"}]
    assert _keys(evaluate_sev(m)) == ["db_unavailable"]


# ---------------------------------------------------------------- SEV-3

def test_sev3_latency_slo_breach():
    m = healthy()
    m["latency"]["t0_t2_ms"] = {"p95": T02_P95_MS / 1000.0, "n": 10}
    alerts = evaluate_sev(m)
    assert _keys(alerts) == ["latensi_t02"]
    assert alerts[0]["sev"] == 3


def test_sev3_spread_xauusd_abs_btc_not():
    m = healthy()
    m["spread"] = {
        "XAUUSD": {"p95_1h": SPREAD_ABS_XAUUSD, "p50_1h": 0.4},
        "BTCUSD": {"p95_1h": 120.0, "p50_1h": 39.0},  # skala beda: tanpa ambang absolut
    }
    assert _keys(evaluate_sev(m)) == ["spread_tinggi"]
    a = evaluate_sev(m)[0]
    assert a["sev"] == 3 and "XAUUSD" in a["what"]


def test_sev3_feed_stale_and_data_gap():
    m = healthy()
    m["feed"]["candles"]["XAUUSD:M5"]["age_s"] = CANDLE_STALE_S + 1
    m["feed"]["gaps_1h"] = {"XAUUSD": {"count": 3, "max_gap_s": 95.0}}
    keys = _keys(evaluate_sev(m))
    assert keys == ["feed_stale", "data_gap"]
    assert all(a["sev"] == 3 for a in evaluate_sev(m))


def test_sev3_db_connections_and_disk():
    m = healthy()
    m["db"]["connections"] = int(DB_CONN_PCT)  # 80/100
    m["host"]["disk_root_pct"] = DISK_PCT
    keys = _keys(evaluate_sev(m))
    assert "db_connections" in keys and "disk_penuh" in keys


def test_sev3_backup_old_or_missing():
    m = healthy()
    m["backup"] = {"age_s": BACKUP_AGE_H * 3600 + 1}
    assert _keys(evaluate_sev(m)) == ["backup_age"]
    m["backup"] = {"age_s": None}
    assert _keys(evaluate_sev(m)) == ["backup_age"]


def test_sev3_drawdown_watch_below_halt():
    m = healthy()
    m["risk"]["daily_drawdown_pct"] = DAILY_DD_WATCH_PCT
    assert _keys(evaluate_sev(m)) == ["drawdown_watch"]
    # di atas watch tapi di bawah auto-halt 3% tetap SEV-3
    m["risk"]["daily_drawdown_pct"] = 2.0
    assert _keys(evaluate_sev(m)) == ["drawdown_watch"]


def test_sev3_stuck_failure_rate_paper_stale():
    m = healthy()
    m["orders"]["stuck_sent_60s"] = 1
    m["orders"]["failure_rate_24h"] = FAILED_RATE_WATCH
    m["orders"]["terminal_24h"] = 10
    m["strategies"]["runners"]["runner"]["paper_state_age_s"] = 901
    keys = _keys(evaluate_sev(m))
    assert keys == ["order_stuck", "failure_rate", "paper_runner_stale"]


def test_failure_rate_ignored_with_few_orders():
    m = healthy()
    m["orders"]["failure_rate_24h"] = 0.5
    m["orders"]["terminal_24h"] = 3  # < 5: rasio bermakna
    assert evaluate_sev(m) == []


# ---------------------------------------------------------------- format Telegram

def test_format_alert_escapes_markdown():
    """parse_mode Markdown: nilai dinamis harus lolos Telegram (insiden 23 Nov:
    underscore bikin entity tak tertutup -> 400 diam-diam)."""
    m = healthy()
    m["risk"]["unprotected_positions"] = [{"ticket_sym": "XAUUSD BUY 0.02"}]
    m["audit"]["admin_lockouts_new"] = 1
    m["reconciliation"]["new"]["mismatch_new"] = 1
    alerts = evaluate_sev(m)
    assert alerts  # 3 alert SEV-1
    for a in alerts:
        text = format_alert(a, test=True)
        # tanda markdown hanya boleh muncul ter-escape (\_, \[, \*)
        stripped = text.replace("\\_", "").replace("\\[", "").replace("\\]", "").replace("\\*", "").replace("\\`", "")
        assert not any(ch in stripped for ch in "_*`["), (a["key"], text)
        # kerangka actionable lengkap
        assert "Apa:" in text and "Dampak:" in text and "Waktu:" in text
        assert "Otomatis:" in text and "Manual:" in text
        assert "TEST" in text


def test_format_alert_prod_has_no_test_marker():
    m = healthy()
    m["risk"]["consecutive_failed"] = 3
    a = evaluate_sev(m)[0]
    assert "TEST" not in format_alert(a)


# ---------------------------------------------------------------- integration

async def test_collect_metrics_sections(client):
    """collect_metrics di test DB: seluruh section PRD §20.1 terisi."""
    m = await collect_metrics()
    assert m["db"]["available"] is True
    for section in ("api", "db", "host", "ea", "feed", "spread", "latency",
                    "orders", "reconciliation", "strategies", "risk", "backup",
                    "triggers", "audit"):
        assert section in m, section
    assert m["orders"]["state_counts"] == {}  # DB test kosong
    assert m["latency"]["t0_t2_ms"]["n"] == 0
    assert m["risk"]["open_positions"] == 0
    assert evaluate_sev(m) == []  # sistem sehat -> tanpa alert


async def test_metrics_endpoint_auth(client):
    """GET /metrics: 200 dengan session, 401 tanpa."""
    from httpx import ASGITransport, AsyncClient
    resp = await client.get("/metrics")
    assert resp.status_code == 200
    body = resp.json()
    assert body["db"]["available"] is True
    async with AsyncClient(transport=ASGITransport(app=client._transport.app),
                           base_url="http://test") as anon:
        r = await anon.get("/metrics")
        assert r.status_code == 401


async def test_sev_watch_loop_sends_on_transition(client, fake_tg, monkeypatch):
    """Jalur penuh evaluate -> format -> notify_owner pada transisi masalah.

    fake_tg (conftest) mengganti tg_api; loop dipanggil sekali dengan metrics
    tidak sehat SETELAH baseline sehat -> alert SEV-1 terkirim + auto-action
    kill-switch GLOBAL_HALT menyala (di DB test).
    """
    from app import kill_switch, metrics as metrics_mod

    m = healthy()
    m["risk"]["unprotected_positions"] = [{"ticket_sym": "XAUUSD BUY 0.02"}]
    m["risk"]["open_positions"] = 1

    async def fake_collect(window_s=90.0):
        return m

    monkeypatch.setattr(metrics_mod, "collect_metrics", fake_collect)
    monkeypatch.setattr(metrics_mod, "SEV_CHECK_INTERVAL_S", 0.01)
    stop = asyncio.Event()
    task = asyncio.create_task(metrics_mod.sev_watch_loop(stop))
    try:
        await asyncio.sleep(0.15)  # baseline + >=1 iterasi berikutnya
        stop.set()
        await asyncio.wait_for(task, timeout=5)
    finally:
        if not task.done():
            task.cancel()
    # baseline (iterasi 1, tanpa kirim) -> iterasi 2 alert SEV-1
    assert any("SEV-1" in c["params"]["text"] for c in fake_tg)
    sent = [c["params"]["text"] for c in fake_tg]
    assert any("posisi tanpa sl" in t.lower() or "POSISI TANPA SL" in t for t in sent)
    # auto-action: kill-switch GLOBAL_HALT di DB test
    state = await kill_switch.get_state()
    assert state["active"] is True and state["mode"] == "GLOBAL_HALT"
    assert state["source"] == "auto:sev_posisi_tanpa_sl"




# ── 26 Nov 2026: alarm palsu (gate rejection, runner pensiun, harness) ──

async def test_order_metrics_gate_rejection_bukan_kegagalan_eksekusi():
    """Rasio FAILED hanya menghitung kegagalan eksekusi pasar.

    Insiden 26 Nov 2026: alert SEV-3 "Rasio FAILED 40% (145/360)" padahal
    145/145 adalah penolakan risk gate (kill-switch + drawdown 25 Nov) dan
    nol kegagalan broker.
    """
    from app import db
    from datetime import datetime, timedelta, timezone
    import json as _json

    now = datetime.now(timezone.utc)
    async with db.pool().connection() as conn:
        for _ in range(8):
            row = await conn.execute(
                "INSERT INTO orders (symbol, side, volume, status, fail_reason, "
                "created_at) VALUES ('XAUUSD', 'BUY', 0.01, 'FAILED', "
                "'risk_gate_rejected: kill-switch aktif (stage=risk_gate)', %s) "
                "RETURNING id",
                (now - timedelta(hours=1),),
            )
            oid = (await row.fetchone())["id"]
            await conn.execute(
                "INSERT INTO order_events (order_id, from_status, to_status, payload) "
                "VALUES (%s, 'RECEIVED', 'FAILED', %s)",
                (oid, _json.dumps({"risk": "rejected",
                                   "fail": {"stage": "risk_gate"}})),
            )
        for _ in range(2):
            row = await conn.execute(
                "INSERT INTO orders (symbol, side, volume, status, fail_reason, "
                "created_at) VALUES ('XAUUSD', 'BUY', 0.01, 'FAILED', "
                "'OrderSend failed retcode=10018', %s) RETURNING id",
                (now - timedelta(hours=1),),
            )
            oid = (await row.fetchone())["id"]
            await conn.execute(
                "INSERT INTO order_events (order_id, from_status, to_status, payload) "
                "VALUES (%s, 'RECEIVED', 'FAILED', %s)",
                (oid, _json.dumps({"fail": {"stage": "execution"}})),
            )

    metrics = await collect_metrics()
    o = metrics["orders"]
    assert o["failed_risk_gate_24h"] >= 8
    assert o["failed_24h"] == 2, o
    assert o["failure_rate_24h"] <= 0.2, o


async def test_paper_runner_pensiun_tidak_memicu_alert_stale():
    """shadow_dbg & shadow_lb-replay-d0 sudah dipensiunkan: state-nya tua
    (2 hari) tapi tidak boleh jadi alert paper_runner_stale."""
    from app import db
    from datetime import datetime, timedelta, timezone

    old = datetime.now(timezone.utc) - timedelta(days=2)
    async with db.pool().connection() as conn:
        for key in ("shadow_dbg", "shadow_lb-replay-d0", "runner_hidup_test"):
            await conn.execute(
                "INSERT INTO paper_state (key, value, updated_at) VALUES (%s, %s, %s) "
                "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, "
                "updated_at = EXCLUDED.updated_at",
                (key, "{}" if key != "runner_hidup_test" else "{}", old),
            )
    metrics = await collect_metrics()
    strat = metrics["strategies"]
    assert "shadow_dbg" not in strat["runners"]
    assert "shadow_lb-replay-d0" not in strat["runners"]
    assert set(strat["retired_runners"]) >= {"shadow_dbg", "shadow_lb-replay-d0"}
    types = [a["key"] for a in evaluate_sev(metrics)]
    # runner hidup yang basi TETAP alert (kontrol positif)
    assert "paper_runner_stale" in types
    stale = [a for a in evaluate_sev(metrics) if a["key"] == "paper_runner_stale"]
    assert all("shadow_dbg" not in a["what"] and "replay-d0" not in a["what"]
               for a in stale)
