# Copyright (c) 2026 Lumine. All rights reserved.
"""Unit tests for the tick collector and OHLCV aggregator.

These tests exercise aggregation logic without PostgreSQL or Redis.
Persistence and stream integration are covered by Level 2 tests.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from lumine.data.collector import Tick, build_bar, ingest_tick, resample_bars_until
from lumine.shared.errors import ValidationError


class TestTickValidation:
    """Tick parsing and validation rules."""

    def test_tick_requires_positive_prices(self) -> None:
        with pytest.raises(ValidationError):
            Tick(
                ts=datetime(2026, 8, 3, 12, 0, 0, tzinfo=UTC),
                symbol="XAUUSD",
                bid=Decimal("-1.0"),
                ask=Decimal("2500.00"),
                last=Decimal("2500.00"),
                volume=Decimal("1.0"),
                source="mt5",
            )

    def test_tick_rejects_negative_volume(self) -> None:
        with pytest.raises(ValidationError):
            Tick(
                ts=datetime(2026, 8, 3, 12, 0, 0, tzinfo=UTC),
                symbol="XAUUSD",
                bid=Decimal("2500.00"),
                ask=Decimal("2500.10"),
                last=Decimal("2500.05"),
                volume=Decimal("-1.0"),
                source="mt5",
            )

    def test_tick_rejects_crossed_spread(self) -> None:
        # __post_init__ (collector.py:53-55): ask < bid is a corrupt
        # market feed — reject before it reaches the aggregator.
        with pytest.raises(ValidationError, match="ask must be greater"):
            Tick(
                ts=datetime(2026, 8, 3, 12, 0, 0, tzinfo=UTC),
                symbol="XAUUSD",
                bid=Decimal("2500.10"),
                ask=Decimal("2500.00"),
                last=Decimal("2500.05"),
                volume=Decimal("1.0"),
                source="mt5",
            )

    def test_tick_accepts_equal_bid_ask(self) -> None:
        # Zero spread (bid == ask) is legal — the invariant is ask >= bid.
        tick = Tick(
            ts=datetime(2026, 8, 3, 12, 0, 0, tzinfo=UTC),
            symbol="XAUUSD",
            bid=Decimal("2500.00"),
            ask=Decimal("2500.00"),
            last=Decimal("2500.00"),
            volume=Decimal("1.0"),
            source="mt5",
        )
        assert tick.ask == tick.bid

    def test_tick_normalizes_naive_ts_to_utc(self) -> None:
        # __post_init__ (collector.py:56-57): a tz-naive timestamp is
        # assumed UTC and stamped — the pipeline never holds naive datetimes.
        # Ruff DTZ001 flags naive construction, so build then strip tzinfo.
        naive = datetime(2026, 8, 3, 12, 0, 0, tzinfo=UTC).replace(tzinfo=None)
        tick = Tick(
            ts=naive,
            symbol="XAUUSD",
            bid=Decimal("2500.00"),
            ask=Decimal("2500.10"),
            last=Decimal("2500.05"),
            volume=Decimal("1.5"),
            source="mt5",
        )
        assert tick.ts.tzinfo is UTC
        assert tick.ts == datetime(2026, 8, 3, 12, 0, 0, tzinfo=UTC)

    def test_tick_accepts_valid_input(self) -> None:
        tick = Tick(
            ts=datetime(2026, 8, 3, 12, 0, 0, tzinfo=UTC),
            symbol="XAUUSD",
            bid=Decimal("2500.00"),
            ask=Decimal("2500.10"),
            last=Decimal("2500.05"),
            volume=Decimal("1.5"),
            source="mt5",
        )
        assert tick.symbol == "XAUUSD"
        assert tick.last == Decimal("2500.05")


class TestIngestTick:
    """State updates performed when a tick is ingested."""

    def test_empty_state_after_first_tick(self) -> None:
        state = {}
        tick = Tick(
            ts=datetime(2026, 8, 3, 12, 0, 5, tzinfo=UTC),
            symbol="XAUUSD",
            bid=Decimal("2500.00"),
            ask=Decimal("2500.10"),
            last=Decimal("2500.05"),
            volume=Decimal("1.0"),
            source="mt5",
        )
        bar = ingest_tick(state, tick, timeframe_s=60)
        assert bar is None
        assert state["open"] == Decimal("2500.05")
        assert state["volume"] == Decimal("1.0")

    def test_ingest_tick_requires_keyword_timeframe(self) -> None:
        state = {}
        tick = Tick(
            ts=datetime(2026, 8, 3, 12, 0, 5, tzinfo=UTC),
            symbol="XAUUSD",
            bid=Decimal("2500.00"),
            ask=Decimal("2500.10"),
            last=Decimal("2500.05"),
            volume=Decimal("1.0"),
            source="mt5",
        )
        with pytest.raises(TypeError):
            ingest_tick(state, tick, 60)

    def test_bar_closed_on_timeframe_boundary(self) -> None:
        state = {}
        timeframe_s = 60
        start = datetime(2026, 8, 3, 12, 0, 0, tzinfo=UTC)
        first = Tick(
            ts=start,
            symbol="XAUUSD",
            bid=Decimal("2500.00"),
            ask=Decimal("2500.10"),
            last=Decimal("2500.00"),
            volume=Decimal("1.0"),
            source="mt5",
        )
        ingest_tick(state, first, timeframe_s=timeframe_s)
        second = Tick(
            ts=start.replace(second=59),
            symbol="XAUUSD",
            bid=Decimal("2501.00"),
            ask=Decimal("2501.10"),
            last=Decimal("2501.00"),
            volume=Decimal("2.0"),
            source="mt5",
        )
        bar = ingest_tick(state, second, timeframe_s=timeframe_s)
        assert bar is None
        assert state["high"] == Decimal("2501.00")
        assert state["low"] == Decimal("2500.00")
        assert state["volume"] == Decimal("3.0")

        third = Tick(
            ts=start.replace(minute=1),
            symbol="XAUUSD",
            bid=Decimal("2502.00"),
            ask=Decimal("2502.10"),
            last=Decimal("2502.00"),
            volume=Decimal("1.0"),
            source="mt5",
        )
        bar = ingest_tick(state, third, timeframe_s=timeframe_s)
        assert bar is not None
        assert bar.ts == start
        assert bar.open_ == Decimal("2500.00")
        assert bar.high == Decimal("2501.00")
        assert bar.low == Decimal("2500.00")
        assert bar.close == Decimal("2501.00")
        assert bar.volume == Decimal("3.0")
        assert bar.symbol == "XAUUSD"

    def test_new_state_starts_with_boundary_tick(self) -> None:
        state = {}
        timeframe_s = 60
        start = datetime(2026, 8, 3, 12, 0, 0, tzinfo=UTC)
        first = Tick(
            ts=start,
            symbol="XAUUSD",
            bid=Decimal("2500.00"),
            ask=Decimal("2500.10"),
            last=Decimal("2500.00"),
            volume=Decimal("1.0"),
            source="mt5",
        )
        ingest_tick(state, first, timeframe_s=timeframe_s)
        boundary = Tick(
            ts=start.replace(minute=1),
            symbol="XAUUSD",
            bid=Decimal("2502.00"),
            ask=Decimal("2502.10"),
            last=Decimal("2502.00"),
            volume=Decimal("1.0"),
            source="mt5",
        )
        ingest_tick(state, boundary, timeframe_s=timeframe_s)
        assert state["open"] == Decimal("2502.00")
        assert state["volume"] == Decimal("1.0")


class TestBuildBar:
    """Finalizing an aggregation state into a Bar."""

    def test_build_bar_copies_state(self) -> None:
        state = {
            "ts": datetime(2026, 8, 3, 12, 0, 0, tzinfo=UTC),
            "open": Decimal("2500.00"),
            "high": Decimal("2505.00"),
            "low": Decimal("2498.00"),
            "close": Decimal("2502.00"),
            "volume": Decimal("10.0"),
            "source": "mt5",
        }
        bar = build_bar("XAUUSD", state)
        assert bar.open_ == Decimal("2500.00")
        assert bar.close == Decimal("2502.00")
        assert bar.symbol == "XAUUSD"


class TestResampleBars:
    """Building higher-timeframe bars from lower-timeframe bars."""

    def test_resample_to_5m_from_1m(self) -> None:
        start = datetime(2026, 8, 3, 12, 0, 0, tzinfo=UTC)
        bars = [
            build_bar(
                "XAUUSD",
                {
                    "ts": start.replace(minute=i),
                    "open": Decimal(str(2500 + i)),
                    "high": Decimal(str(2501 + i)),
                    "low": Decimal(str(2499 + i)),
                    "close": Decimal(str(2500 + i + 0.5)),
                    "volume": Decimal("1.0"),
                    "source": "mt5",
                },
            )
            for i in range(5)
        ]
        now = start.replace(minute=5, second=1)
        resampled = resample_bars_until(bars, 300, source="aggregator", now=now)
        assert len(resampled) == 1
        assert resampled[0].open_ == Decimal("2500.0")
        assert resampled[0].high == Decimal("2505.0")
        assert resampled[0].low == Decimal("2499.0")
        assert resampled[0].close == Decimal("2504.5")
        assert resampled[0].volume == Decimal("5.0")
        assert resampled[0].ts == start

    def test_resample_with_incomplete_bucket_dropped(self) -> None:
        start = datetime(2026, 8, 3, 12, 0, 0, tzinfo=UTC)
        bars = [
            build_bar(
                "XAUUSD",
                {
                    "ts": start.replace(minute=i),
                    "open": Decimal(str(2500 + i)),
                    "high": Decimal(str(2501 + i)),
                    "low": Decimal(str(2499 + i)),
                    "close": Decimal(str(2500 + i + 0.5)),
                    "volume": Decimal("1.0"),
                    "source": "mt5",
                },
            )
            for i in range(3)
        ]
        now = start.replace(minute=5, second=1)
        resampled = resample_bars_until(bars, 300, source="aggregator", now=now)
        # The 00:00-00:04 bucket is complete relative to the input, so it is emitted.
        assert len(resampled) == 1

    def test_resample_empty_input(self) -> None:
        assert resample_bars_until([], 300, source="aggregator", now=datetime.now(UTC)) == []

    def test_resample_handles_gaps(self) -> None:
        start = datetime(2026, 8, 3, 12, 0, 0, tzinfo=UTC)
        bars = [
            build_bar(
                "XAUUSD",
                {
                    "ts": start,
                    "open": Decimal(2500),
                    "high": Decimal(2501),
                    "low": Decimal(2499),
                    "close": Decimal("2500.5"),
                    "volume": Decimal("1.0"),
                    "source": "mt5",
                },
            ),
            build_bar(
                "XAUUSD",
                {
                    "ts": start.replace(minute=6),
                    "open": Decimal(2510),
                    "high": Decimal(2511),
                    "low": Decimal(2509),
                    "close": Decimal("2510.5"),
                    "volume": Decimal("1.0"),
                    "source": "mt5",
                },
            ),
        ]
        now = start.replace(minute=10, second=1)
        resampled = resample_bars_until(bars, 300, source="aggregator", now=now)
        assert len(resampled) == 2
        assert resampled[0].ts == start
        assert resampled[1].ts == start.replace(minute=5)

    def test_resample_drops_bucket_at_reference_boundary(self) -> None:
        # resample_bars_until (collector.py:238-239) drops buckets that
        # are >= the floored reference time — a bar whose bucket equals
        # the current 5m bucket must not be published as a full bar.
        start = datetime(2026, 8, 3, 12, 0, 0, tzinfo=UTC)
        bars = [
            build_bar(
                "XAUUSD",
                {
                    "ts": start,
                    "open": Decimal(2500),
                    "high": Decimal(2501),
                    "low": Decimal(2499),
                    "close": Decimal("2500.5"),
                    "volume": Decimal("1.0"),
                    "source": "mt5",
                },
            )
        ]
        # reference == the bucket start itself → bucket_ts >= last_complete.
        resampled = resample_bars_until(
            bars, 300, source="aggregator", now=start.replace(second=0)
        )
        assert resampled == []
