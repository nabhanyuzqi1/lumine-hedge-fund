"""Read-only API hasil shadow strategy (PRD v2.2 §9, t_f2v22a4).

Shadow tidak pernah mengirim order; endpoint ini hanya MEMBACA
shadow_runs + shadow_signals untuk monitoring owner dan gerbang promosi
shadow->paper (§9.3). Tidak ada endpoint tulis di sini.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from .auth import get_current_user
from . import db

router = APIRouter(prefix="/shadow", tags=["shadow"])


@router.get("/runs")
async def list_shadow_runs(user: dict = Depends(get_current_user)):
    """Registry run shadow: versi/label, periode, status, metrik simulasi."""
    async with db.pool().connection() as conn:
        rows = await conn.execute(
            """
            SELECT run_id, strategy_id, strategy_version, label, symbol,
                   timeframe, period_start, period_end, config, cost_model,
                   metrics, signal_count, status, note, created_at, completed_at
            FROM shadow_runs ORDER BY created_at DESC LIMIT 100
            """)
        return {"runs": [dict(r) for r in await rows.fetchall()]}


@router.get("/runs/{run_id}/signals")
async def shadow_run_signals(run_id: str, limit: int = 100,
                             user: dict = Depends(get_current_user)):
    """Sinyal shadow satu run: harga referensi, spread, regime, alasan, sim fill."""
    limit = max(1, min(int(limit), 500))
    async with db.pool().connection() as conn:
        run = await conn.execute(
            "SELECT run_id, strategy_id, label, status FROM shadow_runs "
            "WHERE run_id = %s", (run_id,))
        if (await run.fetchone()) is None:
            raise HTTPException(404, "shadow run not found")
        rows = await conn.execute(
            """
            SELECT id, strategy_id, strategy_version, label, symbol, timeframe,
                   ts, ref_bid, ref_ask, spread, spread_median_15m,
                   regime_label, regime_confidence, side, volume, sl, tp,
                   reason, params_hash, code_commit, is_simulation, sim_status,
                   sim_fill_price, sim_cost_usd, sim_exit_price, sim_pnl_usd,
                   sim_exit_reason, sim_opened_at, sim_closed_at, detail,
                   created_at
            FROM shadow_signals WHERE run_id = %s
            ORDER BY ts DESC LIMIT %s
            """,
            (run_id, limit))
        return {"run_id": run_id, "is_simulation": True,
                "signals": [dict(r) for r in await rows.fetchall()]}
