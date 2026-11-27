"""API degradation detection (PRD v2.2 §10, t_f2v22a5).

Read: status + indikator + event (semua user ter-autentikasi).
Tulis: HANYA re-enable owner (PRD §10.3 "Re-enable memerlukan review dan
approval owner") — admin + step-up 2FA, dengan review_note wajib sebagai
bukti review; setiap panggilan tercatat append-only di degradation_events.
Tidak ada endpoint yang menaikkan status secara manual: eskalasi hanya dari
evaluator (data-driven), bukan input manual.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from . import db, degradation, degradation_store
from .auth import get_current_user, require_2fa

router = APIRouter(prefix="/strategies", tags=["degradation"])


class ReEnableBody(BaseModel):
    review_note: str = Field(min_length=10, max_length=500)


@router.get("/degradation")
async def degradation_states(user: dict = Depends(get_current_user)):
    """Semua status degradation + snapshot indikator (monitoring)."""
    async with db.pool().connection() as conn:
        rows = await degradation_store.state_rows(conn)
    return {"states": rows}


@router.get("/{strategy_id}/degradation")
async def degradation_detail(strategy_id: str,
                             user: dict = Depends(get_current_user)):
    """Detail satu strategi: state, indikator, event terakhir."""
    async with db.pool().connection() as conn:
        state = await degradation_store.load_state(conn, strategy_id)
        events = await degradation_store.recent_events(conn, strategy_id,
                                                       limit=30)
    return {"strategy_id": strategy_id, "state": state, "events": events}


@router.post("/{strategy_id}/degradation/re-enable")
async def re_enable(strategy_id: str, body: ReEnableBody,
                    user: dict = Depends(require_2fa)):
    """Re-enable owner (PRD §10.3): WATCH/DEGRADED/HALTED -> NORMAL.

    require_2fa = admin + TOTP step-up (approval owner). review_note wajib
    (>= 10 char) sebagai bukti review; tersimpan di event append-only.
    """
    async with db.pool().connection() as conn:
        state = await degradation_store.load_state(conn, strategy_id)
        if state.get("status") == "NORMAL":
            raise HTTPException(400, "strategi sudah NORMAL; "
                                     "re-enable tidak diperlukan")
        new_state = await degradation_store.re_enable(
            conn, strategy_id=strategy_id,
            actor=str(user.get("username") or "owner"),
            note=body.review_note)
    return {"strategy_id": strategy_id,
            "from_status": state.get("status"),
            "status": new_state.get("status"),
            "reenable_history": new_state.get("reenable_history")}
