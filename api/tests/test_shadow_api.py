"""Tests read-only API shadow (PRD 9.2): hasil sinyal bisa dibaca owner,
tidak ada endpoint tulis di router shadow.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app import db
from shadow import store
from shadow.specs import params_hash


async def _seed_shadow_signal(conn, *, label="lb-api") -> str:
    run_id = await store.ensure_run(
        conn, strategy_id="london_breakout", strategy_version="1.0.0",
        label=label, symbol="XAUUSD", timeframe="5m",
        params_hash=params_hash({}), code_commit="api-test", config={})
    await store.insert_signal(
        conn, run_id=run_id, signal_ref="abc123",
        strategy_id="london_breakout", strategy_version="1.0.0", label=label,
        symbol="XAUUSD", timeframe="5m",
        ts=datetime(2026, 11, 24, 9, 30, 30, tzinfo=timezone.utc),
        ref_bid=1999.85, ref_ask=2000.15, spread=0.30, spread_median_15m=0.25,
        regime_label="RANGE", regime_confidence=0.8, side="BUY", volume=0.04,
        sl=1990.0, tp=2015.0, reason="api test", params_hash=params_hash({}),
        code_commit="api-test", sim_status="FILLED", sim_fill_price=2000.25,
        sim_cost_usd=1.28, detail={})
    return str(run_id)


async def test_shadow_api_runs_and_signals(client, _clean_db):
    async with db.pool().connection() as conn:
        run_id = await _seed_shadow_signal(conn)
    r = await client.get("/shadow/runs")
    assert r.status_code == 200, r.text
    runs = r.json()["runs"]
    assert any(str(x["run_id"]) == run_id for x in runs)
    r = await client.get(f"/shadow/runs/{run_id}/signals")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["is_simulation"] is True  # PRD 9.2: simulasi, bukan realized
    sigs = body["signals"]
    assert len(sigs) == 1
    s = sigs[0]
    assert float(s["ref_bid"]) == 1999.85 and float(s["ref_ask"]) == 2000.15
    assert float(s["spread"]) == 0.30 and s["regime_label"] == "RANGE"
    assert s["label"] == "lb-api" and s["sim_status"] == "FILLED"


async def test_shadow_api_requires_auth(_clean_db):
    from httpx import ASGITransport, AsyncClient
    from app.main import app
    async with AsyncClient(transport=ASGITransport(app=app),
                           base_url="http://test") as c:
        r = await c.get("/shadow/runs")
    assert r.status_code == 401


async def test_shadow_api_unknown_run_404(client, _clean_db):
    r = await client.get(
        "/shadow/runs/00000000-0000-0000-0000-000000000000/signals")
    assert r.status_code == 404


def test_shadow_router_has_no_write_endpoints():
    from app import shadow_routes
    for route in shadow_routes.router.routes:
        methods = set(route.methods or {})
        assert methods <= {"GET", "HEAD"}, (
            f"router shadow harus read-only, {route.path} punya {methods}")
