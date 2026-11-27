"""Test self-improvement loop mingguan (PRD v2.1 §5.9, P4; kartu t_f2p4a1).

Kriteria verdict DIDEKLARASIKNAN sebelum run; deploy hanya lewat keputusan
owner; non-owner ditolak (garis merah PRD §5.9).
"""
from __future__ import annotations

import json

import pytest
from fastapi import HTTPException

from app import db, self_improve
from app.selfimprove_analysis import (
    evaluate_criteria,
    render_report,
    split_telegram,
    _stitched_from_windows,
)


def _report(net=20.0, pf=1.167, dd=0.05, win_profit=70.0):
    """Report walk-forward sintetis dengan trades_detail per window.

    2 window x 5 trade: profit [win,-30,-5,-10,-15] -> net 20 (win=70),
    gross win 2x win, gross loss 120 (PF 1.167), expectancy 2.0.
    """
    windows = []
    for i in range(2):
        windows.append({"test_metrics": {
            "trades": 5, "profit_factor": pf,
            "trades_detail": [
                {"profit": win_profit, "r_multiple": 1.0},
                {"profit": -30.0, "r_multiple": -1.0},
                {"profit": -5.0, "r_multiple": -0.2},
                {"profit": -10.0, "r_multiple": -0.5},
                {"profit": -15.0, "r_multiple": -0.7},
            ]}})
    return {"aggregate": {
        "n_windows": 2, "stitched_net_profit_usd": net,
        "stitched_max_drawdown_pct": dd,
    }, "windows": windows}


def test_criteria_lulus():
    info = evaluate_criteria(_report(), {"min_trades": 10})
    assert info["verdict"] == "LULUS"
    assert all(info["checks"].values())


def test_criteria_gagal_pf_dan_dd():
    # trade-level juga rugi (gross win 0) -> PF 0 -> GAGAL
    info = evaluate_criteria(_report(net=-100.0, pf=0.8, dd=0.15, win_profit=-10.0),
                             {"min_trades": 10})
    assert info["verdict"] == "GAGAL"
    assert not info["checks"]["profit_factor_gt"]
    assert not info["checks"]["net_profit_usd_gt"]
    assert not info["checks"]["max_drawdown_pct_lte"]


def test_criteria_min_trades_kustom():
    # trades hasil stitching dari trades_detail: 2 window x 5 = 10
    info = evaluate_criteria(_report(), {"min_trades": 15})
    assert info["verdict"] == "GAGAL"
    assert not info["checks"]["min_trades"]
    info2 = evaluate_criteria(_report(), {"min_trades": 10})
    assert info2["verdict"] == "LULUS"


def test_stitched_from_windows():
    agg = _stitched_from_windows(_report()["windows"])
    assert agg["stitched_trades"] == 10
    assert agg["stitched_expectancy_usd"] == 2.0
    assert agg["stitched_profit_factor"] == 1.167


def test_split_telegram():
    text = "\n".join(f"baris {i} " + "x" * 80 for i in range(200))
    chunks = split_telegram(text)
    assert len(chunks) > 1
    assert all(len(c) <= 3900 for c in chunks)
    assert "\n".join(chunks) == text


def test_split_telegram_tunggal():
    assert split_telegram("pendek") == ["pendek"]


def test_render_report_menyertakan_bagian_kunci():
    analysis = {"kill_switch": {"mode": None}, "orders_by_status": {"FILLED": 3},
                "order_events_7d": 12, "anomalies_7d": [],
                "paper_state": {"runner": {"balance": 10000.0, "position": None}},
                "walkforward_summary": []}
    entries = [{"id": "w47-p1", "title": "uji SL 5.0", "verdict": "GAGAL",
                "status": "PROPOSED", "criteria_result": {
                    "aggregate": {"net_profit_usd": -587.6, "profit_factor": 0.7,
                                  "trades": 134, "max_drawdown_pct": 0.06},
                    "checks": {"profit_factor_gt": False},
                    }}]
    text = render_report("2026-W47", analysis, entries)
    assert "2026-W47" in text
    assert "w47-p1" in text and "GAGAL" in text
    assert "approve owner" in text
    assert "-587.60" in text


