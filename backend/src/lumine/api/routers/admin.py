# Copyright (c) 2026 Lumine. All rights reserved.
"""Admin endpoints for API key lifecycle and kill-switch control."""

from __future__ import annotations

import asyncio
import json
import secrets
import time
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status

from lumine.api.middleware.auth import AuthenticatedPrincipal, require_scope
from lumine.api.middleware.rate_limit import rate_limit_dependency
from lumine.api.schemas.api import (
    AdminKey,
    CreatedAdminKey,
    CreateKeyRequest,
    KillSwitchRequest,
    KillSwitchStatus,
    LLMUsageEntry,
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
            name = (c.name or "unknown").removeprefix("/")
            # B2: one-shot container (migrate) — bukan service runtime.
            # Exclude agar health count akurat (bukan "unhealthy" padahal
            # memang wajar sudah selesai & berhenti).
            if name == "backend-migrate-1":
                continue
            status_raw = c.status or "unknown"
            health = None
            if c.attrs.get("State", {}).get("Health", {}).get("Status"):
                health = c.attrs["State"]["Health"]["Status"]
            running = c.status == "running"
            name = (c.name or "unknown").removeprefix("/")
            # Image bisa None jika sudah dihapus (dangling) — handle gracefully.
            try:
                image = c.image.tags[0] if c.image and c.image.tags else None
            except Exception:
                image = None
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
    except Exception as exc:
        # Log exception untuk debug (jangan silent fail).
        import structlog
        log = structlog.get_logger()
        log.error("docker_list_containers_failed", exc_type=type(exc).__name__, exc_msg=str(exc)[:300])
        services = [ServiceStatus(name="unknown", status="unknown")]

    # B9: enabled_symbols dari Redis config (default ["XAUUSD"]).
    enabled_symbols = ["XAUUSD"]
    try:
        import json as _json

        r = await get_redis()
        raw = await r.hget(_SYSCONFIG_KEY, "enabled_symbols")
        if raw:
            parsed = _json.loads(raw)
            if isinstance(parsed, list) and parsed:
                enabled_symbols = [str(s).upper() for s in parsed]
    except Exception:
        pass  # Redis down → default XAUUSD

    return SystemInfo(
        services=services,
        llm_gateway_url=settings.llm_gateway_url,
        llm_gateway_configured=bool(settings.llm_gateway_api_key),
        demo_data=settings.demo_data,
        paper_trading=settings.paper_trading,
        environment=getattr(settings, "environment", "production"),
        version="1.0.0",
        enabled_symbols=enabled_symbols,
    )


# Runtime override store — env vars tidak bisa diubah in-process di prod,
# tapi kita simpan di Redis agar restart bisa memuat override.
_SYSCONFIG_KEY = "lumine:system_config"


@router.get("/llm-usage", response_model=list[LLMUsageEntry])
async def list_llm_usage(
    _principal: Annotated[AuthenticatedPrincipal, require_scope("admin")],
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[LLMUsageEntry]:
    """B10: recent LLM calls — untuk LLM routing diagram superadmin.

    Data real dari tabel llm_usage (append-only cost-accounting log).
    """
    from sqlalchemy import select

    from lumine.data.models import LLMUsage, ModelVersion
    from lumine.data.session import get_sessionmaker

    try:
        async with get_sessionmaker()() as session:
            rows = (
                await session.execute(
                    select(LLMUsage, ModelVersion.model_id)
                    .join(ModelVersion, LLMUsage.model_version_id == ModelVersion.id, isouter=True)
                    .order_by(LLMUsage.ts.desc())
                    .limit(limit)
                )
            ).all()
            return [
                LLMUsageEntry(
                    id=row.LLMUsage.id,
                    ts=row.LLMUsage.ts,
                    role=row.LLMUsage.role,
                    tier=row.LLMUsage.tier,
                    model=row.model_id,
                    tokens_in=row.LLMUsage.tokens_in,
                    tokens_out=row.LLMUsage.tokens_out,
                    cost_usd=row.LLMUsage.cost_usd,
                    fallback_hops=row.LLMUsage.fallback_hops,
                    degraded=row.LLMUsage.degraded,
                    lane=row.LLMUsage.lane,
                )
                for row in rows
            ]
    except Exception:
        return []


@router.get("/llm-models")
async def list_llm_models(
    _principal: Annotated[AuthenticatedPrincipal, require_scope("admin")],
    refresh: bool = Query(default=False),
) -> dict:
    """B10b: auto-discovery model 9router (18 Aug 2026).

    Fetch GET {llm_gateway_url}/v1/models → daftar model aktif → cache
    Redis `lumine:llm_routing:models`. UI superadmin pakai ini untuk
    dropdown default/fallback model. `?refresh=1` paksa fetch ulang.
    """
    from lumine.llm_gateway.routing_overlay import ROUTING_KEY

    r = await get_redis()
    cache_key = f"{ROUTING_KEY}:models"
    if not refresh:
        cached = await r.get(cache_key)
        if cached:
            import json as _json

            return _json.loads(cached.decode() if isinstance(cached, bytes) else cached)

    from lumine.shared.config import get_settings

    settings = get_settings()
    url = settings.llm_gateway_url.rstrip("/") + "/v1/models"
    key = settings.llm_gateway_api_key
    models: list[dict] = []
    error: str | None = None
    try:
        import urllib.request

        def _fetch() -> dict:
            req = urllib.request.Request(url, headers={"Authorization": f"Bearer {key}"})  # noqa: S310  # nosec B310 — url dari env LLM_GATEWAY_URL
            with urllib.request.urlopen(req, timeout=10) as resp:  # noqa: S310  # nosec B310 — url dari env LLM_GATEWAY_URL
                import json as _json

                return _json.loads(resp.read())

        import asyncio

        payload = await asyncio.to_thread(_fetch)
        for item in payload.get("data", []):
            mid = item.get("id", "")
            if mid:
                models.append(
                    {
                        "id": mid,
                        "owned_by": item.get("owned_by", ""),
                        "created": item.get("created"),
                    }
                )
    except Exception as exc:
        error = str(exc)[:200]

    payload = {"models": models, "fetched_at": time_now_iso(), "error": error}
    import json as _json

    await r.set(cache_key, _json.dumps(payload), ex=300)
    return payload


def time_now_iso() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).isoformat()


@router.put("/system-config", response_model=dict)
async def update_system_config(  # noqa: C901, PLR0912 — fixed field list, many branches
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
    if request.enabled_symbols is not None:
        # B9: enable/disable currency — simpan sebagai JSON di Redis.
        import json as _json

        updates["enabled_symbols"] = _json.dumps(
            [s.upper() for s in request.enabled_symbols]
        )

    if request.llm_auto_fallback is not None:
        import json as _json

        updates["llm_auto_fallback"] = "1" if request.llm_auto_fallback else "0"
        # Chain fallback model (ADR-0042): simpan list JSON.
        if request.llm_fallback_models is not None:
            updates["llm_fallback_models"] = _json.dumps(request.llm_fallback_models)
    elif request.llm_fallback_models is not None:
        import json as _json

        updates["llm_fallback_models"] = _json.dumps(request.llm_fallback_models)

    if request.paper_trading is not None:
        updates["paper_trading"] = "1" if request.paper_trading else "0"

    if updates:
        await r.hset(_SYSCONFIG_KEY, mapping=updates)

    # v4.11 (18 Aug 2026): REALTIME routing overlay — default/fallback model
    # langsung dipakai cycle berikutnya (tanpa restart api container).
    # Worker baca `lumine:llm_routing` tiap decision cycle.
    overlay_updates: dict[str, str] = {}
    if request.llm_default_model is not None:
        overlay_updates["default_model"] = request.llm_default_model
    if request.llm_fallback_models is not None:
        import json as _json

        overlay_updates["fallback_models"] = _json.dumps(request.llm_fallback_models)
    if request.llm_auto_fallback is not None:
        overlay_updates["auto_discovery"] = "1" if request.llm_auto_fallback else "0"
    if overlay_updates:
        from lumine.llm_gateway.routing_overlay import ROUTING_KEY

        await r.hset(ROUTING_KEY, mapping=overlay_updates)

    note = (
        "runtime config tersimpan; routing model realtime (tanpa restart), "
        "key/url masih butuh restart"
        if overlay_updates
        else "restart api container to apply all changes"
    )
    return {"updated": list(updates.keys()), "note": note}


@router.get("/ea-status")
async def get_ea_status(
    _principal: Annotated[AuthenticatedPrincipal, require_scope("admin")],
) -> dict:
    """EA status: version, seed phase, last tick, ticks sent — dari Redis mt5:status hash."""
    try:
        r = await get_redis()
        raw = await r.hgetall("mt5:status")
        # mt5:ticks queue length → proxy untuk "ticks pending"
        ticks_pending = await r.llen("mt5:ticks")
        # mt5:logs — recent EA log lines (LPUSH by EA, newest first)
        logs_raw = await r.lrange("mt5:logs", 0, 49)
        logs = [ln.decode() if isinstance(ln, bytes) else str(ln) for ln in logs_raw]
        status = {k.decode() if isinstance(k, bytes) else k: v.decode() if isinstance(v, bytes) else v
                  for k, v in raw.items()} if raw else {}
        return {
            "ea_version": status.get("ea_version", "unknown"),
            "ea_build": status.get("ea_build", "unknown"),
            "seed_phase": status.get("seed_phase", "unknown"),
            "seed_done": status.get("seed_done", "0"),
            "last_tick_ts": status.get("last_tick_ts"),
            "ticks_sent": status.get("ticks_sent", "0"),
            "ticks_pending": ticks_pending,
            "proxy_url": status.get("proxy_url", "unknown"),
            "symbol": status.get("symbol", "unknown"),
            "bid": status.get("bid"),
            "ask": status.get("ask"),
            "spread": status.get("spread"),
            "session_high": status.get("session_high"),
            "session_low": status.get("session_low"),
            "equity": status.get("equity"),
            "balance": status.get("balance"),
            "margin": status.get("margin"),
            "free_margin": status.get("free_margin"),
            "margin_level": status.get("margin_level"),
            "leverage": status.get("leverage"),
            "net_pnl": status.get("net_pnl"),
            # v4.11 (18 Aug 2026): connected = tick FRESH (<30s), bukan
            # sekadar hash ada — status Redis punya TTL 90s, EA bisa mati
            # tapi status masih tampil "Connected" hingga 90s.
            "connected": _ea_fresh(status),
            "logs": logs,
        }
    except Exception as exc:
        return {"connected": False, "error": str(exc), "logs": []}


def _ea_fresh(status: dict[str, str], max_age_s: float = 30.0) -> bool:
    """EA connected = last_tick_ts dalam max_age_s detik (atau status segar).

    Status Redis di-hset EA tiap InpStatusInterval (5s) tanpa TTL per
    field; hash bisa bertahan setelah EA mati. Gunakan last_tick_ts
    (epoch) sebagai sumber kebenaran freshness.
    """
    if not status:
        return False
    try:
        last = float(status.get("last_tick_ts", 0))
        if last > 0:
            import time as _time

            return (_time.time() - last) < max_age_s
    except (TypeError, ValueError):
        pass
    # Fallback: hash ada (EA baru start, tick pertama belum).
    return bool(status.get("ea_version"))


@router.post("/ea-command")
async def post_ea_command(
    body: dict,
    _principal: Annotated[AuthenticatedPrincipal, require_scope("admin")],
) -> dict:
    """Kirim command ke EA MT5 via Redis (SEED_NOW / RESEED / STATUS / PANEL_TOGGLE / PING).

    Body: {"action": "SEED_NOW"} — EA polling /commands tiap 1 detik, langsung eksekusi.
    """
    action = str(body.get("action", "")).upper().strip()
    allowed = {"SEED_NOW", "RESEED", "STATUS", "PANEL_TOGGLE", "PING"}
    if action not in allowed:
        return {"ok": False, "error": f"action harus salah satu dari: {sorted(allowed)}"}
    try:
        r = await get_redis()
        payload = {
            "id": f"web-{int(time.time())}",
            "command_id": f"web-{int(time.time())}",
            "action": action,
        }
        await r.rpush("mt5:commands", json.dumps(payload))
        return {"ok": True, "queued": payload}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
