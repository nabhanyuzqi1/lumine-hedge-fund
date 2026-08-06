# Copyright (c) 2026 Lumine. All rights reserved.
"""Persistence helpers for market data.

Bridges the deterministic collector core to PostgreSQL and Redis.
All I/O is explicit so the collector module stays testable without
infrastructure.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from lumine.data.models import Tick as TickModel
from lumine.data.redis_client import push_tick

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from lumine.data.collector import Bar, Tick


async def persist_tick(
    session: AsyncSession,
    tick: Tick,
    *,
    push_to_redis: bool = False,
) -> None:
    """Insert ``tick`` into PostgreSQL and optionally the Redis buffer."""
    session.add(
        TickModel(
            ts=tick.ts,
            symbol=tick.symbol,
            bid=tick.bid,
            ask=tick.ask,
            last=tick.last,
            volume=tick.volume,
            source=tick.source,
        )
    )
    if push_to_redis:
        await push_tick(
            tick.symbol,
            {
                "ts": tick.ts.isoformat(),
                "symbol": tick.symbol,
                "bid": str(tick.bid),
                "ask": str(tick.ask),
                "last": str(tick.last),
                "volume": str(tick.volume),
                "source": tick.source,
            },
        )


async def persist_bar(
    session: AsyncSession,
    bar: Bar,
    table: type[Any],
) -> None:
    """Insert ``bar`` into the specified ``table`` (e.g. Bars1M)."""
    session.add(
        table(
            ts=bar.ts,
            symbol=bar.symbol,
            open=bar.open_,
            high=bar.high,
            low=bar.low,
            close=bar.close,
            volume=bar.volume,
            source=bar.source,
        )
    )
