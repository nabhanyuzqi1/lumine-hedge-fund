# Copyright (c) 2026 Lumine. All rights reserved.
"""MT5 bridge client: sends commands and waits for results over Redis.

The client is intentionally thin: it serializes ``BridgeCommand`` instances,
pushes them to a Redis LIST, subscribes to a Redis PUB/SUB channel, and returns
the first ``BridgeResult`` whose ``command_id`` matches. All Redis I/O is
performed through the caller-supplied ``aioredis.Redis`` instance so tests can
substitute a fake without patching global state.
"""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING

from lumine.bridge.types import BridgeCommand, BridgeResult

if TYPE_CHECKING:
    import redis.asyncio as aioredis


class BridgeTimeoutError(TimeoutError):
    """Raised when no matching result arrives within the configured timeout."""


class BridgeClient:
    """Request/response client for the MT5 EA bridge."""

    def __init__(
        self,
        redis: aioredis.Redis,
        *,
        command_channel: str,
        result_channel: str,
        response_timeout_s: float,
    ) -> None:
        """Configure the bridge client."""
        self._redis = redis
        self._command_channel = command_channel
        self._result_channel = result_channel
        self._response_timeout_s = response_timeout_s

    async def send_command(self, command: BridgeCommand) -> None:
        """Serialize ``command`` and push it onto the MT5 command LIST."""
        payload = command.model_dump(mode="json")
        await self._redis.lpush(self._command_channel, json.dumps(payload))

    async def receive_result(self, command_id: str) -> BridgeResult | None:
        """Subscribe to results and return the first matching ``command_id``.

        Returns ``None`` only if the channel publishes a message that cannot be
        parsed as JSON. A timeout raises ``BridgeTimeoutError``.
        """
        pubsub = self._redis.pubsub()
        await pubsub.subscribe(self._result_channel)
        try:
            deadline = asyncio.get_event_loop().time() + self._response_timeout_s
            while True:
                remaining = deadline - asyncio.get_event_loop().time()
                if remaining <= 0:
                    msg = f"No result for {command_id} within {self._response_timeout_s}s"
                    raise BridgeTimeoutError(msg)
                message = await pubsub.get_message(
                    ignore_subscribe_messages=True, timeout=remaining
                )
                if message is None:
                    continue
                data = message.get("data")
                if isinstance(data, bytes):
                    data = data.decode()
                try:
                    parsed = json.loads(data)
                except (json.JSONDecodeError, TypeError):
                    continue
                result = BridgeResult.model_validate(parsed)
                if result.command_id == command_id:
                    return result
        finally:
            await pubsub.unsubscribe(self._result_channel)
            await pubsub.aclose()  # type: ignore[no-untyped-call]

    async def send_and_wait(self, command: BridgeCommand) -> BridgeResult:
        """Send ``command`` and block until its matching result arrives."""
        await self.send_command(command)
        result = await self.receive_result(command.command_id)
        if result is None:
            msg = f"No parseable result for {command.command_id} within {self._response_timeout_s}s"
            raise BridgeTimeoutError(msg)
        return result
