# Copyright (c) 2026 Lumine. All rights reserved.
"""Idempotency key protection for write endpoints — docs/09-api/error-contract.md:178-189.

Contract:
- `X-Idempotency-Key` header on POST requests.
- Same key + same body within 1h → HTTP 200, original success envelope
  with `meta.idempotent_replay: true`.
- Same key + different body → HTTP 409 `CONFLICT`; client must use a new key.
- Window: 1 hour (Redis TTL + in-record timestamp check).

Fail-open on Redis errors: availability wins for replay protection, the
worst case is a duplicate execution, not a blocked write path.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import time
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

from starlette.datastructures import Headers

from lumine.data.redis_client import get_redis

_IDEMPOTENCY_TTL_S = 3600  # 1h window (error-contract.md:182)

Receive = Callable[[], Awaitable[dict[str, Any]]]
Send = Callable[[dict[str, Any]], Awaitable[None]]


async def _drain_body(receive: Receive) -> bytes:
    """Read the full request body from the receive channel."""
    chunks: list[bytes] = []
    more = True
    while more:
        message = await receive()
        if message["type"] == "http.disconnect":
            break
        chunks.append(message.get("body", b""))
        more = message.get("more_body", False)
    return b"".join(chunks)


def _resume_receive(body: bytes) -> Receive:
    """Replay a drained request body into the downstream app."""
    served = False

    async def _receive() -> dict[str, Any]:
        nonlocal served
        if not served:
            served = True
            return {"type": "http.request", "body": body, "more_body": False}
        return {"type": "http.disconnect"}

    return _receive


class IdempotencyMiddleware:
    """Replay stored success responses for reused idempotency keys."""

    def __init__(self, app: Callable[..., Any]) -> None:
        """Wrap the ASGI app with idempotency handling."""
        self.app: Callable[..., Any] = app

    async def __call__(self, scope: dict[str, Any], receive: Receive, send: Send) -> None:
        """Intercept POST requests carrying an idempotency key."""
        if scope["type"] != "http" or scope["method"] != "POST":
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        idem_key = headers.get("x-idempotency-key")
        if not idem_key:
            await self.app(scope, receive, send)
            return
        request_id = headers.get("x-request-id") or uuid.uuid4().hex

        api_key = headers.get("x-lumine-api-key", "anonymous")
        path = scope["path"]
        if scope.get("query_string"):
            path = f"{path}?{scope['query_string'].decode()}"
        store_key = f"lumine:idem:{api_key}:{scope['method']}:{path}:{idem_key}"

        body = await _drain_body(receive)
        body_hash = hashlib.sha256(body).hexdigest()

        try:
            redis = await get_redis()
            cached = await redis.get(store_key)
        except (OSError, ConnectionError, TimeoutError):
            # Fail-open: Redis outage must not block writes.
            await self.app(scope, _resume_receive(body), send)
            return

        if cached:
            try:
                record: dict[str, Any] = json.loads(cached)
            except json.JSONDecodeError:
                record = {}
            fresh = time.time() - record.get("created_at", 0) <= _IDEMPOTENCY_TTL_S
            if record and fresh:
                if record.get("body_hash") == body_hash:
                    await self._replay(record, send)
                    return
                await self._conflict(idem_key, request_id, send)
                return
            with contextlib.suppress(Exception):
                await redis.delete(store_key)

        # Fresh request: forward and capture the response for replay.
        status_code = await self._forward_and_capture(scope, send, body)
        if 200 <= status_code < 300:
            response_body = b"".join(self._captured)
            with contextlib.suppress(Exception):
                await redis.set(
                    store_key,
                    json.dumps(
                        {
                            "created_at": time.time(),
                            "body_hash": body_hash,
                            "status_code": status_code,
                            "body": response_body.decode(),
                        }
                    ),
                    ex=_IDEMPOTENCY_TTL_S,
                )

    async def _forward_and_capture(
        self,
        scope: dict[str, Any],
        send: Send,
        body: bytes,
    ) -> int:
        """Run the downstream app, capturing the response body chunks."""
        self._captured: list[bytes] = []
        status_code = 200

        async def _capture_send(message: dict[str, Any]) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
            elif message["type"] == "http.response.body":
                self._captured.append(message.get("body", b""))
            await send(message)

        await self.app(scope, _resume_receive(body), _capture_send)
        return status_code

    async def _replay(self, record: dict[str, Any], send: Send) -> None:
        """Return the stored success envelope marked as a replay."""
        try:
            envelope = json.loads(record.get("body", "{}"))
            envelope["meta"]["idempotent_replay"] = True
            payload = json.dumps(envelope).encode()
        except (json.JSONDecodeError, KeyError, TypeError):
            payload = str(record.get("body", "")).encode()
        status_code = int(record.get("status_code", 200))
        await send(
            {
                "type": "http.response.start",
                "status": status_code,
                "headers": [(b"content-type", b"application/json")],
            }
        )
        await send({"type": "http.response.body", "body": payload})

    async def _conflict(self, idem_key: str, request_id: str, send: Send) -> None:
        """Reject a reused key with a different body (409 CONFLICT)."""
        envelope = {
            "meta": {
                "api_version": "v1",
                "timestamp": datetime.now(UTC)
                .isoformat(timespec="milliseconds")
                .replace("+00:00", "Z"),
                "request_id": request_id,
                "status": "error",
            },
            "error": {
                "code": "CONFLICT",
                "message": f"idempotency key reused with different body: {idem_key}",
                "details": {},
                "trace_id": request_id,
            },
        }
        await send(
            {
                "type": "http.response.start",
                "status": 409,
                "headers": [(b"content-type", b"application/json")],
            }
        )
        await send({"type": "http.response.body", "body": json.dumps(envelope).encode()})
