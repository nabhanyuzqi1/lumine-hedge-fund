# Copyright (c) 2026 Lumine. All rights reserved.
"""Request logging middleware — trace_id propagation and access logs.

Emits structlog entries per HTTP request with trace_id, method, path,
status, duration_ms, and api_key, and echoes the trace id back as the
X-Request-ID response header. The trace id also feeds the envelope's
meta.request_id / error.trace_id (control-plane.md observability contract).
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

import structlog.contextvars
from starlette.datastructures import Headers

from lumine.shared.logging import get_logger

Receive = Callable[[], Awaitable[dict[str, Any]]]
Send = Callable[[dict[str, Any]], Awaitable[None]]


class RequestLoggingMiddleware:
    """Log one start + one completion entry per HTTP request."""

    def __init__(self, app: Callable[..., Any]) -> None:
        """Wrap the ASGI app with trace_id logging."""
        self.app: Callable[..., Any] = app

    async def __call__(self, scope: dict[str, Any], receive: Receive, send: Send) -> None:
        """Wrap the app, propagating trace_id into contextvars and headers."""
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        trace_id = headers.get("x-request-id") or uuid.uuid4().hex
        started = time.monotonic()
        api_key = headers.get("x-lumine-api-key", "anonymous")

        logger = get_logger("api")
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(trace_id=trace_id, api_key=api_key)

        path = scope["path"]
        if scope.get("query_string"):
            path = f"{path}?{scope['query_string'].decode()}"
        logger.info("request_start", method=scope["method"], path=path)

        status_code = 0

        async def _send(message: dict[str, Any]) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                message.setdefault("headers", [])
                message["headers"].append((b"x-request-id", trace_id.encode()))
            await send(message)

        try:
            await self.app(scope, receive, _send)
        finally:
            duration_ms = round((time.monotonic() - started) * 1000, 2)
            if status_code:
                logger.info(
                    "request_complete",
                    status=status_code,
                    duration_ms=duration_ms,
                )
            else:
                logger.warning("request_aborted", duration_ms=duration_ms)
