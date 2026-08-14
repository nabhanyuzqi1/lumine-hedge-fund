# Copyright (c) 2026 Lumine. All rights reserved.
"""FeatureProvider serves point-in-time feature snapshots.

The provider reads OHLCV bars from PostgreSQL, recent ticks from Redis,
computes technical indicators via pure functions, and caches each indicator
under `feat:{symbol}:{name}`.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import desc, select

from lumine.data.models import Bars1M, Bars5M
from lumine.features.indicators import atr, ema, pivot_points, rsi
from lumine.features.types import FeatureSnapshot, PivotPoints
from lumine.shared.types import Timeframe

if TYPE_CHECKING:
    import redis.asyncio as aioredis
    from sqlalchemy.ext.asyncio import AsyncSession


TIMEFRAME_TABLES: dict[Timeframe, type[Any]] = {
    Timeframe.M1: Bars1M,
    Timeframe.M5: Bars5M,
}

FEATURE_CONFIG: list[dict[str, Any]] = [
    {"name": "atr_14", "fn": atr, "period": 14, "ttl": 60},
    {"name": "ema_12", "fn": ema, "period": 12, "ttl": 60},
    {"name": "rsi_14", "fn": rsi, "period": 14, "ttl": 60},
]


class FeatureProvider:
    """Async provider for feature snapshots."""

    def __init__(self, redis: aioredis.Redis) -> None:
        """Initialize provider with an async Redis client."""
        self.redis = redis

    def _table_for_timeframe(self, timeframe: Timeframe) -> type[Any]:
        try:
            return TIMEFRAME_TABLES[timeframe]
        except KeyError as exc:
            msg = f"unsupported timeframe: {timeframe}"
            raise ValueError(msg) from exc

    async def _fetch_bars(
        self,
        session: AsyncSession,
        symbol: str,
        timeframe: Timeframe,
        count: int,
    ) -> list[dict[str, Any]]:
        table = self._table_for_timeframe(timeframe)
        stmt = select(table).where(table.symbol == symbol).order_by(desc(table.ts)).limit(count)
        result = await session.execute(stmt)
        rows = result.scalars().all()
        normalized: list[dict[str, Any]] = []
        for row in reversed(rows):
            if isinstance(row, dict):
                normalized.append(row)
            else:
                normalized.append(
                    {
                        "ts": row.ts,
                        "open_": row.open,
                        "high": row.high,
                        "low": row.low,
                        "close": row.close,
                        "volume": row.volume,
                        "source": row.source,
                    }
                )
        return normalized

    async def _get_cached_indicator(self, symbol: str, name: str) -> Decimal | None:
        raw = await self.redis.get(f"feat:{symbol}:{name}")
        if raw is None:
            return None
        decoded = raw.decode() if isinstance(raw, bytes) else raw
        return Decimal(decoded)

    async def _cache_indicator(self, symbol: str, name: str, value: Decimal, ttl: int) -> None:
        await self.redis.setex(f"feat:{symbol}:{name}", ttl, str(value))

    async def _compute_indicator(
        self,
        bars: list[dict[str, Any]],
        symbol: str,
        config: dict[str, Any],
    ) -> Decimal | None:
        cached = await self._get_cached_indicator(symbol, config["name"])
        if cached is not None:
            return cached

        fn: Callable[..., Decimal] = config["fn"]
        period: int = config["period"]
        if len(bars) < period + 1:
            return None
        value = fn(bars, period=period)
        await self._cache_indicator(symbol, config["name"], value, config["ttl"])
        return value

    async def _compute_pivots(self, bars: list[dict[str, Any]]) -> PivotPoints | None:
        if not bars:
            return None
        return pivot_points(bars)

    async def _fetch_recent_ticks(self, symbol: str, count: int = 100) -> list[dict[str, Any]]:
        raw = await self.redis.lrange(f"ticks:{symbol}", 0, count - 1)
        return [json.loads(item.decode() if isinstance(item, bytes) else item) for item in raw]

    async def get_features(
        self,
        session: AsyncSession,
        symbol: str,
        timeframe: Timeframe,
        count: int,
    ) -> FeatureSnapshot:
        """Return a feature snapshot for the given symbol and timeframe."""
        bars = await self._fetch_bars(session, symbol, timeframe, count)
        as_of_ts = bars[-1]["ts"] if bars else datetime.now(UTC)

        indicators: dict[str, Decimal] = {}
        for config in FEATURE_CONFIG:
            value = await self._compute_indicator(bars, symbol, config)
            if value is not None:
                indicators[config["name"]] = value

        pivots = await self._compute_pivots(bars)
        await self._fetch_recent_ticks(symbol)

        return FeatureSnapshot(
            symbol=symbol,
            timeframe=timeframe,
            as_of_ts=as_of_ts,
            indicators=indicators,
            pivots=pivots,
        )