def test_render_report_markdown_aman_telegram():
    """Nilai dinamis ber-karakter Markdown Telegram harus di-escape.

    Temuan gerbang P4 (t_f2co_p4): laporan W48 memuat literal t_f2p4a1 dan
    nama kriteria berunderscore sehingga Telegram menolak pesan (can't
    parse entities) sementara pemanggil melaporkan sukses.
    """
    analysis = {"kill_switch": {"mode": "STOP_NEW_ORDERS"},
                "orders_by_status": {"PARTIALLY_FILLED": 2},
                "order_events_7d": 3, "anomalies_7d": [],
                "paper_state": {"runner_x": {"balance": 1.0, "position": None}},
                "walkforward_summary": [
                    {"strategy_id": "mean_reversion", "symbol": "XAUUSD",
                     "timeframe": "M5", "net_usd": -1.0, "windows": 1,
                     "trades": 1, "avg_pf": 0.5}]}
    entries = [{"id": "w47-x", "title": "petik * hasil _ bagus",
                "verdict": "GAGAL", "status": "PROPOSED",
                "criteria_result": {
                    "aggregate": {"net_profit_usd": -1.0, "profit_factor": 0.5,
                                  "trades": 1, "max_drawdown_pct": 0.01},
                    "checks": {"net_profit_usd_gt": False}}}]
    text = render_report("2026-W48", analysis, entries)
    # semua underscore dinamis ter-escape; penanda bold sengaja tetap ada
    stripped = text.replace("\\_", "").replace("\\*", "").replace("\\`", "")
    assert "_" not in stripped
    assert stripped.count("*") % 2 == 0
    # tidak ada referensi kartu memtak tertanam di template
    assert "t_f2p4a1" not in text


def test_load_proposals_repo():
    proposals = self_improve.load_proposals()
    assert len(proposals) >= 1
    ids = [p["id"] for p in proposals]
    assert len(ids) == len(set(ids))


def test_decide_decision_invalid():
    import asyncio
    with pytest.raises(ValueError):
        asyncio.run(self_improve.decide("x", "MAYBE", "admin"))


async def test_decide_unknown_proposal():
    with pytest.raises(KeyError):
        await self_improve.decide("tidak-ada", "APPROVED", "admin")


async def test_deploy_butuh_approved():
    async with db.pool().connection() as conn:
        await conn.execute(
            """INSERT INTO improvement_proposals
               (id, week, title, hypothesis, change)
               VALUES ('t-deploy-1', '2026-W47', 'u', 'h', %s)""",
            (json.dumps({"strategy_id": "mean_reversion", "version": "1.1.0",
                         "symbol": "XAUUSD", "tf": "M5", "params": {},
                         "mode": "paper"}),))
    with pytest.raises(ValueError):
        await self_improve.deploy("t-deploy-1", "admin")


async def test_flow_approve_lalu_deploy():
    async with db.pool().connection() as conn:
        await conn.execute(
            """INSERT INTO improvement_proposals
               (id, week, title, hypothesis, change, verdict, evidence)
               VALUES ('t-flow-1', '2026-W47', 'MR num_std 3.0', 'h', %s,
                       'GAGAL', '{}')""",
            (json.dumps({"strategy_id": "mean_reversion", "version": "1.1.0",
                         "symbol": "XAUUSD", "tf": "M5",
                         "params": {"num_std": 3.0, "min_rr": 1.0},
                         "mode": "paper"}),))
    result = await self_improve.decide("t-flow-1", "APPROVED", "admin",
                                       "setuju uji paper")
    assert result["status"] == "DEPLOYED"
    async with db.pool().connection() as conn:
        strat = await (await conn.execute(
            "SELECT enabled, status, current_version FROM strategies "
            "WHERE strategy_id = 'mean_reversion'")).fetchone()
        assert strat["enabled"] is True and strat["status"] == "PAPER"
        assert strat["current_version"] == "1.1.0"
        version = await (await conn.execute(
            "SELECT id, status FROM strategy_versions "
            "WHERE strategy_id = 'mean_reversion' AND version = '1.1.0'")).fetchone()
        assert version["status"] == "APPROVED"
        approvals = await (await conn.execute(
            "SELECT stage, decision FROM strategy_approvals "
            "WHERE strategy_version_id = %s ORDER BY id",
            (version["id"],))).fetchall()
        assert [a["stage"] for a in approvals] == ["OWNER_APPROVE", "DEPLOY"]
        dep = await (await conn.execute(
            "SELECT service, environment, deployed_by FROM deployment_records "
            "WHERE service = 'fund2-strategy-mean_reversion'")).fetchone()
        assert dep["deployed_by"] == "admin"
        params = await (await conn.execute(
            "SELECT value FROM settings WHERE key = 'strategy_params_mean_reversion'"
        )).fetchone()
        val = params["value"]
        val = val if isinstance(val, dict) else json.loads(val)
        assert val["num_std"] == 3.0
        prop = await (await conn.execute(
            "SELECT status, reviewer FROM improvement_proposals WHERE id = 't-flow-1'"
        )).fetchone()
        assert prop["status"] == "DEPLOYED" and prop["reviewer"] == "admin"


async def test_non_owner_ditolak():
    from app.selfimprove_routes import _require_owner
    with pytest.raises(HTTPException) as exc:
        await _require_owner({"username": "qac"})
    assert exc.value.status_code == 403
    user = await _require_owner({"username": "admin"})
    assert user == "admin"
