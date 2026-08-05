# Copyright (c) 2026 Lumine. All rights reserved.
"""Reconciliation logic (docs/08-trading/reconciliation.md, ADR-0021).

Two gates:

1. **Fill comparison** — the bridge-reported fill is compared against
   the expected price/volume with explicit tolerances. A mismatch is a
   red flag recorded for TCA and can arm the kill switch.
2. **Daily broker reconciliation** — an internally ``CLOSED`` position
   may only be promoted to ``SETTLED`` after the broker confirms; a
   drift between internal state and broker state arms the kill switch
   (silent position drift is the failure mode, ADR-0021).

All comparisons are pure; arming the kill switch is the only side
effect and it goes through an injected Redis client.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import redis.asyncio as aioredis


@dataclass(frozen=True)
class FillComparison:
    """Deviation metrics for one fill vs its expectation."""

    expected_price: Decimal
    fill_price: Decimal
    expected_volume: Decimal
    fill_volume: Decimal
    price_deviation_pct: Decimal
    volume_deviation_pct: Decimal
    price_mismatch: bool
    volume_mismatch: bool

    @property
    def mismatch(self) -> bool:
        """True when either dimension deviated beyond tolerance."""
        return self.price_mismatch or self.volume_mismatch


def _deviation(actual: Decimal, expected: Decimal) -> Decimal:
    if expected == 0:
        return Decimal(0)
    return abs(actual - expected) / expected


def compare_fill(  # noqa: PLR0913 — comparison inputs are a fixed contract
    *,
    expected_price: Decimal,
    fill_price: Decimal,
    expected_volume: Decimal,
    fill_volume: Decimal,
    price_tolerance_pct: Decimal = Decimal("0.005"),   # 0.5%
    volume_tolerance_pct: Decimal = Decimal("0.01"),   # 1%
) -> FillComparison:
    """Compare a fill against its expectation; deviations beyond tolerance mismatch."""
    return FillComparison(
        expected_price=expected_price,
        fill_price=fill_price,
        expected_volume=expected_volume,
        fill_volume=fill_volume,
        price_deviation_pct=_deviation(fill_price, expected_price),
        volume_deviation_pct=_deviation(fill_volume, expected_volume),
        price_mismatch=_deviation(fill_price, expected_price) > price_tolerance_pct,
        volume_mismatch=_deviation(fill_volume, expected_volume) > volume_tolerance_pct,
    )


@dataclass(frozen=True)
class SettlementGate:
    """Outcome of the daily broker-reconciliation gate (ADR-0021)."""

    internal_status: str
    broker_status: str
    settled: bool        # True when the gate passed
    drift: bool          # True when internal/broker disagree → arm kill switch


def reconciliation_gate(*, internal_status: str, broker_status: str) -> SettlementGate:
    """Promote CLOSED→SETTLED only on broker confirmation; drift arms kill switch.

    An internally CLOSED position whose broker still reports OPEN (or any
    internal/broker disagreement on a CLOSED position) is drift.
    """
    if internal_status == "CLOSED":
        settled = broker_status == "SETTLED"
        drift = not settled
    else:
        settled = True
        drift = False
    return SettlementGate(
        internal_status=internal_status,
        broker_status=broker_status,
        settled=settled,
        drift=drift,
    )


async def arm_kill_switch(redis: aioredis.Redis, key: str) -> None:
    """Arm the kill switch by setting ``key`` (no TTL — persists until cleared)."""
    await redis.set(key, "1")


__all__ = (
    "FillComparison",
    "SettlementGate",
    "arm_kill_switch",
    "compare_fill",
    "reconciliation_gate",
)
