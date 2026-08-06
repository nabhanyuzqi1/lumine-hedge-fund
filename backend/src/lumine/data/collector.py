# Copyright (c) 2026 Lumine. All rights reserved.
"""Tick collector and OHLCV aggregator.

This module owns the hot path from market tick to persisted bar:

1. ``Tick`` validation and normalization.
2. In-memory aggregation state per (symbol, timeframe).
3. ``ingest_tick`` updates the running bar and emits a finalized ``Bar``
   when the timeframe boundary is crossed.
4. ``resample_bars`` rolls lower-timeframe bars into higher-timeframe bars.

Persistence, Redis streams, and partition lifecycle are orchestrated by
callers (the data-ingest worker) so this module stays deterministic and
easily unit-tested.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal  # noqa: TC003 — used at runtime in Tick.__post_init__
from typing import Any

from lumine.shared.errors import ValidationError

# ── Data classes ──────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Tick:
    """A normalized market tick.

    Fields map to the ``ticks`` PostgreSQL table. Prices and volume are
    stored as ``Decimal`` to avoid floating-point drift in aggregation.
    """

    ts: datetime
    symbol: str
    bid: Decimal
    ask: Decimal
    last: Decimal
    volume: Decimal
    source: str

    def __post_init__(self) -> None:
        """Validate tick invariants."""
        if self.bid <= 0 or self.ask <= 0 or self.last <= 0:
            msg = "tick prices must be positive"
            raise ValidationError(msg)
        if self.volume < 0:
            msg = "tick volume must be non-negative"
            raise ValidationError(msg)
        if self.ask < self.bid:
            msg = "ask must be greater than or equal to bid"
            raise ValidationError(msg)
        if self.ts.tzinfo is None:
            object.__setattr__(self, "ts", self.ts.replace(tzinfo=UTC))


@dataclass(frozen=True)
class Bar:
    """A normalized OHLCV bar.

    Field names avoid SQLAlchemy reserved words (``open`` -> ``open_``).
    All numeric fields are ``Decimal`` for deterministic aggregation.
    """

    ts: datetime
    symbol: str
    open_: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    source: str


# ── Timeframe helpers ─────────────────────────────────────────────────────────


def _floor_ts(ts: datetime, timeframe_s: int) -> datetime:
    """Floor ``ts`` to the start of its timeframe bucket."""
    epoch = int(ts.timestamp())
    bucket_start = (epoch // timeframe_s) * timeframe_s
    return datetime.fromtimestamp(bucket_start, tz=ts.tzinfo or UTC)


# ── Aggregation state machine ─────────────────────────────────────────────────


def ingest_tick(
    state: dict[str, Any],
    tick: Tick,
    *,
    timeframe_s: int,
) -> Bar | None:
    """Update the running aggregation ``state`` for ``tick``.

    The ``state`` dict is mutated in place and must be supplied by the
    caller (e.g., one state per symbol/timeframe). When ``tick`` falls
    into a new timeframe bucket, the previous bar is finalized and a new
    state is seeded with the boundary tick.

    Args:
        state: Mutable aggregation state for the current bucket.
        tick: The incoming tick.
        timeframe_s: Bucket size in seconds (e.g., 60 for 1m).

    Returns:
        A finalized ``Bar`` when the bucket boundary is crossed, else ``None``.

    """
    bucket = _floor_ts(tick.ts, timeframe_s)

    if not state:
        _seed_state(state, tick, bucket)
        return None

    current_bucket = state["ts"]
    if bucket == current_bucket:
        _update_state(state, tick)
        return None

    # Boundary crossed: emit the completed bar and start a new bucket.
    bar = build_bar(tick.symbol, state)
    state.clear()
    _seed_state(state, tick, bucket)
    return bar


def _seed_state(
    state: dict[str, Any],
    tick: Tick,
    bucket: datetime,
) -> None:
    """Initialize a fresh aggregation state with ``tick``."""
    state.update(
        {
            "ts": bucket,
            "open": tick.last,
            "high": tick.last,
            "low": tick.last,
            "close": tick.last,
            "volume": tick.volume,
            "source": tick.source,
        }
    )


def _update_state(state: dict[str, Any], tick: Tick) -> None:
    """Incorporate ``tick`` into the current aggregation state."""
    state["high"] = max(state["high"], tick.last)
    state["low"] = min(state["low"], tick.last)
    state["close"] = tick.last
    state["volume"] += tick.volume


def build_bar(symbol: str, state: dict[str, Any]) -> Bar:
    """Materialize ``state`` into an immutable ``Bar``."""
    return Bar(
        ts=state["ts"],
        symbol=symbol,
        open_=state["open"],
        high=state["high"],
        low=state["low"],
        close=state["close"],
        volume=state["volume"],
        source=state["source"],
    )


# ── Higher-timeframe resampling ───────────────────────────────────────────────


def resample_bars(
    bars: list[Bar],
    *,
    target_s: int,
    source: str,
) -> list[Bar]:
    """Roll lower-timeframe ``bars`` into higher-timeframe bars.

    Gaps in the input produce empty buckets that are skipped (no synthetic
    bars). By default, incomplete trailing buckets are dropped to avoid
    publishing partially-formed bars. Pass ``now`` explicitly to override
    the reference time (used in tests).

    Args:
        bars: Ordered list of lower-timeframe bars, all for the same symbol.
        target_s: Target bucket size in seconds (e.g., 300 for 5m).
        source: Value for the ``source`` field (typically ``"aggregator"``).

    Returns:
        Ordered list of finalized higher-timeframe bars.

    """
    return resample_bars_until(bars, target_s=target_s, source=source)


def resample_bars_until(
    bars: list[Bar],
    target_s: int,
    *,
    source: str,
    now: datetime | None = None,
) -> list[Bar]:
    """Expose ``now`` so tests can control the resampling boundary."""
    if not bars:
        return []

    symbol = bars[0].symbol
    buckets: dict[datetime, dict[str, Any]] = {}

    for bar in bars:
        bucket = _floor_ts(bar.ts, target_s)
        if bucket not in buckets:
            buckets[bucket] = {
                "ts": bucket,
                "open": bar.open_,
                "high": bar.high,
                "low": bar.low,
                "close": bar.close,
                "volume": bar.volume,
                "source": source,
            }
        else:
            agg = buckets[bucket]
            agg["high"] = max(agg["high"], bar.high)
            agg["low"] = min(agg["low"], bar.low)
            agg["close"] = bar.close
            agg["volume"] += bar.volume

    reference = now or datetime.now(UTC)
    last_complete = _floor_ts(reference, target_s)

    result = []
    for bucket_ts in sorted(buckets):
        if bucket_ts >= last_complete:
            continue
        result.append(build_bar(symbol, buckets[bucket_ts]))
    return result
