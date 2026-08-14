# Copyright (c) 2026 Lumine. All rights reserved.
"""Command RPC endpoints for operational control (B-04: real dispatch).

Every command is enqueued to the Redis Streams ``rpc:commands`` and
processed by ``lumine.rpc.worker`` (started in the app lifespan). The
receipt carries a real ``command_id``; status can be polled via
``GET /rpc/commands/{command_id}``.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException

from lumine.api.middleware.auth import AuthenticatedPrincipal, require_scope
from lumine.api.middleware.rate_limit import rate_limit_dependency
from lumine.api.schemas.api import RpcCommandRequest, RpcCommandResponse, RpcCommandResult
from lumine.rpc.queue import enqueue_command, get_result
from lumine.shared.config import Settings, get_settings
from lumine.shared.errors import KillSwitchError

router = APIRouter(prefix="/rpc", tags=["rpc"])


async def _kill_switch_armed(settings: Settings) -> bool:
    """Check whether the kill switch is currently armed."""
    from lumine.data.redis_client import get_redis

    r = await get_redis()
    raw = await r.hget(settings.kill_switch_key, "armed")
    if raw is None:
        return False
    value = raw.decode() if isinstance(raw, bytes) else raw
    return value == "1"


async def _accept(command: str, payload: dict | None = None) -> RpcCommandResponse:
    """Enqueue a command and return its acceptance receipt."""
    command_id = await enqueue_command(command, payload)
    return RpcCommandResponse(
        command_id=UUID(command_id),
        command=command,
        status="accepted",
        reason=None,
        enqueued_at=datetime.now(UTC),
    )


@router.post(
    "/run-decision-cycle",
    response_model=RpcCommandResponse,
    dependencies=[Depends(rate_limit_dependency)],
)
async def run_decision_cycle(
    settings: Annotated[Settings, Depends(get_settings)],
    _principal: Annotated[AuthenticatedPrincipal, require_scope("write:workflows")],
    request: RpcCommandRequest | None = Body(None),
) -> RpcCommandResponse:
    """Enqueue a full decision-cycle workflow run."""
    if await _kill_switch_armed(settings):
        msg = "decision cycle blocked by kill switch"
        raise KillSwitchError(msg)
    params = (request.parameters if request else {}) or {}
    return await _accept("run_decision_cycle", params)


@router.post(
    "/halt-trading",
    response_model=RpcCommandResponse,
    dependencies=[Depends(rate_limit_dependency)],
)
async def halt_trading(
    _principal: Annotated[AuthenticatedPrincipal, require_scope("admin")],
) -> RpcCommandResponse:
    """Halt all trading activity at the operational level."""
    return await _accept("halt_trading")


@router.post(
    "/resume-trading",
    response_model=RpcCommandResponse,
    dependencies=[Depends(rate_limit_dependency)],
)
async def resume_trading(
    _principal: Annotated[AuthenticatedPrincipal, require_scope("admin")],
) -> RpcCommandResponse:
    """Resume trading activity after an operational halt."""
    return await _accept("resume_trading")


@router.post(
    "/cancel-order",
    response_model=RpcCommandResponse,
    dependencies=[Depends(rate_limit_dependency)],
)
async def cancel_order(
    request: RpcCommandRequest,
    _principal: Annotated[AuthenticatedPrincipal, require_scope("write:orders")],
) -> RpcCommandResponse:
    """Request cancellation of an open order."""
    return await _accept("cancel_order", request.parameters)


@router.get(
    "/commands/{command_id}",
    response_model=RpcCommandResult,
    dependencies=[Depends(rate_limit_dependency)],
)
async def get_command_status(
    command_id: UUID,
    _principal: Annotated[AuthenticatedPrincipal, require_scope("read:workflows")],
) -> RpcCommandResult:
    """Return the execution status/result of a previously enqueued command."""
    result = await get_result(str(command_id))
    if result is None:
        raise HTTPException(status_code=404, detail="unknown command id")
    return RpcCommandResult(
        command_id=command_id,
        command=result.get("command") or "unknown",
        status=result["status"],
        result=result.get("result"),
        error=result.get("error"),
        enqueued_at=result.get("enqueued_at"),
        processed_at=result.get("processed_at"),
    )
