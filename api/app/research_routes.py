"""Endpoint riset Hermes (PRD v2.2 §12, t_f2v22a7).

Role 'research' (kredensial service Hermes) + 'admin'. Semua endpoint
write di sini HANYA menulis tabel riset (research_reports /
research_proposals / backtest_runs) — middleware default-deny di
app/main.py menolak role 'research' untuk endpoint lain.

Keputusan proposal (APPROVED/REJECTED) dan penandaan DEPLOYED adalah
owner-only: admin + CSRF + 2FA step-up + username == settings.owner_username
(pola selfimprove_routes). Proposal PROPOSED tidak punya jalur ke DEPLOYED
tanpa keputusan owner yang tercatat (kolom decided_by/decided_at).
"""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from . import db
from .auth import get_current_user, require_2fa, require_csrf
from .research import (
    ResearchToolError, UnknownToolError, allowlist_public, run_tool,
)

router = APIRouter(prefix="/research")


def require_research(user: dict = Depends(require_csrf)) -> dict:
    """Role riset: 'research' atau 'admin' (agent/user ditolak 403)."""
    if user.get("role") not in ("research", "admin"):
        raise HTTPException(403, "research role required")
    return user


async def _require_owner(user: dict) -> str:
    """Username pemanggil harus = settings.owner_username (default admin)."""
    settings = await db.get_settings()
    owner = str(settings.get("owner_username") or "admin").strip('"')
    if user.get("username") != owner:
        raise HTTPException(403, "hanya owner yang boleh memutuskan/deploy usulan riset")
    return user["username"]


@router.get("/tools")
async def list_tools(user: dict = Depends(get_current_user)):
    """Allowlist tool riset + skema input/output (transparansi PRD 12.4)."""
    if user.get("role") not in ("research", "admin"):
        raise HTTPException(403, "research role required")
    return {"tools": allowlist_public()}


@router.post("/tools/{name}")
async def call_tool(name: str, request: Request,
                    user: dict = Depends(require_research)):
    """Jalankan satu tool allowlist. Body = args JSON tool."""
    try:
        body = await request.json()
    except Exception:
        body = {}
    if not isinstance(body, dict):
        raise HTTPException(422, "body harus objek JSON args")
    try:
        result = await run_tool(name, body, actor=user["username"])
    except UnknownToolError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ResearchToolError as exc:
        raise HTTPException(422, str(exc)) from exc
    return result


@router.get("/reports")
async def list_reports(limit: int = 20, user: dict = Depends(get_current_user)):
    if user.get("role") not in ("research", "admin"):
        raise HTTPException(403, "research role required")
    limit = max(1, min(limit, 100))
    return await run_tool("list_reports", {"limit": limit}, actor=user["username"])


@router.get("/proposals")
async def list_proposals(limit: int = 20, user: dict = Depends(get_current_user)):
    if user.get("role") not in ("research", "admin"):
        raise HTTPException(403, "research role required")
    limit = max(1, min(limit, 100))
    return await run_tool("list_proposals", {"limit": limit}, actor=user["username"])


class DecisionBody(BaseModel):
    decision: str            # APPROVED | REJECTED
    rationale: str | None = Field(None, max_length=2000)


@router.post("/proposals/{proposal_id}/decision")
async def decide_proposal(proposal_id: int, body: DecisionBody,
                          user: dict = Depends(require_2fa)):
    """Keputusan owner atas usulan riset (admin+CSRF+2FA+owner_username)."""
    owner = await _require_owner(user)
    decision = body.decision.strip().upper()
    if decision not in ("APPROVED", "REJECTED"):
        raise HTTPException(422, "decision harus APPROVED | REJECTED")
    async with db.pool().connection() as conn:
        row = await conn.execute(
            "SELECT id, status FROM research_proposals WHERE id = %s",
            (proposal_id,))
        proposal = await row.fetchone()
        if proposal is None:
            raise HTTPException(404, "proposal tidak ditemukan")
        if proposal["status"] != "PROPOSED":
            raise HTTPException(
                422, f"proposal status {proposal['status']} sudah diputuskan")
        await conn.execute(
            """
            UPDATE research_proposals
            SET status = %s, decided_by = %s, decided_at = now(),
                decision_note = %s
            WHERE id = %s
            """,
            (decision, owner, body.rationale, proposal_id),
        )
        await conn.execute(
            """
            INSERT INTO audit_log (actor, actor_role, action, object, details)
            VALUES (%s, %s, 'RESEARCH_PROPOSAL_DECISION', %s, %s)
            """,
            (owner, user.get("role"), f"research_proposals/{proposal_id}",
             json.dumps({"decision": decision, "rationale": body.rationale})),
        )
    return {"ok": True, "proposal_id": proposal_id, "status": decision,
            "decided_by": owner}


class DeployedBody(BaseModel):
    strategy_version_id: int = Field(ge=1)
    note: str | None = Field(None, max_length=2000)


@router.post("/proposals/{proposal_id}/deployed")
async def mark_deployed(proposal_id: int, body: DeployedBody,
                        user: dict = Depends(require_2fa)):
    """Tandai proposal APPROVED sebagai DEPLOYED (owner-only, bookkeeping).

    Ini BUKAN mekanisme deploy: eksekusi perubahan tetap lewat release
    workflow versioning (activate owner+2FA) — PRD 12.2 langkah 11.
    Endpoint ini hanya mencatat bahwa proposal terkait versi yang
    sudah diaktifkan, sehingga status proposal tidak menggantung.
    """
    owner = await _require_owner(user)
    async with db.pool().connection() as conn:
        row = await conn.execute(
            "SELECT id, status FROM research_proposals WHERE id = %s",
            (proposal_id,))
        proposal = await row.fetchone()
        if proposal is None:
            raise HTTPException(404, "proposal tidak ditemukan")
        if proposal["status"] != "APPROVED":
            raise HTTPException(
                422, "hanya proposal APPROVED yang bisa ditandai DEPLOYED "
                     "(keputusan owner wajib lebih dulu)")
        ver = await conn.execute(
            "SELECT id FROM strategy_versions WHERE id = %s",
            (body.strategy_version_id,))
        if await ver.fetchone() is None:
            raise HTTPException(422, "strategy_version_id tidak ditemukan")
        await conn.execute(
            """
            UPDATE research_proposals
            SET status = 'DEPLOYED', strategy_version_id = %s,
                deployed_at = now(),
                decision_note = COALESCE(decision_note, '') || %s
            WHERE id = %s
            """,
            (body.strategy_version_id,
             f" | deployed: {body.note or ''}", proposal_id),
        )
        await conn.execute(
            """
            INSERT INTO audit_log (actor, actor_role, action, object, details)
            VALUES (%s, %s, 'RESEARCH_PROPOSAL_DEPLOYED', %s, %s)
            """,
            (owner, user.get("role"), f"research_proposals/{proposal_id}",
             json.dumps({"strategy_version_id": body.strategy_version_id})),
        )
    return {"ok": True, "proposal_id": proposal_id, "status": "DEPLOYED"}
