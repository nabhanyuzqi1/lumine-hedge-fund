# Copyright (c) 2026 Lumine. All rights reserved.
"""Pure technical indicator functions.

All inputs are sequences of bar-like dicts; all calculations use Decimal to
avoid floating-point drift. Invalid inputs raise ValidationError.
"""

from __future__ import annotations

from decimal import Decimal
from itertools import pairwise
from typing import Any

from lumine.features.types import PivotPoints
from lumine.shared.errors import ValidationError


def _validate_bars(bars: list[dict[str, Any]], period: int | None = None) -> None:
    if not bars:
        msg = "bars cannot be empty"
        raise ValidationError(msg)
    if period is not None and period <= 0:
        msg = "period must be positive"
        raise ValidationError(msg)
    if period is not None and len(bars) < period + 1:
        msg = f"need at least {period + 1} bars for indicator"
        raise ValidationError(msg)


def _true_range(bar: dict[str, Any], previous_close: Decimal) -> Decimal:
    high = Decimal(bar["high"])
    low = Decimal(bar["low"])
    return max(high - low, abs(high - previous_close), abs(low - previous_close))


def atr(bars: list[dict[str, Any]], *, period: int) -> Decimal:
    """Wilder/RMA-smoothed Average True Range.

    Uses the standard true-range formula and a rolling moving average with
    alpha = 1 / period.
    """
    _validate_bars(bars, period)
    tr_values: list[Decimal] = [_true_range(bars[0], bars[0]["close"])]
    for previous, current in pairwise(bars):
        tr_values.append(_true_range(current, previous["close"]))

    alpha = Decimal(1) / Decimal(period)
    value = tr_values[0]
    for tr in tr_values[1:]:
        value = tr * alpha + value * (Decimal(1) - alpha)
    return value


def ema(bars: list[dict[str, Any]], *, period: int) -> Decimal:
    """Exponential moving average of closing prices.

    Seed is the SMA of the first `period` closes; subsequent values use
    multiplier = 2 / (period + 1).
    """
    _validate_bars(bars, period)
    multiplier = Decimal(2) / Decimal(period + 1)
    closes = [b["close"] for b in bars]
    value = sum(closes[:period], Decimal(0)) / Decimal(period)
    for close in closes[period:]:
        value = close * multiplier + value * (Decimal(1) - multiplier)
    return value


def rsi(bars: list[dict[str, Any]], *, period: int) -> Decimal:
    """Relative Strength Index using RMA-smoothed gains/losses."""
    _validate_bars(bars, period)
    closes = [b["close"] for b in bars]
    changes = [closes[i] - closes[i - 1] for i in range(1, len(closes))]

    gains = [max(c, Decimal(0)) for c in changes]
    losses = [max(-c, Decimal(0)) for c in changes]

    alpha = Decimal(1) / Decimal(period)
    avg_gain = sum(gains[:period], Decimal(0)) / Decimal(period)
    avg_loss = sum(losses[:period], Decimal(0)) / Decimal(period)

    for gain, loss in zip(gains[period:], losses[period:], strict=True):
        avg_gain = gain * alpha + avg_gain * (Decimal(1) - alpha)
        avg_loss = loss * alpha + avg_loss * (Decimal(1) - alpha)

    if avg_loss == 0:
        return Decimal(100)
    rs = avg_gain / avg_loss
    return Decimal(100) - (Decimal(100) / (Decimal(1) + rs))


def pivot_points(bars: list[dict[str, Any]]) -> PivotPoints:
    """Classic floor-trader pivot points from the most recent bar."""
    _validate_bars(bars)
    last = bars[-1]
    high = last["high"]
    low = last["low"]
    close = last["close"]
    pivot = (high + low + close) / Decimal(3)
    r1 = Decimal(2) * pivot - low
    s1 = Decimal(2) * pivot - high
    r2 = pivot + (high - low)
    s2 = pivot - (high - low)
    return PivotPoints(
        pivot=pivot,
        r1=r1,
        r2=r2,
        s1=s1,
        s2=s2,
        high=high,
        low=low,
        close=close,
    )
