"""In-process SSE broadcaster for the dashboard."""
from __future__ import annotations

import asyncio
import json


class Broadcaster:
    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue] = set()

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=256)
        self._subscribers.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self._subscribers.discard(q)

    def publish(self, event: dict) -> None:
        for q in list(self._subscribers):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                pass  # drop events for slow consumers instead of blocking publishers

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)


broadcaster = Broadcaster()


def sse_format(event: dict) -> str:
    return f"event: {event.get('type', 'message')}\ndata: {json.dumps(event, default=str)}\n\n"
