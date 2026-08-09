# Copyright (c) 2026 Lumine. All rights reserved.
"""Admin endpoints for API key lifecycle and kill-switch control."""

from __future__ import annotations

import secrets
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, status

from lumine.api.middleware.auth import AuthenticatedPrincipal, require_scope
from lumine.api.middleware.rate_limit import rate_limit_dependency
from lumine.api.schemas.api import (
    AdminKey,
    CreatedAdminKey,
    CreateKeyRequest,
    KillSwitchRequest,
    KillSwitchStatus,
)
from lumine.data.redis_client import get_redis
from lumine.shared.config import Settings, get_settings
from lumine.shared.errors import DuplicateRecordError

router = APIRouter(prefix="/admin", tags=["admin"])


def _decode_hash(raw: dict[bytes | str, bytes | str]) -> dict[str, str]:
    """Normalize Redis hash fields to strings."""
    return {
        (k.decode() if isinstance(k, bytes) else k): (v.decode() if isinstance(v, bytes) else v)
        for k, v in raw.items()
    }


def _key_redis_key(key_id: str) -> str:
    return f"lumine:api_key:{key_id}"


@router.get("/keys", response_model=list[AdminKey])
async def list_api_keys(
    _principal: Annotated[AuthenticatedPrincipal, require_scope("admin")],
) -> list[AdminKey]:
    """List all dynamic API keys (excluding the bootstrap key)."""
    r = await get_redis()
    keys: list[AdminKey] = []
    async for key in r.scan_iter(match="lumine:api_key:*"):
        key_id = key.decode().split(":")[-1] if isinstance(key, bytes) else key.split(":")[-1]
        raw = await r.hgetall(_key_redis_key(key_id))
        if not raw:
            continue
        decoded = _decode_hash(raw)
        keys.append(
            AdminKey(
                key_id=key_id,
                name=decoded.get("name", ""),
                scopes=decoded.get("scopes", "").split(",") if decoded.get("scopes") else [],
                revoked=decoded.get("revoked") == "1",
                created_at=datetime.fromisoformat(
                    decoded.get("created_at", datetime.now(UTC).isoformat())
                ),
            )
        )
    return keys


@router.post(
    "/keys",
    response_model=CreatedAdminKey,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(rate_limit_dependency)],
)
async def create_api_key(
    request: CreateKeyRequest,
    _principal: Annotated[AuthenticatedPrincipal, require_scope("admin")],
) -> CreatedAdminKey:
    """Create a new dynamic API key and return the secret exactly once."""
    r = await get_redis()
    redis_key = _key_redis_key(request.key_id)

    exists = await r.exists(redis_key)
    if exists:
        msg = f"API key {request.key_id} already exists"
        raise DuplicateRecordError(msg)

    secret = secrets.token_urlsafe(32)
    now = datetime.now(UTC)
    await r.hset(
        redis_key,
        mapping={
            "secret": secret,
            "name": request.name,
            "scopes": ",".join(request.scopes),
            "revoked": "0",
            "created_at": now.isoformat(),
        },
    )
    return CreatedAdminKey(
        key_id=request.key_id,
        secret=secret,
        scopes=request.scopes,
        created_at=now,
    )


@router.delete(
    "/keys/{key_id}",
    response_model=AdminKey,
    dependencies=[Depends(rate_limit_dependency)],
)
async def revoke_api_key(
    key_id: Annotated[str, Path(...)],
    _principal: Annotated[AuthenticatedPrincipal, require_scope("admin")],
) -> AdminKey:
    """Revoke a dynamic API key. The bootstrap key cannot be revoked here."""
    if key_id == "bootstrap":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="bootstrap key cannot be revoked via API",
        )

    r = await get_redis()
    redis_key = _key_redis_key(key_id)
    raw = await r.hgetall(redis_key)
    if not raw:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API key not found")

    decoded = _decode_hash(raw)
    await r.hset(redis_key, "revoked", "1")
    return AdminKey(
        key_id=key_id,
        name=decoded.get("name", ""),
        scopes=decoded.get("scopes", "").split(",") if decoded.get("scopes") else [],
        revoked=True,
        created_at=datetime.fromisoformat(decoded.get("created_at", datetime.now(UTC).isoformat())),
    )


@router.get("/kill-switch", response_model=KillSwitchStatus)
async def get_kill_switch(
    settings: Annotated[Settings, Depends(get_settings)],
    _principal: Annotated[AuthenticatedPrincipal, require_scope("admin")],
) -> KillSwitchStatus:
    """Return the current kill-switch state."""
    r = await get_redis()
    raw = await r.hgetall(settings.kill_switch_key)
    if not raw:
        return KillSwitchStatus(armed=False, reason=None, updated_at=None)

    decoded = _decode_hash(raw)
    return KillSwitchStatus(
        armed=decoded.get("armed") == "1",
        reason=decoded.get("reason") or None,
        updated_at=datetime.fromisoformat(decoded["updated_at"])
        if "updated_at" in decoded
        else None,
    )


@router.post(
    "/kill-switch",
    response_model=KillSwitchStatus,
    dependencies=[Depends(rate_limit_dependency)],
)
async def set_kill_switch(
    request: KillSwitchRequest,
    settings: Annotated[Settings, Depends(get_settings)],
    _principal: Annotated[AuthenticatedPrincipal, require_scope("admin")],
) -> KillSwitchStatus:
    """Arm or disarm the kill switch."""
    r = await get_redis()
    now = datetime.now(UTC)
    await r.hset(
        settings.kill_switch_key,
        mapping={
            "armed": "1" if request.armed else "0",
            "reason": request.reason,
            "updated_at": now.isoformat(),
            "updated_by": _principal.key_id,
        },
    )
    return KillSwitchStatus(
        armed=request.armed,
        reason=request.reason,
        updated_at=now,
    )
