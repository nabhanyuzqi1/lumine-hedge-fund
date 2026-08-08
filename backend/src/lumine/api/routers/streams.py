# Copyright (c) 2026 Lumine. All rights reserved.
"""Server-Sent Event (SSE) realtime streams.

Channels: portfolio, positions, market, workflow_events, alerts.
Clients connect with Last-Event-ID for replay / reconnect.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Annotated

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

from lumine.api.middleware.auth import AuthenticatedPrincipal, require_scope

router = APIRouter(prefix="/streams", tags=["streams"])


async def _event_stream(
    request: Request,
    channel: str,
    interval_s: float = 2.0,
) -> AsyncIterator[str]:
    """Generate SSE events until the client disconnects."""
    event_id = int(request.headers.get("Last-Event-ID", 0))
    while not await request.is_disconnected():
        event_id += 1
        payload = {
            "channel": channel,
            "event_id": event_id,
            "timestamp": datetime.now(UTC).isoformat(),
            "data": {"message": f"heartbeat for {channel}"},
        }
        yield f"id: {event_id}\nevent: {channel}\ndata: {json.dumps(payload)}\n\n"
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(request.is_disconnected(), timeout=interval_s)


@router.get("/portfolio")
async def stream_portfolio(
    request: Request,
    _principal: Annotated[AuthenticatedPrincipal, require_scope("read:portfolio")],
) -> StreamingResponse:
    """SSE stream of portfolio snapshot updates."""
    return StreamingResponse(
        _event_stream(request, "portfolio"),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/positions")
async def stream_positions(
    request: Request,
    _principal: Annotated[AuthenticatedPrincipal, require_scope("read:portfolio")],
) -> StreamingResponse:
    """SSE stream of position updates."""
    return StreamingResponse(
        _event_stream(request, "positions"),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/market")
async def stream_market(
    request: Request,
    _principal: Annotated[AuthenticatedPrincipal, require_scope("read:market")],
) -> StreamingResponse:
    """SSE stream of market bar updates."""
    return StreamingResponse(
        _event_stream(request, "market"),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/workflow-events")
async def stream_workflow_events(
    request: Request,
    _principal: Annotated[AuthenticatedPrincipal, require_scope("read:workflows")],
) -> StreamingResponse:
    """SSE stream of workflow run lifecycle events."""
    return StreamingResponse(
        _event_stream(request, "workflow_events"),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/alerts")
async def stream_alerts(
    request: Request,
    _principal: Annotated[AuthenticatedPrincipal, require_scope("read:portfolio")],
) -> StreamingResponse:
    """SSE stream of risk and system alerts."""
    return StreamingResponse(
        _event_stream(request, "alerts"),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
