"""Endpoint config risk per-strategy (RISK-D, t_a172bb7b).

Alur (meniru pola approval yang sudah ada, PRD §18):
- Baca (panel Strategy Lab): sesi login apa pun; menampilkan nilai EFEKTIF
  per strategi + sumbernya (global / override / override_capped).
- Usul perubahan: admin + CSRF. Belum mengubah config aktif; hanya
  membuat request PROPOSED (satu per strategi, yang lama SUPERSEDED).
- Keputusan: owner (admin + CSRF + 2FA step-up + username ==
  settings.owner_username). APPROVED langsung menerapkan override;
  validasi ceiling global diulang saat apply (409 bila global mengetat).
- Tidak ada endpoint yang menulis override langsung (tanpa approval).

Semua perubahan tercatat: request row (siapa/kapan/alasan) + audit_log
(RISK_OVERRIDE_APPLIED / RISK_OVERRIDE_REJECTED, lengkap nilai lama/baru).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from . import db, risk_config
from .auth import get_current_user, require_admin, require_2fa
from .selfimprove_routes import _require_owner
from .strategies import REGISTRY

router = APIRouter(prefix="/risk/config")


class OverrideBody(BaseModel):
    # None = reset penuh ke global; key bernilai null = hapus key itu saja.
    overrides: dict | None = None
    note: str | None = None


class DecisionBody(BaseModel):
    decision: str  # APPROVED | REJECTED
    note: str | None = None


def _keys_meta() -> list[dict]:
    return [{"key": k, **risk_config.KEY_META[k]} for k in risk_config.KEY_ORDER]


def _payload(strategy_id: str, eff: dict, override: dict) -> dict:
    return {
        "strategy_id": strategy_id,
        "name": next((m.get("name") for m in REGISTRY
                      if m.get("id") == strategy_id), strategy_id),
        "symbols": eff["symbols"],
        "effective": eff["values"],
        "sources": eff["sources"],
        "capped": eff["capped"],
        "global": eff["global"],
        "override": override,
    }


@router.get("/strategies")
async def list_strategy_risk(user: dict = Depends(get_current_user)):
    """Config risk efektif semua strategi terdaftar + yang punya override."""
    async with db.pool().connection() as conn:
        settings = await db.get_settings()
        overrides = await risk_config.load_overrides(conn)
        ids = [m["id"] for m in REGISTRY]
        for sid in overrides:
            if sid not in ids:
                ids.append(sid)
        rows = [
            _payload(sid, risk_config.effective(
                sid, overrides.get(sid, {}), settings), overrides.get(sid, {}))
            for sid in ids
        ]
        pending = await risk_config.list_requests(conn, limit=50)
    return {
        "global": risk_config.global_config(settings),
        "keys": _keys_meta(),
        "strategies": rows,
        "pending": [r for r in pending if r["status"] == "PROPOSED"],
    }


@router.get("/strategies/{strategy_id}")
async def get_strategy_risk(strategy_id: str,
                            user: dict = Depends(get_current_user)):
    """Config risk efektif satu strategi + riwayat usulan (audit trail)."""
    sid = strategy_id.strip().lower()
    async with db.pool().connection() as conn:
        settings = await db.get_settings()
        override = await risk_config.override_for(conn, sid)
        eff = risk_config.effective(sid, override, settings)
        requests = await risk_config.list_requests(conn, sid, limit=10)
    payload = _payload(sid, eff, override)
    payload["requests"] = requests
    payload["pending"] = next(
        (r for r in requests if r["status"] == "PROPOSED"), None)
    return payload


@router.post("/strategies/{strategy_id}/propose", status_code=201)
async def propose_strategy_risk(strategy_id: str, body: OverrideBody,
                                user: dict = Depends(require_admin)):
    """Usulkan override risk per-strategy (menunggu keputusan owner).

    Usul = admin + CSRF (belum mengubah config aktif). Apply-nya butuh
    keputusan owner dengan 2FA step-up di endpoint decision.
    """
    sid = strategy_id.strip().lower()
    async with db.pool().connection() as conn:
        async with conn.transaction():
            try:
                request = await risk_config.propose(
                    conn, sid, body.overrides, user["username"], body.note)
            except risk_config.RiskOverrideInvalid as exc:
                raise HTTPException(status_code=422,
                                    detail={"errors": exc.errors})
    return {"request": request}


@router.get("/requests")
async def list_risk_requests(limit: int = 50,
                             user: dict = Depends(get_current_user)):
    async with db.pool().connection() as conn:
        return {"requests": await risk_config.list_requests(
            conn, limit=max(1, min(int(limit), 200)))}


@router.post("/requests/{request_id}/decision")
async def decide_risk_request(request_id: int, body: DecisionBody,
                              user: dict = Depends(require_2fa)):
    """Keputusan owner atas usulan override (APPROVED = langsung berlaku)."""
    reviewer = await _require_owner(user)
    async with db.pool().connection() as conn:
        async with conn.transaction():
            try:
                result = await risk_config.decide(
                    conn, request_id, body.decision, reviewer, body.note)
            except KeyError as exc:
                raise HTTPException(status_code=404, detail=str(exc))
            except risk_config.RiskOverrideInvalid as exc:
                # Global sudah mengetat sejak usulan dibuat: tolak apply,
                # owner harus mengusulkan nilai yang masih <= ceiling baru.
                raise HTTPException(status_code=409, detail={
                    "errors": exc.errors,
                    "hint": "ceiling global berubah; usulkan ulang nilai "
                            "yang <= batas global sekarang",
                })
            except ValueError as exc:
                raise HTTPException(status_code=409, detail=str(exc))
    return result
