# Copyright (c) 2026 Lumine. All rights reserved.
"""Feature provider types and value objects.

Defines the public contract between the feature store and consumers such as
analyst agents and the risk engine. Types are deterministic and Decimal-based
to match market data precision rules.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import datetime
    from decimal import Decimal

    from lumine.shared.types import Timeframe


@dataclass(frozen=True)
class PivotPoints:
    """Classic floor-trader pivot levels derived from the prior bar."""

    pivot: Decimal
    r1: Decimal
    r2: Decimal
    s1: Decimal
    s2: Decimal
    high: Decimal
    low: Decimal
    close: Decimal


@dataclass(frozen=True)
class FeatureSnapshot:
    """Point-in-time feature vector for a symbol/timeframe."""

    symbol: str
    timeframe: Timeframe
    as_of_ts: datetime
    indicators: dict[str, Decimal]
    pivots: PivotPoints | None
