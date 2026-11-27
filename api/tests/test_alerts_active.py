"""Tests GET /alerts/active (PRD v2.2 §20.2/§21, task UI-D0).

Unit: helper active_alerts - field alert stabil {sev, key, what, impact,
since, source} dari evaluator SEV yang sama dengan sev_watch_loop.
Integration: endpoint di DB test sehat -> {alerts: []} (bukan 404),
auth 401 tanpa login, terdaftar di /openapi.json. Tanpa kredensial
Telegram produksi (conftest layer 4/5); helper tidak mengirim apa pun.
"""
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app import metrics as metrics_mod
from app.main import app


def healthy() -> dict:
    """Metrics dasar sehat: semua rule di bawah ambang (sama test_metrics)."""
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


# ---------------------------------------------------------------- unit

async def test_active_alerts_empty_when_healthy(monkeypatch):
    """Metrics sehat -> alerts [] dengan as_of + window_s terisi."""
    async def fake_collect(window_s=90.0):
        return {**healthy(), "window_s": window_s}

    monkeypatch.setattr(metrics_mod, "collect_metrics", fake_collect)
    out = await metrics_mod.active_alerts()
    assert out["alerts"] == []
    assert out["as_of"]
    assert out["window_s"] == 90.0


async def test_active_alerts_fields_stable(monkeypatch):
    """SEV-1 evaluator -> field stabil {sev, key, what, impact, since, source}."""
    m = healthy()
    m["risk"]["unprotected_positions"] = [{"ticket_sym": "XAUUSD BUY 0.02"}]
    m["risk"]["open_positions"] = 1

    async def fake_collect(window_s=90.0):
        return m

    monkeypatch.setattr(metrics_mod, "collect_metrics", fake_collect)
    out = await metrics_mod.active_alerts()
    assert len(out["alerts"]) == 1
    a = out["alerts"][0]
    assert set(a) == {"sev", "key", "what", "impact", "since", "source"}
    assert a["sev"] == 1
    assert a["key"] == "posisi_tanpa_sl"
    assert a["what"] and a["impact"] and a["since"] and a["source"]


async def test_active_alerts_no_writes(monkeypatch):
    """Read-only: helper tidak mengubah DB (hanya baca metrics)."""
    from app import db

    async def fake_collect(window_s=90.0):
        return healthy()

    monkeypatch.setattr(metrics_mod, "collect_metrics", fake_collect)
    async with db.pool().connection() as conn:
        cur = await conn.execute("SELECT COUNT(*) AS n FROM audit_log")
        before = (await cur.fetchone())["n"]
    await metrics_mod.active_alerts()
    async with db.pool().connection() as conn:
        cur = await conn.execute("SELECT COUNT(*) AS n FROM audit_log")
        after = (await cur.fetchone())["n"]
    assert after == before


# ---------------------------------------------------------------- integration

async def test_alerts_active_endpoint_empty(client, monkeypatch):
    """DB test sehat & kosong -> 200 + alerts [] (bukan 404).

    Backup age & disk di-stub supaya test hermetik (host tanpa JSON backup
    sukses memicu SEV-3 backup_age - drift lingkungan, bukan perilaku UI).
    """
    async def fake_backup_age():
        return {"age_s": 3600.0, "last": None}

    def fake_host():
        return {"disk_root_pct": 50.0, "disk_home_pct": 50.0}

    monkeypatch.setattr(metrics_mod, "_backup_age", fake_backup_age)
    monkeypatch.setattr(metrics_mod, "_host_metrics", fake_host)
    resp = await client.get("/alerts/active")
    assert resp.status_code == 200
    body = resp.json()
    assert body["alerts"] == []
    assert body["as_of"] and body["window_s"]


async def test_alerts_active_requires_auth(user):
    """Tanpa session cookie -> 401 (auth get_current_user)."""
    async with AsyncClient(transport=ASGITransport(app=app),
                           base_url="http://test") as anon:
        r = await anon.get("/alerts/active")
        assert r.status_code == 401


async def test_alerts_active_in_openapi(client):
    """DoD: endpoint terdaftar di /openapi.json."""
    resp = await client.get("/openapi.json")
    assert resp.status_code == 200
    assert "/alerts/active" in resp.json()["paths"]
