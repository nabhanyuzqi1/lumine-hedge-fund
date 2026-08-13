# Copyright (c) 2026 Lumine. All rights reserved.
"""Market data service with tick price caching."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import orjson


@dataclass
class Tick:
    """Latest tick data for a symbol."""

    symbol: str
    bid: float
    ask: float
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    volume: float = 0.0


class MarketService:
    """
    In-memory cache of latest tick prices for subscribed symbols.

    Provides:
    - get_quote(symbol): Get current bid/ask for a symbol
    - update_tick(symbol, bid, ask): Receive fresh tick from MT5 feed
    - subscribe_symbols(symbols): Mark symbols as active subscriptions
    """

    def __init__(self):
        self._ticks: dict[str, Tick] = {}
        self._subscriptions: set[str] = set()
        self._lock = asyncio.Lock()

    async def get_quote(self, symbol: str) -> Tick | None:
        """
        Get latest quote for a symbol.

        Returns None if no cached data available.
        """
        async with self._lock:
            tick = self._ticks.get(symbol)

        if tick is None:
            return None

        # Check if data is stale (> 30s old)
        if datetime.now(UTC) - tick.timestamp > timedelta(seconds=30):
            return None

        return tick

    async def update_tick(self, symbol: str, bid: float, ask: float, volume: float = 0.0) -> None:
        """
        Update cached tick price for a symbol.

        Call this when receiving new price data from MT5 feed.
        """
        tick = Tick(
            symbol=symbol,
            bid=bid,
            ask=ask,
            timestamp=datetime.now(UTC),
            volume=volume,
        )

        async with self._lock:
            self._ticks[symbol] = tick

    async def get_spread(self, symbol: str) -> float | None:
        """Get spread in pips for a symbol."""
        tick = await self.get_quote(symbol)
        if tick is None:
            return None

        # Assume 5 decimal places for most pairs
        pip_size = 0.00001

        spread_points = (tick.ask - tick.bid) / pip_size
        return spread_points

    async def subscribe_symbols(self, symbols: list[str]) -> None:
        """Mark symbols as active subscriptions."""
        async with self._lock:
            self._subscriptions.update(symbols)

    async def is_subscribed(self, symbol: str) -> bool:
        """Check if symbol is actively subscribed."""
        async with self._lock:
            return symbol in self._subscriptions

    async def get_subscriptions(self) -> list[str]:
        """Get list of all active subscriptions."""
        async with self._lock:
            return list(self._subscriptions)

    async def get_all_ticks(self) -> dict[str, Tick]:
        """Get all cached ticks (used for initial SSE stream state)."""
        async with self._lock:
            return dict(self._ticks)

    def serialize_ticks(self) -> str:
        """Serialize all ticks to JSON string."""
        ticks_data = {
            symbol: {
                "symbol": tick.symbol,
                "bid": tick.bid,
                "ask": tick.ask,
                "timestamp": tick.timestamp.isoformat(),
                "volume": tick.volume,
            }
            for symbol, tick in self._ticks.items()
        }

        return orjson.dumps(ticks_data).decode("utf-8")
