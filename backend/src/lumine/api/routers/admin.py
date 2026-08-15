# Copyright (c) 2026 Lumine. All rights reserved.
"""Admin endpoints for API key lifecycle and kill-switch control."""

from __future__ import annotations

import asyncio
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
    ServiceStatus,
    SystemConfigUpdate,
    SystemInfo,
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
        tier=decoded.get("tier") if decoded.get("tier") in {"global", "book", "strategy"} else None,
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
            "tier": request.tier or "global",
            "updated_at": now.isoformat(),
            "updated_by": _principal.key_id,
        },
    )
    return KillSwitchStatus(
        armed=request.armed,
        reason=request.reason,
        tier=request.tier,
        updated_at=now,
    )


# ── Superadmin endpoints ───────────────────────────────────────────────────


@router.get("/system-info", response_model=SystemInfo)
async def get_system_info(
    settings: Annotated[Settings, Depends(get_settings)],
    _principal: Annotated[AuthenticatedPrincipal, require_scope("admin")],
) -> SystemInfo:
    """Snapshot status seluruh sistem — untuk superadmin control center.

    Baca status container via Docker API socket (docker CLI tidak ada di
    image; SDK `docker` baca /containers/json langsung). Fallback graceful
    ke [unknown] jika socket tidak di-mount (dev/local).
    """
    services: list[ServiceStatus] = []

    def _list_containers() -> list[ServiceStatus]:
        import docker

        client = docker.from_env()
        out: list[ServiceStatus] = []
        for c in client.containers.list(all=True):
            status_raw = c.status or "unknown"
            health = None
            if c.attrs.get("State", {}).get("Health", {}).get("Status"):
                health = c.attrs["State"]["Health"]["Status"]
            running = c.status == "running"
            name = (c.name or "unknown").removeprefix("/")
            image = (c.image.tags[0] if c.image and c.image.tags else None)
            out.append(
                ServiceStatus(
                    name=name,
                    status="running" if running else "stopped",
                    health=health,
                    image=image,
                    uptime=status_raw,
                )
            )
        return sorted(out, key=lambda s: s.name)

    try:
        services = await asyncio.to_thread(_list_containers)
    except Exception:
        services = [ServiceStatus(name="unknown", status="unknown")]

    return SystemInfo(
        services=services,
        llm_gateway_url=settings.llm_gateway_url,
        llm_gateway_configured=bool(settings.llm_gateway_api_key),
        demo_data=settings.demo_data,
        environment=getattr(settings, "environment", "production"),
        version="1.0.0",
    )


# Runtime override store — env vars tidak bisa diubah in-process di prod,
# tapi kita simpan di Redis agar restart bisa memuat override.
_SYSCONFIG_KEY = "lumine:system_config"


@router.put("/system-config", response_model=dict)
async def update_system_config(
    request: SystemConfigUpdate,
    _principal: Annotated[AuthenticatedPrincipal, require_scope("admin")],
) -> dict:
    """Update konfigurasi runtime (LLM key, trading params).

    Nilai disimpan ke Redis. Untuk apply penuh perlu restart container api.
    Field None = tidak diubah.
    """
    r = await get_redis()
    updates: dict[str, str] = {}
    if request.llm_gateway_api_key is not None:
        updates["llm_gateway_api_key"] = request.llm_gateway_api_key
    if request.llm_gateway_url is not None:
        updates["llm_gateway_url"] = request.llm_gateway_url
    if request.demo_data is not None:
        updates["demo_data"] = "1" if request.demo_data else "0"
    if request.llm_daily_budget_usd is not None:
        updates["llm_daily_budget_usd"] = str(request.llm_daily_budget_usd)
    if request.llm_default_model is not None:
        updates["llm_default_model"] = request.llm_default_model
    if request.max_exposure_per_trade is not None:
        updates["max_exposure_per_trade"] = str(request.max_exposure_per_trade)
    if request.risk_per_trade is not None:
        updates["risk_per_trade"] = str(request.risk_per_trade)
    if request.max_daily_loss_pct is not None:
        updates["max_daily_loss_pct"] = str(request.max_daily_loss_pct)

    if updates:
        await r.hset(_SYSCONFIG_KEY, mapping=updates)

    return {"updated": list(updates.keys()), "note": "restart api container to apply all changes"}
