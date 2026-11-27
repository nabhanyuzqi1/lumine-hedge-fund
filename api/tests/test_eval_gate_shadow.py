"""Tests gerbang promosi shadow -> paper (PRD 9.3, scripts/eval_gate_shadow.py).

Data sintetis di test DB: PASS / FAIL(leakage) / INSUFFICIENT / PENDING.
"""
from __future__ import annotations

import importlib.util
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest

from app import db

UTC = timezone.utc
BASE = datetime(2026, 11, 23, 8, 0, 0, tzinfo=UTC)  # masa lalu (out-of-sample)

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "eval_gate_shadow.py"


@pytest.fixture
def gate():
    spec = importlib.util.spec_from_file_location("eval_gate_shadow", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["eval_gate_shadow"] = mod
    spec.loader.exec_module(mod)
    return mod


async def _seed(conn, *, label, n=12, pnl=(15.0, -5.0), leak=False,
                critical=False, approved=False):
    from app import db
    await db.set_setting("kill_switch", False)
    # strategi + versi registry utk approval
    await conn.execute(
        "INSERT INTO strategies (strategy_id, name, status, environment, "
        "current_version, enabled) VALUES ('london_breakout', 'LB', 'SHADOW', "
        "'dev', '1.0.0', TRUE) ON CONFLICT (strategy_id) DO NOTHING")
    await conn.execute(
        "INSERT INTO strategy_versions (strategy_id, version, code_commit_hash) "
        "VALUES ('london_breakout', '1.0.0', 'test123') "
        "ON CONFLICT (strategy_id, version) DO NOTHING")
    if approved:
        await conn.execute(
            "INSERT INTO strategy_approvals (strategy_version_id, stage, "
            "decision, reviewer, rationale) SELECT id, 'SHADOW_REVIEW', "
            "'APPROVED', 'owner', 'test' FROM strategy_versions "
            "WHERE strategy_id='london_breakout' AND version='1.0.0'")
    if critical:
        await conn.execute(
            "INSERT INTO system_events (event_type, severity, source, actor, "
            "message) VALUES ('STRATEGY_FAULT', 'CRITICAL', 'supervisor', "
            "'london_breakout', 'test fault')")
    run_id = uuid4().hex
    # tutup run RUNNING sebelumnya untuk label yang sama (unique partial index)
    await conn.execute(
        "UPDATE shadow_runs SET status='COMPLETED', completed_at=now() "
        "WHERE strategy_id='london_breakout' AND label=%s AND status='RUNNING'",
        (label,))
    await conn.execute(
        "INSERT INTO shadow_runs (run_id, strategy_id, strategy_version, label, "
        "symbol, timeframe, period_start, period_end, status, config) "
        "VALUES (%s, 'london_breakout', '1.0.0', %s, 'XAUUSD', '5m', %s, "
        "NULL, 'RUNNING', '{}'::jsonb)",
        (run_id, label, BASE))  # period_end NULL = run masih RUNNING
    for i in range(n):
        ts = BASE + timedelta(minutes=30 * i)
        created = ts + (timedelta(minutes=-10) if leak else timedelta(seconds=2))
        p = pnl[i % len(pnl)]
        await conn.execute(
            "INSERT INTO shadow_signals (run_id, strategy_id, strategy_version, "
            "label, symbol, timeframe, ts, ref_bid, ref_ask, spread, side, "
            "volume, sl, tp, reason, params_hash, is_simulation, sim_status, "
            "sim_fill_price, sim_cost_usd, sim_pnl_usd, sim_exit_reason, "
            "sim_opened_at, sim_closed_at, created_at) "
            "VALUES (%s,'london_breakout','1.0.0',%s,'XAUUSD','5m',%s,1999.85,"
            "2000.15,0.30,'BUY',0.04,1990,2015,'test',%s,TRUE,'FILLED',2000.25,"
            "1.28,%s,'TP',%s,%s,%s)",
            (run_id, label, ts, "h" * 16, p, ts + timedelta(minutes=5),
             ts + timedelta(minutes=5), created))
    return run_id


async def test_gate_pending_then_pass(gate, _clean_db):
    async with db.pool().connection() as conn:
        await _seed(conn, label="g-pending", approved=False)
    report, verdict = gate.evaluate(label="g-pending", min_signals=10,
                                    max_per_day=200, min_profit_factor=0.5)
    assert verdict == "PENDING"  # cek otomatis lulus, owner belum approve
    assert all(report["checks"].values())
    async with db.pool().connection() as conn:
        await _seed(conn, label="g-pending", approved=True)
    report, verdict = gate.evaluate(label="g-pending", min_signals=10,
                                    max_per_day=200, min_profit_factor=0.5)
    assert verdict == "PASS"
    assert report["owner_approval"]["approved"] is True


async def test_gate_fail_on_leakage(gate, _clean_db):
    async with db.pool().connection() as conn:
        await _seed(conn, label="g-leak", leak=True, approved=True)
    report, verdict = gate.evaluate(label="g-leak", min_signals=10,
                                    max_per_day=50, min_profit_factor=0.5)
    assert verdict == "FAIL"
    assert report["checks"]["no_data_leakage"] is False
    assert report["metrics"]["leakage_signals"] >= 1


async def test_gate_fail_on_critical(gate, _clean_db):
    async with db.pool().connection() as conn:
        await _seed(conn, label="g-crit", critical=True, approved=True)
    report, verdict = gate.evaluate(label="g-crit", min_signals=10,
                                    max_per_day=50, min_profit_factor=0.5)
    assert verdict == "FAIL"
    assert report["checks"]["no_critical_errors"] is False


async def test_gate_insufficient(gate, _clean_db):
    async with db.pool().connection() as conn:
        await _seed(conn, label="g-thin", n=3, approved=True)
    report, verdict = gate.evaluate(label="g-thin", min_signals=10,
                                    max_per_day=50, min_profit_factor=0.5)
    assert verdict == "INSUFFICIENT"


async def test_gate_missing_label_insufficient(gate, _clean_db):
    report, verdict = gate.evaluate(label="no-such-label", min_signals=10,
                                    max_per_day=50, min_profit_factor=0.5)
    assert verdict == "INSUFFICIENT"
    assert report == {}
