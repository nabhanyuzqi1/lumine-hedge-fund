"""Endpoint versioning, approval & rollback strategi (PRD v2.2 §11, t_f2v22a6).

RBAC:
- register/attach/submit/review stage BACKTEST/SHADOW/PAPER: admin (CSRF).
- review stage OWNER_APPROVAL/LIVE_APPROVAL, activate, rollback: owner
  (admin + 2FA step-up + username == settings.owner_username), selaras
  gerbang approve self-improve.
Semua keputusan append-only di strategy_approvals; tidak ada endpoint
yang mengubah artifact versi final (PRD 11.1/11.4).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from . import db, versioning
from .auth import get_current_user, require_2fa
from .selfimprove_routes import _require_owner

router = APIRouter(prefix="/strategies")


class VersionBody(BaseModel):
    version: str
    params: dict = {}
    name: str | None = None
    code_commit_hash: str | None = None
    code_path: str | None = None
    data_version: str | None = None
    backtest_report: dict | None = None
    walkforward_report: dict | None = None
    shadow_report: dict | None = None
    paper_report: dict | None = None
    risk_profile: dict | None = None
    change_reason: str | None = None


class ArtifactBody(BaseModel):
    fields: dict = {}


class SubmitBody(BaseModel):
    evidence: dict | None = None


class ReviewBody(BaseModel):
    stage: str
    decision: str
    rationale: str | None = None
    evidence: dict | None = None


class ActivateBody(BaseModel):
    mode: str  # paper | live
    reason: str | None = None


class RollbackBody(BaseModel):
    to_version: str | None = None
    reason: str
    position_policy: str = "MANAGE_AS_IS"


def _http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, KeyError):
        return HTTPException(404, str(exc).strip("'"))
    if isinstance(exc, versioning.VersionFrozen):
        return HTTPException(409, str(exc))
    if isinstance(exc, versioning.VersioningError):
        return HTTPException(409, str(exc))
    return HTTPException(500, f"{type(exc).__name__}: {exc}")


@router.get("/{strategy_id}/versions")
async def list_versions(strategy_id: str,
                        user: dict = Depends(get_current_user)):
    async with db.pool().connection() as conn:
        try:
            return await versioning.list_versions(conn, strategy_id)
        except KeyError as exc:
            raise HTTPException(404, str(exc).strip("'"))


@router.post("/{strategy_id}/versions")
async def register_version(strategy_id: str, body: VersionBody,
                           user: dict = Depends(require_2fa)):
    try:
        return await versioning.register_version(
            strategy_id, version=body.version, params=body.params,
            name=body.name, code_commit_hash=body.code_commit_hash,
            code_path=body.code_path, data_version=body.data_version,
            backtest_report=body.backtest_report,
            walkforward_report=body.walkforward_report,
            shadow_report=body.shadow_report, paper_report=body.paper_report,
            risk_profile=body.risk_profile, change_reason=body.change_reason,
            created_by=user["username"])
    except Exception as exc:
        raise _http_error(exc)


@router.get("/{strategy_id}/versions/{version}")
async def version_detail(strategy_id: str, version: str,
                         user: dict = Depends(get_current_user)):
    async with db.pool().connection() as conn:
        try:
            row = await versioning.get_version(conn, strategy_id, version)
        except Exception as exc:
            raise _http_error(exc)
    if row is None:
        raise HTTPException(404, f"versi {strategy_id}/{version} tidak terdaftar")
    return row


@router.post("/{strategy_id}/versions/{version}/artifacts")
async def attach_artifacts(strategy_id: str, version: str, body: ArtifactBody,
                           user: dict = Depends(require_2fa)):
    try:
        return await versioning.attach_artifacts(
            strategy_id, version, actor=user["username"], **body.fields)
    except Exception as exc:
        raise _http_error(exc)


@router.post("/{strategy_id}/versions/{version}/submit")
async def submit_review(strategy_id: str, version: str, body: SubmitBody,
                        user: dict = Depends(require_2fa)):
    try:
        return await versioning.submit_review(
            strategy_id, version, actor=user["username"],
            evidence=body.evidence)
    except Exception as exc:
        raise _http_error(exc)


@router.post("/{strategy_id}/versions/{version}/review")
async def review_version(strategy_id: str, version: str, body: ReviewBody,
                         user: dict = Depends(require_2fa)):
    """Keputusan stage (PRD 11.2). Stage owner wajib username owner."""
    stage = (body.stage or "").strip().upper()
    if stage in versioning.OWNER_STAGES:
        reviewer = await _require_owner(user)
    else:
        reviewer = user["username"]
    try:
        return await versioning.decide_stage(
            strategy_id, version, stage, body.decision, reviewer=reviewer,
            rationale=body.rationale, evidence=body.evidence)
    except Exception as exc:
        raise _http_error(exc)


@router.post("/{strategy_id}/versions/{version}/activate")
async def activate_version(strategy_id: str, version: str, body: ActivateBody,
                           user: dict = Depends(require_2fa)):
    actor = await _require_owner(user)
    try:
        return await versioning.activate_version(
            strategy_id, version, mode=body.mode, actor=actor,
            reason=body.reason)
    except Exception as exc:
        raise _http_error(exc)


@router.post("/{strategy_id}/rollback")
async def rollback_strategy(strategy_id: str, body: RollbackBody,
                            user: dict = Depends(require_2fa)):
    actor = await _require_owner(user)
    try:
        return await versioning.rollback_strategy(
            strategy_id, to_version=body.to_version, actor=actor,
            reason=body.reason, position_policy=body.position_policy)
    except Exception as exc:
        raise _http_error(exc)


# ── Read summary untuk Strategy Lab (PRD v2.2 §21.4, t_b61b39d0) ────────────
# Kedua endpoint read-only (get_current_user, tanpa 2FA) dan tidak mengubah
# perilaku endpoint versioning di atasnya maupun tabel immutable (PRD 11.4).
@router.get("/lifecycle-summary")
async def lifecycle_summary(user: dict = Depends(get_current_user)):
    """Ringkasan lifecycle semua strategi dalam satu panggilan (anti N+1).

    Per strategi: versi aktif, jumlah versi, approval terakhir, flag
    walk-forward/shadow, status degradasi (absen = NORMAL), dan status
    lifecycle supervisor (PRD 5.3).
    """
    async with db.pool().connection() as conn:
        strategies = await versioning.lifecycle_summary(conn)
    return {"strategies": strategies}


@router.get("/{strategy_id}/approvals")
async def list_approvals(strategy_id: str, limit: int = 50,
                         user: dict = Depends(get_current_user)):
    """Riwayat approval strategi (append-only, PRD 11), urut desc, limit 50.

    Return 404 bila strategy_id tidak dikenal; daftar kosong bila strategi
    dikenal tetapi belum punya keputusan approval.
    """
    async with db.pool().connection() as conn:
        if await versioning.get_strategy(conn, strategy_id) is None:
            raise HTTPException(404, f"strategi {strategy_id} tidak terdaftar")
        approvals = await versioning.list_approvals(conn, strategy_id,
                                                    limit=limit)
    return {"approvals": approvals}
