# Copyright (c) 2026 Lumine. All rights reserved.
"""Unit tests for technical indicators.

Tests cover ATR, EMA, RSI, and pivot-point calculations against hand-checkable
expected values. All functions are pure: no I/O, no state.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from lumine.features.indicators import (
    atr,
    ema,
    pivot_points,
    rsi,
)
from lumine.shared.errors import ValidationError


def _bar(
    ts_offset: int,
    open_: str,
    high: str,
    low: str,
    close: str,
    volume: str = "1.0",
) -> dict[str, object]:
    return {
        "ts": datetime(2026, 8, 3, 12, 0, 0, tzinfo=UTC).replace(minute=ts_offset),
        "open_": Decimal(open_),
        "high": Decimal(high),
        "low": Decimal(low),
        "close": Decimal(close),
        "volume": Decimal(volume),
        "source": "test",
    }


class TestATR:
    """Average True Range over a lookback window."""

    def test_atr_requires_bars(self) -> None:
        with pytest.raises(ValidationError):
            atr([], period=14)

    def test_atr_period_must_be_positive(self) -> None:
        bars = [_bar(0, "100.0", "110.0", "90.0", "105.0")]
        with pytest.raises(ValidationError):
            atr(bars, period=0)

    def test_atr_insufficient_bars(self) -> None:
        bars = [_bar(i, "100.0", "110.0", "90.0", "105.0") for i in range(3)]
        with pytest.raises(ValidationError):
            atr(bars, period=14)

    def test_atr_matches_hand_calculation(self) -> None:
        """RMA-smoothed ATR matches a hand-computed 2-period example."""
        bars = [
            _bar(0, "100.0", "110.0", "90.0", "100.0"),
            _bar(1, "100.0", "115.0", "95.0", "110.0"),
            _bar(2, "110.0", "120.0", "105.0", "115.0"),
        ]
        result = atr(bars, period=2)
        # TR0 = max(110-90, |110-100|, |90-100|) = 20
        # TR1 = max(115-95, |115-100|, |95-100|) = 20
        # TR2 = max(120-105, |120-110|, |105-110|) = 15
        # RMA: atr0 = 20, atr1 = (20*1 + 20)/(2) = 20, atr2 = (20*1 + 15)/(2) = 17.5
        assert result == Decimal("17.5")

    def test_atr_uses_high_low_close(self) -> None:
        bars = [
            _bar(0, "2500.0", "2505.0", "2495.0", "2500.0"),
            _bar(1, "2500.0", "2510.0", "2498.0", "2508.0"),
            _bar(2, "2508.0", "2512.0", "2502.0", "2505.0"),
        ]
        result = atr(bars, period=2)
        # TR0 = max(10, |2500-2500|, |2495-2500|) = 10
        # TR1 = max(12, |2510-2500|, |2498-2500|) = 12
        # TR2 = max(10, |2512-2508|, |2502-2508|) = 10
        # RMA with period=2: seed=10, next=(10*1+12)/2=11, final=(11*1+10)/2=10.5
        assert result == Decimal("10.5")

    def test_atr_captures_gap_up(self) -> None:
        # _true_range (indicators.py:30-33): when the current bar gaps
        # above the previous close, abs(high - prev_close) dominates the
        # range — without that branch TR would be max(4, 10) = 10, not 14.
        bars = [
            _bar(0, "100.0", "110.0", "90.0", "100.0"),
            _bar(1, "112.0", "114.0", "110.0", "112.0"),
        ]
        result = atr(bars, period=1)
        # TR0 = max(20, 10, 10) = 20; TR1 = max(4, 14, 10) = 14;
        # period=1 → alpha=1 → ATR == last TR.
        assert result == Decimal(14)


class TestEMA:
    """Exponential moving average of closes."""

    def test_ema_requires_bars(self) -> None:
        with pytest.raises(ValidationError):
            ema([], period=10)

    def test_ema_period_must_be_positive(self) -> None:
        bars = [_bar(0, "10.0", "11.0", "9.0", "10.0")]
        with pytest.raises(ValidationError):
            ema(bars, period=0)

    def test_ema_insufficient_bars(self) -> None:
        bars = [_bar(i, "10.0", "11.0", "9.0", "10.0") for i in range(5)]
        with pytest.raises(ValidationError):
            ema(bars, period=10)

    def test_ema_matches_hand_calculation(self) -> None:
        """3-period EMA with multiplier 1/2 matches hand-computed values."""
        bars = [
            _bar(0, "10.0", "11.0", "9.0", "10.0"),
            _bar(1, "10.0", "12.0", "9.0", "12.0"),
            _bar(2, "12.0", "13.0", "11.0", "11.0"),
            _bar(3, "11.0", "12.0", "10.0", "13.0"),
        ]
        result = ema(bars, period=3)
        # seed = (10+12+11)/3 = 11; mult = 1/2
        # ema1 = 13*1/2 + 11*1/2 = 12
        assert result == Decimal(12)


class TestRSI:
    """Relative Strength Index over a lookback window."""

    def test_rsi_requires_bars(self) -> None:
        with pytest.raises(ValidationError):
            rsi([], period=14)

    def test_rsi_period_must_be_positive(self) -> None:
        bars = [_bar(0, "10.0", "11.0", "9.0", "10.0")]
        with pytest.raises(ValidationError):
            rsi(bars, period=0)

    def test_rsi_insufficient_bars(self) -> None:
        bars = [_bar(i, "10.0", "11.0", "9.0", "10.0") for i in range(5)]
        with pytest.raises(ValidationError):
            rsi(bars, period=14)

    def test_rsi_maximum(self) -> None:
        bars = [_bar(i, str(10 + i), str(11 + i), str(9 + i), str(10 + i)) for i in range(15)]
        result = rsi(bars, period=14)
        assert result == Decimal(100)

    def test_rsi_minimum(self) -> None:
        bars = [_bar(i, str(20 - i), str(21 - i), str(19 - i), str(20 - i)) for i in range(15)]
        result = rsi(bars, period=14)
        assert result == Decimal(0)

    def test_rsi_mixed_moves(self) -> None:
        bars = [_bar(i, "10.0", "11.0", "9.0", "11.0" if i % 2 else "10.0") for i in range(15)]
        result = rsi(bars, period=14)
        # first 14 changes: 7 gains of 1 and 7 losses of 1 -> avg_gain=avg_loss=0.5
        # 15th change is 0; RMA keeps both near 0.5 -> RS≈1 -> RSI≈50
        assert result == Decimal(50)

    def test_rsi_flat_closes_return_100(self) -> None:
        # indicators.py:86-87: with every change == 0, both averages are
        # 0 and avg_loss == 0 short-circuits to RSI 100 — the same branch
        # as a pure gain streak. Pinned so the degenerate flat-market
        # case is deliberate, not emergent behavior.
        bars = [_bar(i, "10.0", "11.0", "9.0", "10.0") for i in range(15)]
        assert rsi(bars, period=14) == Decimal(100)

    def test_rsi_smoothes_changes_after_period(self) -> None:
        # indicators.py:82-84: the RMA continuation loop only runs when
        # there are MORE changes than the period — every other RSI test
        # has exactly period changes (zero loop iterations). 16 bars with
        # period 14 → 15 changes → exactly one smoothing step.
        # 7 gains + 7 losses of 1 then one more gain: avg_gain = 7.5/14,
        # avg_loss = 6.5/14, rs = 15/13 → RSI = 375/7.
        bars = [_bar(i, "10.0", "11.0", "9.0", str(10 + (i % 2))) for i in range(16)]
        assert rsi(bars, period=14) == Decimal(375) / Decimal(7)


class TestPivotPoints:
    """Classic floor-trader pivot points from the most recent bar."""

    def test_pivot_requires_bars(self) -> None:
        with pytest.raises(ValidationError):
            pivot_points([])

    def test_pivot_points_match_classic_formula(self) -> None:
        bars = [
            _bar(0, "2500.0", "2510.0", "2490.0", "2505.0"),
            _bar(1, "2505.0", "2520.0", "2500.0", "2515.0"),
        ]
        result = pivot_points(bars)
        # Pivot = (H + L + C) / 3 = (2520 + 2500 + 2515) / 3 = 7535 / 3
        # R1 = 2*P - L; S1 = 2*P - H
        assert result.pivot == Decimal(7535) / Decimal(3)
        assert result.r1 == Decimal(2) * result.pivot - result.low
        assert result.s1 == Decimal(2) * result.pivot - result.high
        assert result.r2 == result.pivot + (result.high - result.low)
        assert result.s2 == result.pivot - (result.high - result.low)

    def test_pivot_points_uses_last_bar(self) -> None:
        bars = [
            _bar(0, "3000.0", "3100.0", "2900.0", "3050.0"),
            _bar(1, "2500.0", "2520.0", "2500.0", "2515.0"),
        ]
        result = pivot_points(bars)
        assert result.high == Decimal(2520)
        assert result.low == Decimal(2500)
        assert result.close == Decimal(2515)
