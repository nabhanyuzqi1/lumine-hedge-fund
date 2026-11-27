"""Endpoint approve/deploy usulan self-improve (PRD v2.1 P4, garis merah §5.9).

Owner-only: admin + CSRF + 2FA step-up + username == settings.owner_username.
Keputusan dicatat append-only (strategy_approvals); perubahan settings ter-audit
otomatis via trigger settings_audit (b002). Role 'agent' dan 'user' ditolak.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from . import db, self_improve
from .auth import get_current_user, require_2fa

router = APIRouter(prefix="/improve")


class DecisionBody(BaseModel):
    decision: str  # APPROVED | REJECTED
    rationale: str | None = None


async def _require_owner(user: dict) -> str:
    """Username pemanggil harus = settings.owner_username (default 'admin')."""
    await self_improve._ensure_pool()
    settings = await db.get_settings()
    owner = str(settings.get("owner_username") or "admin").strip('"')
    if user.get("username") != owner:
        raise HTTPException(
            status_code=403, detail="hanya owner yang boleh memutuskan/deploy usulan")
    return user["username"]


@router.get("/proposals")
async def list_proposals(user: dict = Depends(get_current_user)):
    await self_improve._ensure_pool()
    return await self_improve.status()


@router.post("/proposals/{proposal_id}/decision")
async def decide_proposal(proposal_id: str, body: DecisionBody,
                          user: dict = Depends(require_2fa)):
    reviewer = await _require_owner(user)
    try:
        result = await self_improve.decide(
            proposal_id, body.decision, reviewer, body.rationale)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return result
