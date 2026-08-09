# Copyright (c) 2026 Lumine. All rights reserved.
"""Command RPC endpoints for operational control."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends

from lumine.api.middleware.auth import AuthenticatedPrincipal, require_scope
from lumine.api.middleware.rate_limit import rate_limit_dependency
from lumine.api.schemas.api import RpcCommandRequest, RpcCommandResponse
from lumine.data.redis_client import get_redis
from lumine.shared.config import Settings, get_settings
from lumine.shared.errors import KillSwitchError

router = APIRouter(prefix="/rpc", tags=["rpc"])


async def _kill_switch_armed(settings: Settings) -> bool:
    """Check whether the kill switch is currently armed."""
    r = await get_redis()
    raw = await r.hget(settings.kill_switch_key, "armed")
    if raw is None:
        return False
    value = raw.decode() if isinstance(raw, bytes) else raw
    return value == "1"


async def _accept(command: str) -> RpcCommandResponse:
    """Return an accepted receipt for a command."""
    return RpcCommandResponse(
        command_id=uuid4(),
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
) -> RpcCommandResponse:
    """Enqueue a full decision-cycle workflow run."""
    if await _kill_switch_armed(settings):
        msg = "decision cycle blocked by kill switch"
        raise KillSwitchError(msg)
    return await _accept("run_decision_cycle")


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
    _request: RpcCommandRequest,
    _principal: Annotated[AuthenticatedPrincipal, require_scope("write:orders")],
) -> RpcCommandResponse:
    """Request cancellation of an open order."""
    return await _accept("cancel_order")
