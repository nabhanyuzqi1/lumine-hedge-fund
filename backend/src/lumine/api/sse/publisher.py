# Copyright (c) 2026 Lumine. All rights reserved.
"""SSE event publisher with ring buffer and per-channel event management."""

from __future__ import annotations

import asyncio
import uuid
from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from lumine.trading.market_service import MarketService


@dataclass
class SSEEvent:
    """Structured SSE event for streaming."""

    event_type: str  # position_update, order_fill, tick_update, execution_order, stream_open, stream_resumed
    channel: str  # e.g., portfolio:{id}, orders, market:XAUUSD
    data: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def to_sse_format(self) -> str:
        """Convert to Server-Sent Events text format."""
        lines = [
            f"id: {self.event_id}",
            f"event: {self.event_type}",
            f"data: {to_json(self.data)}",
        ]
        return "\n".join(lines) + "\n\n"


def to_json(data: Any) -> str:
    """Serialize data to JSON string."""
    import orjson

    return orjson.dumps(data).decode("utf-8")


class SSEPublisher:
    """SSE event publisher with ring buffer support.

    Per docs/09-api/sse-api.md:
    - Event ring buffers bounded by count (100) and time (5 min retention)
    - Lifecycle events: stream_open, stream_resumed
    - Heartbeat comment every N seconds (default 30s)
    """

    HEARTBEAT_INTERVAL_SECONDS = 30
    MAX_EVENTS_PER_CHANNEL = 100
    RETENTION_SECONDS = 300  # 5 minutes

    def __init__(self, market_service: MarketService):
        self.market_service = market_service
        self._channels: dict[str, deque[SSEEvent]] = {}
        self._subscribers: set[asyncio.Queue] = set()
        self._heartbeat_task: asyncio.Task | None = None
        self._running = False

    async def subscribe(self) -> asyncio.Queue:
        """Subscribe to all SSE events.

        Returns a queue that receives SSEEvent objects.
        """
        queue: asyncio.Queue[SSEEvent] = asyncio.Queue(maxsize=1000)
        self._subscribers.add(queue)
        return queue

    async def unsubscribe(self, queue: asyncio.Queue) -> None:
        """Unsubscribe from SSE events."""
        self._subscribers.discard(queue)

    async def publish(self, event: SSEEvent) -> None:
        """Publish event to all subscribers and store in ring buffer.

        Event is stored per-channel with bounded ring buffer.
        """
        channel = event.channel

        # Store in channel buffer
        if channel not in self._channels:
            self._channels[channel] = deque(maxlen=self.MAX_EVENTS_PER_CHANNEL)

        self._channels[channel].append(event)

        # Remove old events beyond retention window
        await self._clean_old_events(channel)

        # Notify subscribers
        for queue in self._subscribers:
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                pass  # Subscriber too slow, drop event

    async def publish_position_update(
        self,
        portfolio_id: str,
        position_id: str,
        symbol: str,
        direction: str,
        volume: float,
        entry_price: float,
        current_price: float,
        pnl: float,
    ) -> None:
        """Publish position update event."""
        event = SSEEvent(
            event_type="position_update",
            channel=f"portfolio:{portfolio_id}:positions",
            data={
                "position_id": position_id,
                "symbol": symbol,
                "direction": direction,
                "volume": volume,
                "entry_price": entry_price,
                "current_price": current_price,
                "unrealized_pnl": pnl,
            },
        )
        await self.publish(event)

    async def publish_order_fill(
        self,
        order_id: str,
        status: str,
        fill_price: float,
        fill_volume: float,
        mt5_ticket: int | None = None,
    ) -> None:
        """Publish order fill/finalization event."""
        event = SSEEvent(
            event_type="order_fill",
            channel="orders",
            data={
                "order_id": order_id,
                "status": status,
                "fill_price": fill_price,
                "fill_volume": fill_volume,
                "mt5_ticket": mt5_ticket,
            },
        )
        await self.publish(event)

    async def publish_tick_update(self, symbol: str, bid: float, ask: float) -> None:
            """Publish tick price update event."""
            event = SSEEvent(
                event_type="tick_update",
                channel=f"market:{symbol}",
                data={
                    "symbol": symbol,
                    "bid": bid,
                    "ask": ask,
                    # PITFALL (18 Aug 2026): frontend MarketTick butuh `last`
                    # untuk live chart + isStale — tanpanya chart beku & label
                    # "waiting for live data / market closed" muncul terus.
                    "last": bid,
                    "timestamp": datetime.now(UTC).isoformat(),
                },
            )
            await self.publish(event)

    async def publish_stream_open(self, channel: str) -> None:
        """Publish stream open lifecycle event."""
        event = SSEEvent(
            event_type="stream_open",
            channel=channel,
            data={"connected_at": datetime.now(UTC).isoformat()},
        )
        await self.publish(event)

    async def publish_stream_resumed(self, channel: str, missed_count: int) -> None:
        """Publish stream resumed lifecycle event."""
        event = SSEEvent(
            event_type="stream_resumed",
            channel=channel,
            data={
                "resumed_at": datetime.now(UTC).isoformat(),
                "missed_events": missed_count,
            },
        )
        await self.publish(event)

    async def publish_analyst_output(
        self,
        portfolio_id: str,
        symbol: str,
        analyst_name: str,
        recommendation: str,
        confidence: float,
        reasoning: str,
    ) -> None:
        """Publish analyst output event for workflow decisions."""
        event = SSEEvent(
            event_type="analyst_output",
            channel="analyst-outputs",
            data={
                "portfolio_id": portfolio_id,
                "symbol": symbol,
                "analyst_name": analyst_name,
                "recommendation": recommendation,
                "confidence": confidence,
                "reasoning": reasoning,
                "timestamp": datetime.now(UTC).isoformat(),
            },
        )
        await self.publish(event)

    async def publish_ic_decision(
        self,
        decision_id: str,
        portfolio_id: str,
        action: str,
        positions: list[dict[str, Any]],
        confidence: float,
        reasoning: str,
    ) -> None:
        """Publish IC (Investment Committee) decision event."""
        event = SSEEvent(
            event_type="ic_decision",
            channel="ic-decisions",
            data={
                "decision_id": decision_id,
                "portfolio_id": portfolio_id,
                "action": action,
                "positions": positions,
                "confidence": confidence,
                "reasoning": reasoning,
                "timestamp": datetime.now(UTC).isoformat(),
            },
        )
        await self.publish(event)

    async def publish_cio_proposal(
        self,
        proposal_id: str,
        portfolio_id: str,
        allocation_changes: list[dict[str, Any]],
        expected_return: float,
        risk_score: float,
        reasoning: str,
    ) -> None:
        """Publish CIO capital allocation proposal event."""
        event = SSEEvent(
            event_type="cio_proposal",
            channel="cio-proposals",
            data={
                "proposal_id": proposal_id,
                "portfolio_id": portfolio_id,
                "allocation_changes": allocation_changes,
                "expected_return": expected_return,
                "risk_score": risk_score,
                "reasoning": reasoning,
                "timestamp": datetime.now(UTC).isoformat(),
            },
        )
        await self.publish(event)

    async def publish_risk_assessment(
        self,
        assessment_id: str,
        portfolio_id: str,
        risk_level: str,
        metrics: dict[str, Any],
        alerts: list[str],
    ) -> None:
        """Publish risk assessment event."""
        event = SSEEvent(
            event_type="risk_assessment",
            channel="risk-assessments",
            data={
                "assessment_id": assessment_id,
                "portfolio_id": portfolio_id,
                "risk_level": risk_level,
                "metrics": metrics,
                "alerts": alerts,
                "timestamp": datetime.now(UTC).isoformat(),
            },
        )
        await self.publish(event)

    async def publish_execution_order(
        self,
        order_id: str,
        portfolio_id: str,
        symbol: str,
        action: str,
        status: str,
        quantity: float,
        price: float | None,
    ) -> None:
        """Publish execution order lifecycle event."""
        event = SSEEvent(
            event_type="execution_order",
            channel="execution-orders",
            data={
                "order_id": order_id,
                "portfolio_id": portfolio_id,
                "symbol": symbol,
                "action": action,
                "status": status,
                "quantity": quantity,
                "price": price,
                "timestamp": datetime.now(UTC).isoformat(),
            },
        )
        await self.publish(event)

    async def start_heartbeat(self) -> None:
        """Start background heartbeat task."""
        if self._heartbeat_task and not self._heartbeat_task.done():
            return

        self._running = True
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

    async def stop_heartbeat(self) -> None:
        """Stop background heartbeat task."""
        self._running = False
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass

    async def _heartbeat_loop(self) -> None:
        """Send periodic heartbeat events."""
        while self._running:
            await asyncio.sleep(self.HEARTBEAT_INTERVAL_SECONDS)

            # Send heartbeat to all channels as comment-style line
            for channel in list(self._channels.keys()):
                await self._send_heartbeat(channel)

    async def _send_heartbeat(self, channel: str) -> None:
        """Send heartbeat comment for a channel."""
        heartbeat_event = SSEEvent(
            event_type="heartbeat",
            channel=channel,
            data={"type": "heartbeat"},
        )
        await self.publish(heartbeat_event)

    async def _clean_old_events(self, channel: str) -> None:
        """Remove events older than retention window."""
        if channel not in self._channels:
            return

        cutoff = datetime.now(UTC) - timedelta(seconds=self.RETENTION_SECONDS)

        while self._channels[channel]:
            oldest = self._channels[channel][0]
            if oldest.timestamp < cutoff:
                self._channels[channel].popleft()
            else:
                break

    async def get_channel_history(self, channel: str, limit: int = 10) -> list[SSEEvent]:
        """Get recent events from channel history."""
        if channel not in self._channels:
            return []

        events = list(self._channels[channel])
        return events[-limit:]
