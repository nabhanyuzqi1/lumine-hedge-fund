# Copyright (c) 2026 Lumine. All rights reserved.
"""Redis-based bridge for MT5 Expert Advisor communication."""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from uuid import UUID

import redis.asyncio as redis

from lumine.shared.config import get_settings


@dataclass
class CommandMessage:
    """Command from Python backend → MT5 EA."""

    command_id: str
    order_id: str
    action: str  # OPEN, CLOSE, MODIFY
    symbol: str
    volume: float
    order_type: str  # BUY, SELL
    stop_loss: float | None = None
    take_profit: float | None = None
    idempotency_key: str = ""
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(UTC).isoformat()
        if not self.idempotency_key:
            self.idempotency_key = f"{self.order_id}:attempt_1"


@dataclass
class ResultMessage:
    """Result from MT5 EA → Python backend."""

    command_id: str
    order_id: str
    ticket: int
    status: str  # FILLED, PARTIAL, REJECTED, ERROR
    fill_price: float | None = None
    fill_volume: float | None = None
    error_code: int = 0
    error_message: str = ""
    timestamp: str = ""


class MT5Bridge:
    """Redis bridge for MT5 Expert Advisor communication.

    Pattern per docs/08-trading/mt5-integration.md:
    - Commands: LPUSH to queue, BRPOP from EA side
    - Results: PUBLISH channel, SUBSCRIBE from Python side
    - Idempotency: SET key NX EX 3600 before sending commands
    - Timeout: 30s default, then mark FAILED
    """

    COMMAND_QUEUE = "mt5:commands"
    RESULT_CHANNEL = "mt5:results"
    IDEMPOTENCY_PREFIX = "mt5:idempotency:"
    TIMEOUT_SECONDS = 30

    def __init__(self, redis_client: redis.Redis):
        self.redis = redis_client
        self._result_callbacks: list[Callable[[ResultMessage], None]] = []
        self._sub_task: asyncio.Task | None = None
        self._running = False

    async def send_command(self, message: CommandMessage) -> str:
        """Send execution command to MT5 EA via Redis queue.

        Returns command_id for tracking response.
        Checks idempotency before sending.
        """
        # Check idempotency
        idempotency_key = self.IDEMPOTENCY_PREFIX + message.idempotency_key
        exists = await self.redis.set(idempotency_key, "1", nx=True, ex=3600)

        if exists is False:
            # Already sent this command, skip
            raise ValueError(f"Idempotent command already sent: {message.idempotency_key}")

        # Push to command queue
        payload = json.dumps(asdict(message))
        await self.redis.lpush(self.COMMAND_QUEUE, payload)

        return message.command_id

    async def subscribe_results(self, timeout: int | None = None) -> None:
        """Subscribe to result messages from MT5 EA.

        Blocks until subscribed or timeout reached.
        Call handle_result callback when messages arrive.
        """
        pubsub = self.redis.pubsub()
        await pubsub.subscribe(self.RESULT_CHANNEL)

        self._running = True

        try:
            while self._running:
                message = await pubsub.get_message(timeout=timeout or 1.0)

                if message and message["type"] == "message":
                    try:
                        payload = json.loads(message["data"])
                        # EA kirim {id, order_id?, status, ticket, error, fill_price}
                        # — map tolerant ke ResultMessage (PITFALL: field "id"
                        # bukan command_id → ResultMessage(**payload) TypeError).
                        raw_id = payload.get("id", "") or payload.get("command_id", "")
                        result = ResultMessage(
                            command_id=raw_id,
                            order_id=payload.get("order_id", "") or raw_id,
                            ticket=int(payload.get("ticket", 0) or 0),
                            status=payload.get("status", "ERROR"),
                            fill_price=payload.get("fill_price"),
                            fill_volume=payload.get("fill_volume"),
                            error_code=int(payload.get("error_code", 0) or 0),
                            error_message=payload.get("error", "") or payload.get("error_message", ""),
                            timestamp=payload.get("timestamp", ""),
                        )
                        await self._on_result(result)
                    except Exception:
                        pass  # Log error in production
        finally:
            await pubsub.unsubscribe(self.RESULT_CHANNEL)
            await pubsub.close()

    async def _on_result(self, result: ResultMessage) -> None:
        """Process incoming result and notify callbacks."""
        for callback in self._result_callbacks:
            try:
                callback(result)
            except Exception:
                pass  # Individual callback errors should not block others

    def on_result(self, callback: Callable[[ResultMessage], None]) -> None:
        """Register callback for result messages."""
        self._result_callbacks.append(callback)

    async def start(self) -> None:
        """Start background result subscription task."""
        if self._sub_task and not self._sub_task.done():
            return

        self._running = True
        self._sub_task = asyncio.create_task(self.subscribe_results())

    async def stop(self) -> None:
        """Stop background result subscription task."""
        self._running = False
        if self._sub_task:
            self._sub_task.cancel()
            try:
                await self._sub_task
            except asyncio.CancelledError:
                pass

    @classmethod
    async def connect(cls, settings=None) -> MT5Bridge:
        """Create and configure MT5Bridge instance."""
        if settings is None:
            settings = get_settings()

        redis_url = getattr(settings, "redis_url", "redis://localhost:6379")
        client = await redis.from_url(redis_url)

        return cls(client)

    @classmethod
    async def from_url(cls, url: str) -> MT5Bridge:
        """Create MT5Bridge from Redis URL string."""
        client = await redis.from_url(url)
        return cls(client)


# Helper functions for creating messages


def create_open_order_command(
    order_id: UUID,
    symbol: str,
    volume: float,
    order_type: str,
    stop_loss: float | None = None,
    take_profit: float | None = None,
) -> CommandMessage:
    """Create OPEN command for new order."""
    return CommandMessage(
        command_id=str(uuid.uuid4()),
        order_id=str(order_id),
        action="OPEN",
        symbol=symbol,
        volume=volume,
        order_type=order_type,
        stop_loss=stop_loss,
        take_profit=take_profit,
    )


def create_close_order_command(
    order_id: UUID,
    mt5_ticket: int,
) -> CommandMessage:
    """Create CLOSE command to close existing position."""
    return CommandMessage(
        command_id=str(uuid.uuid4()),
        order_id=str(order_id),
        action="CLOSE",
        symbol="",
        volume=0.0,
        order_type="",
    )
