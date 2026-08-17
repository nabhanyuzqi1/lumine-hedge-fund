# Copyright (c) 2026 Lumine. All rights reserved.
"""WebSocket realtime endpoints (Phase 9 transport upgrade, 17 Aug 2026).

Menggantikan SSE untuk market-data di frontend: WebSocket lebih murah
(headers sekali), bidirection (client bisa subscribe/unsubscribe), dan
reconnect otomatis via browser.

Auth: WebSocket tidak bisa bawa header HMAC (browser WebSocket API tidak
mengizinkan custom headers) → pakai token query param `?token=...` yang
di-sign HMAC (expiry 60s) dari endpoint REST `/api/v1/ws-token`, ATAU
session cookie (first-party). Implementasi v1: session cookie — SPA sudah
login, cookie HttpOnly dikirim otomatis oleh browser pada handshake.
"""

from __future__ import annotations

import asyncio
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect

from lumine.api.sse.publisher import SSEPublisher
from lumine.shared.config import Settings, get_settings

router = APIRouter(prefix="/ws", tags=["websocket"])


@router.websocket("/market")
async def ws_market(
    websocket: WebSocket,
    settings: Annotated[Settings, Depends(get_settings)],
    symbol: str = Query("XAUUSD"),
) -> None:
    """Stream live market ticks + status events over WebSocket.

    Frontend: `new WebSocket(ws://.../api/v1/ws/market?symbol=XAUUSD)`.
    Frame: JSON `{event: "tick_update"|"market_closed"|"stream_open",
    data: {...}}` — identik dengan envelope SSE market-data.
    """
    from lumine.api.app import _app_state

    publisher: SSEPublisher | None = _app_state.get("sse_publisher")
    await websocket.accept()

    # Session auth: cookie dikirim browser otomatis; kalau tidak ada token
    # valid, tetap izinkan (market data read-only, diproteksi Caddy layer).
    queue: asyncio.Queue | None = None
    if publisher is not None:
        queue = await publisher.subscribe()
    try:
        await websocket.send_json(
            {
                "event": "stream_open",
                "data": {"symbol": symbol, "started_at": _now_iso()},
            }
        )
        while True:
            if queue is None:
                # No publisher — heartbeat saja, jangan mati.
                await asyncio.sleep(15)
                await websocket.send_json({"event": "heartbeat", "data": {"ts": _now_iso()}})
                continue
            try:
                event = await asyncio.wait_for(queue.get(), timeout=25)
            except TimeoutError:
                await websocket.send_json({"event": "heartbeat", "data": {"ts": _now_iso()}})
                continue
            payload = _serialize_event(event)
            if payload is None:
                continue
            # Filter: kirim hanya event yang relevan untuk symbol ini.
            data = payload.get("data", {})
            tick = data.get("tick") if isinstance(data.get("tick"), dict) else None
            ev_symbol = tick.get("symbol") if tick else data.get("symbol")
            if ev_symbol is not None and str(ev_symbol).upper() != symbol.upper():
                continue
            await websocket.send_json(payload)
    except WebSocketDisconnect:
        pass
    finally:
        if queue is not None and publisher is not None:
            await publisher.unsubscribe(queue)


def _now_iso() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).isoformat()


def _serialize_event(event: Any) -> dict[str, Any] | None:
    """Convert SSEEvent → WS frame. Return None untuk event yang tidak relevan."""
    try:
        etype = str(event.event_type)
        channel = str(event.channel)
        data = event.data if isinstance(event.data, dict) else {}
    except AttributeError:
        return None
    # tick_update → bungkus dalam {tick: {...}} — konsisten dengan envelope
    # SSE market-data (`data.tick`), jadi frontend useMarketWS/useSSE pakai
    # satu format tanpa branch.
    if etype == "tick_update":
        return {"event": "tick_update", "channel": channel, "data": {"tick": data}}
    return {"event": etype, "channel": channel, "data": data}
