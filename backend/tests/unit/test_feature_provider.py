# Copyright (c) 2026 Lumine. All rights reserved.
"""Unit tests for FeatureProvider.

The provider is exercised with mocked async SQLAlchemy sessions and mocked
Redis clients. I/O-free assertions verify SQL text, cache keys, and snapshot
contents.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from lumine.features.provider import FeatureProvider
from lumine.shared.types import Timeframe


def _mock_session(result_rows: list[Any]) -> AsyncSession:
    """Return a minimal mock AsyncSession whose execute returns the rows."""
    session = MagicMock(spec=AsyncSession)
    result = MagicMock()
    result.scalars.return_value.all = MagicMock(return_value=result_rows)
    session.execute = AsyncMock(return_value=result)
    return session


def _make_bar_dict(ts_minute: int, close: str) -> dict[str, Any]:
    ts = datetime(2026, 8, 3, 12, 0, 0, tzinfo=UTC).replace(minute=ts_minute)
    return {
        "ts": ts,
        "open_": Decimal(close) - Decimal("1.0"),
        "high": Decimal(close) + Decimal("2.0"),
        "low": Decimal(close) - Decimal("2.0"),
        "close": Decimal(close),
        "volume": Decimal("1.0"),
        "source": "test",
    }


@pytest.fixture
def redis_mock() -> AsyncMock:
    r = AsyncMock()
    r.get = AsyncMock(return_value=None)
    r.setex = AsyncMock(return_value=True)
    r.lrange = AsyncMock(return_value=[])
    return r


class TestFeatureProviderBasics:
    """Construction and timeframe mapping."""

    def test_unknown_timeframe_raises(self, redis_mock: AsyncMock) -> None:
        provider = FeatureProvider(redis=redis_mock)
        with pytest.raises(ValueError):  # noqa: PT011
            provider._table_for_timeframe(Timeframe.H4)  # noqa: SLF001


def _mock_orm_row(ts_minute: int, close: str) -> MagicMock:
    """Build an ORM-ish row object (Bars1M instance stand-in).

    ``_fetch_bars`` (provider.py:72-86) normalizes ORM objects through
    attribute access (row.ts, row.open, ...) — the mock must expose those
    attributes, not the dict shape ``_make_bar_dict`` produces.
    """
    row = MagicMock()
    row.ts = datetime(2026, 8, 3, 12, 0, 0, tzinfo=UTC).replace(minute=ts_minute)
    row.open = Decimal(close) - Decimal("1.0")
    row.high = Decimal(close) + Decimal("2.0")
    row.low = Decimal(close) - Decimal("2.0")
    row.close = Decimal(close)
    row.volume = Decimal("1.0")
    row.source = "test"
    return row


class TestFeatureProviderGetFeatures:
    """Snapshot assembly from bars + ticks + indicator cache."""

    async def test_get_features_queries_bars_ordered_by_ts(self, redis_mock: AsyncMock) -> None:
        bars = [_make_bar_dict(i, str(2500 + i)) for i in range(15)]
        session = _mock_session(bars)
        provider = FeatureProvider(redis=redis_mock)
        snapshot = await provider.get_features(session, "XAUUSD", Timeframe.M1, count=15)

        assert snapshot.symbol == "XAUUSD"
        assert snapshot.timeframe == Timeframe.M1
        assert len(snapshot.indicators) > 0
        assert snapshot.pivots is not None
        session.execute.assert_awaited_once()
        call_args = session.execute.await_args[0][0]
        assert "bars_1m" in str(call_args)
        assert "ORDER BY" in str(call_args).upper()

    async def test_get_features_uses_redis_cache_hit(self, redis_mock: AsyncMock) -> None:
        bars = [_make_bar_dict(i, str(2500 + i)) for i in range(15)]
        session = _mock_session(bars)
        redis_mock.get = AsyncMock(return_value=b"2.5")
        provider = FeatureProvider(redis=redis_mock)
        snapshot = await provider.get_features(session, "XAUUSD", Timeframe.M1, count=15)

        assert snapshot.indicators["atr_14"] == Decimal("2.5")

    async def test_get_features_caches_miss(self, redis_mock: AsyncMock) -> None:
        bars = [_make_bar_dict(i, str(2500 + i)) for i in range(15)]
        session = _mock_session(bars)
        redis_mock.get = AsyncMock(return_value=None)
        provider = FeatureProvider(redis=redis_mock)
        await provider.get_features(session, "XAUUSD", Timeframe.M1, count=15)

        calls = [c for c in redis_mock.setex.call_args_list if c.args[0] == "feat:XAUUSD:atr_14"]
        assert len(calls) == 1
        assert calls[0].args[1] == 60
        assert float(calls[0].args[2]) > 0

    async def test_get_features_includes_recent_ticks(self, redis_mock: AsyncMock) -> None:
        bars = [_make_bar_dict(i, str(2500 + i)) for i in range(15)]
        session = _mock_session(bars)
        provider = FeatureProvider(redis=redis_mock)
        await provider.get_features(session, "XAUUSD", Timeframe.M1, count=15)

        redis_mock.lrange.assert_awaited_once_with("ticks:XAUUSD", 0, 99)

    async def test_get_features_insufficient_bars(self, redis_mock: AsyncMock) -> None:
        bars = [_make_bar_dict(i, str(2500 + i)) for i in range(5)]
        session = _mock_session(bars)
        provider = FeatureProvider(redis=redis_mock)
        snapshot = await provider.get_features(session, "XAUUSD", Timeframe.M1, count=15)

        assert "atr_14" not in snapshot.indicators
        assert "ema_12" not in snapshot.indicators
        redis_mock.setex.assert_not_awaited()  # insufficient bars → never poison the cache

    async def test_get_features_normalizes_orm_rows(self, redis_mock: AsyncMock) -> None:
        # _fetch_bars (provider.py:72-86): the DB returns ORM objects, not
        # dicts — attribute access must be normalized so indicators can
        # read them (dict path is exercised by the other tests here).
        bars = [_mock_orm_row(i, str(2500 + i)) for i in range(15)]
        session = _mock_session(bars)
        redis_mock.get = AsyncMock(return_value=None)
        provider = FeatureProvider(redis=redis_mock)
        snapshot = await provider.get_features(session, "XAUUSD", Timeframe.M1, count=15)

        assert "atr_14" in snapshot.indicators
        assert snapshot.pivots is not None
        # Cache miss stored the computed value under the feaature key.
        calls = [c for c in redis_mock.setex.call_args_list if c.args[0] == "feat:XAUUSD:atr_14"]
        assert len(calls) == 1

    async def test_get_features_empty_bars_uses_now_and_no_pivots(
        self, redis_mock: AsyncMock
    ) -> None:
        # get_features (provider.py:146-154): with zero bars, as_of_ts
        # falls back to now and pivots stay None — no indicator is
        # computable and nothing poisons the cache.
        before = datetime.now(UTC)
        session = _mock_session([])
        provider = FeatureProvider(redis=redis_mock)
        snapshot = await provider.get_features(session, "XAUUSD", Timeframe.M1, count=15)

        assert snapshot.pivots is None
        assert snapshot.indicators == {}
        assert snapshot.as_of_ts >= before
        redis_mock.setex.assert_not_awaited()

    async def test_cached_indicator_accepts_str_raw(self, redis_mock: AsyncMock) -> None:
        # _get_cached_indicator (provider.py:94-96) coerces both bytes and
        # str raw values into Decimal — a mock returning str must parse.
        bars = [_make_bar_dict(i, str(2500 + i)) for i in range(15)]
        session = _mock_session(bars)
        redis_mock.get = AsyncMock(return_value="2.5")
        provider = FeatureProvider(redis=redis_mock)
        snapshot = await provider.get_features(session, "XAUUSD", Timeframe.M1, count=15)

        assert snapshot.indicators["atr_14"] == Decimal("2.5")
        redis_mock.setex.assert_not_awaited()  # cache hit — nothing written
