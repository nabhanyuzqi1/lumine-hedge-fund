# Copyright (c) 2026 Lumine. All rights reserved.
"""Level 2 integration tests for FeatureProvider.

Verifies FeatureProvider reads real bars from PostgreSQL (testcontainers),
computes indicators with the pure functions, caches them in real Redis,
and reads the real Redis tick buffer. No mocks for PG/Redis.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

import pytest
import pytest_asyncio

from lumine.data.collector import build_bar
from lumine.data.models import Bars1M
from lumine.data.persistence import persist_bar
from lumine.data.redis_client import close_redis, get_recent_ticks, get_redis, push_tick
from lumine.features.indicators import atr, ema, pivot_points, rsi
from lumine.features.provider import FeatureProvider
from lumine.shared.types import Timeframe

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    import redis.asyncio as aioredis
    from sqlalchemy.ext.asyncio import AsyncSession


@pytest_asyncio.fixture(autouse=True)
async def _reset_redis_singleton() -> AsyncIterator[aioredis.Redis]:
    """Force a fresh Redis client per test to avoid cross-loop binding."""
    await close_redis()
    client = await get_redis()
    await client.flushdb()
    yield client
    await client.flushdb()
    await close_redis()


def _bars() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Fifteen ascending XAUUSD bars, as persist states and indicator dicts."""
    persist_states: list[dict[str, Any]] = []
    indicator_bars: list[dict[str, Any]] = []
    for i in range(15):
        close = Decimal("2500.00") + Decimal(i)
        ts = datetime(2026, 8, 3, 12, 0, 0, tzinfo=UTC).replace(minute=i)
        persist_states.append(
            {
                "ts": ts,
                "open": close - Decimal("1.0"),
                "high": close + Decimal("2.0"),
                "low": close - Decimal("2.0"),
                "close": close,
                "volume": Decimal("1.0"),
                "source": "test",
            }
        )
        indicator_bars.append(
            {
                "ts": ts,
                "open_": close - Decimal("1.0"),
                "high": close + Decimal("2.0"),
                "low": close - Decimal("2.0"),
                "close": close,
                "volume": Decimal("1.0"),
                "source": "test",
            }
        )
    return persist_states, indicator_bars


@pytest_asyncio.fixture
async def xauusd_bars(db_session: AsyncSession) -> list[dict[str, Any]]:
    """Persist 15 bars to bars_1m; return the indicator-view dicts."""
    persist_states, indicator_bars = _bars()
    for state in persist_states:
        await persist_bar(db_session, build_bar("XAUUSD", state), Bars1M)
    await db_session.flush()
    return indicator_bars


class TestFeatureProviderReadsPostgres:
    """Snapshot assembly from real PostgreSQL bars."""

    async def test_indicators_match_pure_functions(
        self, db_session: AsyncSession, xauusd_bars: list[dict[str, Any]]
    ) -> None:
        provider = FeatureProvider(redis=await get_redis())
        snapshot = await provider.get_features(db_session, "XAUUSD", Timeframe.M1, count=15)

        assert snapshot.indicators["atr_14"] == atr(xauusd_bars, period=14)
        assert snapshot.indicators["ema_12"] == ema(xauusd_bars, period=12)
        assert snapshot.indicators["rsi_14"] == rsi(xauusd_bars, period=14)
        assert snapshot.pivots == pivot_points(xauusd_bars)
        assert snapshot.as_of_ts == xauusd_bars[-1]["ts"]

    @pytest.mark.usefixtures("xauusd_bars")
    async def test_indicators_written_to_redis_cache(
        self, db_session: AsyncSession
    ) -> None:
        provider = FeatureProvider(redis=await get_redis())
        snapshot = await provider.get_features(db_session, "XAUUSD", Timeframe.M1, count=15)

        client = await get_redis()
        raw = await client.get("feat:XAUUSD:atr_14")
        assert raw is not None
        decoded = raw.decode() if isinstance(raw, bytes) else raw
        assert Decimal(decoded) == snapshot.indicators["atr_14"]


class TestFeatureProviderRedisCache:
    """Cache-hit behavior against real Redis."""

    async def test_cached_value_wins_over_computation(
        self, db_session: AsyncSession, xauusd_bars: list[dict[str, Any]]
    ) -> None:
        client = await get_redis()
        await client.setex("feat:XAUUSD:atr_14", 60, "2.5")

        provider = FeatureProvider(redis=client)
        snapshot = await provider.get_features(db_session, "XAUUSD", Timeframe.M1, count=15)

        assert snapshot.indicators["atr_14"] == Decimal("2.5")
        # The planted cache value differs from the computed value, proving
        # the provider took the cache path instead of recomputing.
        assert Decimal("2.5") != atr(xauusd_bars, period=14)


class TestFeatureProviderTicks:
    """Tick buffer reads against real Redis."""

    @pytest.mark.usefixtures("xauusd_bars")
    async def test_recent_ticks_are_read(
        self,
        db_session: AsyncSession,
    ) -> None:
        client = await get_redis()
        for i in range(5):
            await push_tick(
                "XAUUSD",
                {
                    "ts": datetime(2026, 8, 3, 12, 0, 10 * i, tzinfo=UTC).isoformat(),
                    "symbol": "XAUUSD",
                    "bid": str(Decimal("2500.00") + Decimal(i)),
                    "ask": str(Decimal("2500.10") + Decimal(i)),
                    "last": str(Decimal("2500.05") + Decimal(i)),
                    "volume": "1.0",
                    "source": "mt5",
                },
            )

        provider = FeatureProvider(redis=client)
        snapshot = await provider.get_features(db_session, "XAUUSD", Timeframe.M1, count=15)

        recent = await get_recent_ticks("XAUUSD", count=5)
        assert len(recent) == 5
        assert recent[0]["symbol"] == "XAUUSD"
        assert snapshot.symbol == "XAUUSD"
