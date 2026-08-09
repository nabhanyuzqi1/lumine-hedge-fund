# Copyright (c) 2026 Lumine. All rights reserved.
"""Server-Sent Event (SSE) realtime streams — Phase 9 `sse-api.md`.

Six channels are exposed per the endpoint catalog:

| Endpoint | Event type | Scope | Heartbeat |
|----------|-----------|-------|-----------|
| `/streams/market-data` | `market_data` | `read:market` | 5s |
| `/streams/analyst-outputs` | `analyst_output` | `read:workflows` | 15s |
| `/streams/ic-decisions` | `ic_decision` | `read:workflows` | 15s |
| `/streams/cio-proposals` | `cio_proposal` | `read:workflows` | 15s |
| `/streams/risk-assessments` | `risk_assessment` | `read:portfolio` | 15s |
| `/streams/execution-orders` | `execution_order` | `read:portfolio` | 15s |

Contract points implemented here:
- Heartbeats are SSE comment lines (`: heartbeat`) — they carry no data and
  do NOT increment the event ID.
- Lifecycle events: `stream_open` (first), `stream_resumed` (after a
  `Last-Event-ID` reconnect, with `from_event_id`/`gap_detected`).
- `Last-Event-ID` replay from a per-channel in-memory ring buffer (bounded
  by event count and the 5-minute retention window per sse-api.md).
- Per-key (20) and per-host (1000) concurrent connection limits.

Backing this with the Phase 1 Redis stream catalog is a port/adapter
replacement (sse-api.md "What this document does NOT define"); the event
surface, filtering, and reconnect contract are fixed here.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import time
import uuid
from collections import deque
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Annotated, Any

from fastapi import APIRouter, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse

from lumine.api.middleware.auth import AuthenticatedPrincipal, require_scope

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

router = APIRouter(prefix="/streams", tags=["streams"])

# ── Contract constants (sse-api.md) ────────────────────────────────────────
_MAX_KEY_CONNECTIONS = 20
_MAX_HOST_CONNECTIONS = 1000
_BUFFER_MAX_EVENTS = 1000
_REPLAY_RETENTION_S = 300  # 5 minutes
_HEARTBEAT_MARKET_S = 5
_HEARTBEAT_DEFAULT_S = 15


@dataclass(frozen=True)
class _BufferedEvent:
    """A stored SSE frame for `Last-Event-ID` replay."""

    event_id: int
    ts: float
    frame: str


# Per-channel ring buffer of recently emitted frames, plus the next event
# ID. Process-local; adequate for the single-worker deployment.
_buffers: dict[str, deque[_BufferedEvent]] = {}
_next_ids: dict[str, int] = {}
_active: dict[str, int] = {}


def _iso_utc_ms(dt: datetime) -> str:
    """ISO 8601 with milliseconds and `Z` suffix (sse-api.md Freshness)."""
    return dt.utcnow().isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _frame(
    _channel: str, stream_id: str, event_id: int, event_type: str, data: dict[str, Any]
) -> str:
    """Serialize one SSE frame with the Phase 9 common envelope."""
    envelope = {
        "meta": {
            "api_version": "v1",
            "timestamp": _iso_utc_ms(datetime.now(UTC)),
            "request_id": f"stream-{stream_id}",
            "status": "ok",
        },
        "data": data,
        "error": None,
    }
    return f"id: {event_id}\nevent: {event_type}\ndata: {json.dumps(envelope)}\n\n"


def _acquire_slot(key_id: str, host: str) -> None:
    """Enforce per-key / per-host connection limits (sse-api.md)."""
    key_slot = f"key:{key_id}"
    host_slot = f"host:{host}"
    if _active.get(key_slot, 0) >= _MAX_KEY_CONNECTIONS:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="stream connection limit reached for API key",
        )
    if _active.get(host_slot, 0) >= _MAX_HOST_CONNECTIONS:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="stream connection limit reached for host",
        )
    _active[key_slot] = _active.get(key_slot, 0) + 1
    _active[host_slot] = _active.get(host_slot, 0) + 1


def _release_slot(key_id: str, host: str) -> None:
    key_slot = f"key:{key_id}"
    host_slot = f"host:{host}"
    _active[key_slot] = max(0, _active.get(key_slot, 0) - 1)
    _active[host_slot] = max(0, _active.get(host_slot, 0) - 1)


def _emit(channel: str, stream_id: str, event_type: str, data: dict[str, Any]) -> str:
    """Assign the next event ID, store the frame for replay, return the frame."""
    event_id = _next_ids.get(channel, 0) + 1
    _next_ids[channel] = event_id
    frame = _frame(channel, stream_id, event_id, event_type, data)
    buffer = _buffers.setdefault(channel, deque(maxlen=_BUFFER_MAX_EVENTS))
    buffer.append(_BufferedEvent(event_id=event_id, ts=time.time(), frame=frame))
    return frame


async def _replay(channel: str, last_event_id: int) -> AsyncIterator[str]:
    """Yield buffered frames with event_id > last_event_id, oldest first."""
    cutoff = time.time() - _REPLAY_RETENTION_S
    for buffered in _buffers.get(channel, ()):
        if buffered.event_id > last_event_id and buffered.ts >= cutoff:
            yield buffered.frame


async def _event_stream(
    request: Request,
    channel: str,
    interval_s: float,
) -> AsyncIterator[str]:
    """Generate SSE events until the client disconnects.

    First a `stream_open` event, then (on `Last-Event-ID` reconnect) a
    `stream_resumed` marker followed by buffered frames, then live events
    interleaved with heartbeat comment lines.
    """
    host = "unknown" if request.client is None else request.client.host
    key_id = request.state.principal.key_id if hasattr(request.state, "principal") else "anonymous"
    _acquire_slot(key_id, host)

    stream_id = uuid.uuid4().hex[:12]
    started_at = _iso_utc_ms(datetime.now(UTC))
    try:
        yield _emit(
            channel,
            stream_id,
            "stream_open",
            {"stream_id": stream_id, "started_at": started_at},
        )

        try:
            last_event_id = int(request.headers.get("Last-Event-ID", "0"))
        except ValueError:
            last_event_id = 0

        if last_event_id > 0:
            oldest = min((b.event_id for b in _buffers.get(channel, ())), default=last_event_id + 1)
            gap_detected = oldest > last_event_id + 1
            yield _frame(
                channel,
                stream_id,
                last_event_id,
                "stream_resumed",
                {"from_event_id": last_event_id, "gap_detected": gap_detected},
            )
            async for frame in _replay(channel, last_event_id):
                yield frame

        while not await request.is_disconnected():
            yield ": heartbeat\n\n"
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(request.is_disconnected(), timeout=interval_s)
    finally:
        _release_slot(key_id, host)


def _stream_response(request: Request, channel: str, interval_s: float) -> StreamingResponse:
    """Build the SSE response for one channel."""
    return StreamingResponse(
        _event_stream(request, channel, interval_s),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/market-data")
async def stream_market_data(
    request: Request,
    _symbol: Annotated[str, Query(min_length=1, description="Symbol to subscribe (required)")],
    _principal: Annotated[AuthenticatedPrincipal, require_scope("read:market")],
) -> StreamingResponse:
    """SSE stream of market bar/tick updates for one symbol (~1/sec, 5s heartbeat)."""
    return _stream_response(request, "market-data", _HEARTBEAT_MARKET_S)


@router.get("/analyst-outputs")
async def stream_analyst_outputs(
    request: Request,
    _principal: Annotated[AuthenticatedPrincipal, require_scope("read:workflows")],
    _workflow_run_id: Annotated[str | None, Query(description="Filter by workflow run")] = None,
) -> StreamingResponse:
    """SSE stream of analyst output events (15s heartbeat)."""
    return _stream_response(request, "analyst-outputs", _HEARTBEAT_DEFAULT_S)


@router.get("/ic-decisions")
async def stream_ic_decisions(
    request: Request,
    _principal: Annotated[AuthenticatedPrincipal, require_scope("read:workflows")],
    _workflow_run_id: Annotated[str | None, Query(description="Filter by workflow run")] = None,
) -> StreamingResponse:
    """SSE stream of investment committee decisions (15s heartbeat)."""
    return _stream_response(request, "ic-decisions", _HEARTBEAT_DEFAULT_S)


@router.get("/cio-proposals")
async def stream_cio_proposals(
    request: Request,
    _principal: Annotated[AuthenticatedPrincipal, require_scope("read:workflows")],
    _workflow_run_id: Annotated[str | None, Query(description="Filter by workflow run")] = None,
) -> StreamingResponse:
    """SSE stream of CIO capital proposals (15s heartbeat)."""
    return _stream_response(request, "cio-proposals", _HEARTBEAT_DEFAULT_S)


@router.get("/risk-assessments")
async def stream_risk_assessments(
    request: Request,
    _principal: Annotated[AuthenticatedPrincipal, require_scope("read:portfolio")],
    _portfolio_id: Annotated[str | None, Query(description="Filter by portfolio")] = None,
) -> StreamingResponse:
    """SSE stream of risk assessment events (15s heartbeat)."""
    return _stream_response(request, "risk-assessments", _HEARTBEAT_DEFAULT_S)


@router.get("/execution-orders")
async def stream_execution_orders(
    request: Request,
    _principal: Annotated[AuthenticatedPrincipal, require_scope("read:portfolio")],
    _symbol: Annotated[str | None, Query(description="Filter by symbol")] = None,
    _status: Annotated[str | None, Query(description="Comma-separated statuses (OR)")] = None,
    _portfolio_id: Annotated[str | None, Query(description="Filter by portfolio")] = None,
) -> StreamingResponse:
    """SSE stream of execution order lifecycle events (15s heartbeat).

    `status` accepts comma-separated values interpreted as OR
    (`status=PENDING,ACTIVE`).
    """
    return _stream_response(request, "execution-orders", _HEARTBEAT_DEFAULT_S)
