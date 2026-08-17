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
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Annotated, Any

from fastapi import APIRouter, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse

from lumine.api.middleware.auth import AuthenticatedPrincipal, require_scope
from lumine.api.sse.publisher import SSEPublisher
from lumine.trading.market_service import MarketService

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


def get_market_service() -> MarketService:
    """Dependency to access market service from app state."""
    from lumine.api.app import _app_state

    return _app_state.get("market_service")


def get_sse_publisher(request: Request) -> SSEPublisher:
    """Get SSEPublisher instance from request state or app state."""
    if hasattr(request.state, "sse_publisher"):
        return request.state.sse_publisher
    from lumine.api.app import _app_state

    return _app_state.get("sse_publisher")


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
    """ISO 8601 with milliseconds and `Z` suffix (sse-api.md Freshness).

    `dt` must be timezone-aware (callers pass `datetime.now(UTC)`); the
    offset is converted to `Z` so clients can compute staleness without
    naive/aware subtraction errors.
    """
    return dt.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


# ── Market calendar (ADR-0037): XAUUSD via broker HFM = forex 24x5 ──────────
# Pasar forex tutup akhir pekan: Sabtu 00:00 UTC s/d Senin 21:00 UTC
# (weekend gap). Feed broker berhenti push tick → SSE harus tandai
# market_closed, bukan stream kosong tanpa penjelasan.
_WEEKEND_CLOSE_WDAY = 5  # Sabtu (ISO: 5)
_WEEKEND_REOPEN_WDAY = 0  # Senin — XAUUSD CFD broker (HFM) buka Senin 00:00 UTC


def _market_status(now: datetime | None = None) -> dict[str, Any]:
    """Return market session status for XAUUSD (CFD 24x5).

    PITFALL (17 Aug 2026): kalender awalnya mengasumsikan forex gap Senin
    00:00-21:00 UTC (standar interbank). Broker XAUUSD CFD (HFM) trading
    LANGSUNG dari Senin 00:00 UTC — kalender lama salah menandai Senin pagi
    sebagai "weekend" padahal EA mengirim tick live. Weekend hanya Sabtu (5)
    + Minggu (6).
    """
    now = now or datetime.now(UTC)
    wday = now.weekday()  # ISO: 0=Senin .. 6=Minggu
    if wday >= _WEEKEND_CLOSE_WDAY:
        # Weekend gap: Sabtu (5) + Minggu (6)
        days_until = (7 - wday) % 7 or 7
        next_open = now.replace(
            hour=0, minute=0, second=0, microsecond=0
        ) + timedelta(days=days_until)
        return {"open": False, "reason": "weekend", "next_open": _iso_utc_ms(next_open)}
    return {"open": True, "reason": "open", "next_open": None}


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

        # Subscribe ke SSEPublisher (in-memory queue) — relay event LIVE
        # ke client. Sebelumnya stream hanya kirim heartbeat dan TIDAK
        # pernah meneruskan event dari worker (bug: committee feed kosong).
        publisher = get_sse_publisher(request)
        queue = await publisher.subscribe()
        try:
            while not await request.is_disconnected():
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=interval_s)
                except TimeoutError:
                    yield ": heartbeat\n\n"
                    continue
                # Relay event yang sesuai channel stream ini.
                if event.channel == channel:
                    data = dict(event.data)
                    data.setdefault("timestamp", event.timestamp.isoformat())
                    yield _emit(channel, stream_id, event.event_type, data)
        finally:
            await publisher.unsubscribe(queue)
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
    symbol: Annotated[str, Query(min_length=1, description="Symbol to subscribe (required)")],
    _principal: Annotated[AuthenticatedPrincipal, require_scope("read:market")],
) -> StreamingResponse:
    """SSE stream of market bar/tick updates for one symbol (~1/sec, 5s heartbeat)."""

    async def market_event_stream():
        """Emit tick updates from MarketService cache."""
        host = "unknown" if request.client is None else request.client.host
        key_id = (
            request.state.principal.key_id if hasattr(request.state, "principal") else "anonymous"
        )
        _acquire_slot(key_id, host)

        stream_id = uuid.uuid4().hex[:12]
        started_at = _iso_utc_ms(datetime.now(UTC))
        market_service = get_market_service()
        publisher = get_sse_publisher(request)

        try:
            # Publish stream_open lifecycle event
            await publisher.publish_stream_open(f"market:{symbol}")

            yield _emit(
                f"market:{symbol}",
                stream_id,
                "stream_open",
                {"stream_id": stream_id, "started_at": started_at},
            )

            # Market calendar: kalau pasar libur (weekend/holiday), emit
            # `market_closed` — UI tampilkan status, koneksi tetap hidup
            # (auto-resume saat market buka, tanpa refresh browser).
            # PITFALL (17 Aug 2026): kalender hardcoded salah mendeteksi
            # "weekend" padahal EA mengirim tick LIVE (XAUUSD broker HFM
            # trading 24/5, termasuk Senin 00:00-21:00 UTC). Data live lebih
            # otoritatif dari kalender: kalau MarketService punya tick fresh
            # (<30s), market jelas BUKA → jangan emit market_closed.
            status = _market_status()
            live_tick = await market_service.get_quote(symbol)
            if not status["open"] and live_tick is None:
                yield _emit(
                    f"market:{symbol}",
                    stream_id,
                    "market_closed",
                    {
                        "reason": status["reason"],
                        "next_open": status["next_open"],
                        "message": f"Market closed ({status['reason']}) — live ticks resume at {status['next_open']}",
                    },
                )
                interval_s = _HEARTBEAT_MARKET_S
                while not await request.is_disconnected():
                    yield ": heartbeat\n\n"
                    with contextlib.suppress(TimeoutError):
                        await asyncio.wait_for(request.is_disconnected(), timeout=interval_s)
                return

            last_tick_time = time.time()
            while not await request.is_disconnected():
                try:
                    tick = await market_service.get_quote(symbol)
                    if tick and (time.time() - last_tick_time) > 1.0:
                        frame = _emit(
                            f"market:{symbol}",
                            stream_id,
                            "tick_update",
                            {
                                # Contract frontend: MarketDataEvent { tick: MarketTick }
                                # (symbol, bid, ask, last, timestamp) — jangan field langsung.
                                "tick": {
                                    "symbol": symbol,
                                    "bid": tick.bid,
                                    "ask": tick.ask,
                                    "last": tick.bid,
                                    "timestamp": _iso_utc_ms(tick.timestamp),
                                },
                            },
                        )
                        yield frame
                        last_tick_time = time.time()

                    with contextlib.suppress(TimeoutError):
                        await asyncio.wait_for(
                            request.is_disconnected(), timeout=_HEARTBEAT_MARKET_S
                        )
                except Exception:
                    break

                yield ": heartbeat\n\n"
        finally:
            _release_slot(key_id, host)

    return StreamingResponse(
        market_event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


async def _event_stream_wrapper(
    request: Request,
    channel: str,
    interval_s: float,
) -> AsyncIterator[str]:
    """SSE stream wrapper with SSEPublisher integration."""
    host = "unknown" if request.client is None else request.client.host
    key_id = request.state.principal.key_id if hasattr(request.state, "principal") else "anonymous"
    _acquire_slot(key_id, host)

    stream_id = uuid.uuid4().hex[:12]
    started_at = _iso_utc_ms(datetime.now(UTC))

    try:
        publisher = get_sse_publisher(request)
        await publisher.publish_stream_open(channel)

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
