# Copyright (c) 2026 Lumine. All rights reserved.
"""TCA rollup and execution-quality alert contracts (ADR-0040)."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable
    from datetime import date, datetime


@dataclass(frozen=True)
class TcaObservation:
    """Minimal immutable input for deterministic rollup and alert evaluation."""

    tca_id: str
    fill_id: str
    strategy_id: str
    symbol: str
    broker_id: str
    regime_id: str
    benchmark_source: str
    decision_ts: datetime
    slippage_bps: Decimal
    slippage_cost_ccy: Decimal


@dataclass(frozen=True)
class TcaRollup:
    """Aggregate execution quality for one dimension and trading date."""

    dimension: str
    key: str
    trading_date: date
    avg_bps: Decimal
    p50_bps: Decimal
    p95_bps: Decimal
    total_cost_ccy: Decimal
    fill_count: int


@dataclass(frozen=True)
class SlippageBreach:
    """Single-fill policy breach."""

    alert_type: str
    fill_id: str
    tca_id: str
    strategy_id: str
    symbol: str
    broker_id: str
    regime_id: str
    slippage_bps: Decimal
    threshold_bps: Decimal


@dataclass(frozen=True)
class SlippageCluster:
    """Repeated slippage breaches for one strategy in a rolling sample."""

    alert_type: str
    strategy_id: str
    breach_count: int
    cluster_limit: int
    fill_ids: tuple[str, ...]


def threshold_for(
    *, symbol: str, regime_id: str, policy: dict[str, Decimal] | None = None
) -> Decimal:
    """Return configured symbol/regime threshold, with ADR-0040 defaults."""
    if policy:
        exact = policy.get(f"{symbol}:{regime_id}")
        if exact is not None:
            return exact
        regime = policy.get(regime_id)
        if regime is not None:
            return regime
    return Decimal(10) if regime_id.lower() == "high_vol" else Decimal(5)


def _percentile(values: list[Decimal], percentile: float) -> Decimal:
    """Compute a linear-interpolated percentile without external dependencies."""
    if not values:
        msg = "percentile requires at least one value"
        raise ValueError(msg)
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * percentile
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = Decimal(str(position - lower))
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def build_rollups(observations: Iterable[TcaObservation]) -> list[TcaRollup]:
    """Build daily strategy/broker/symbol/regime/session rollups in memory."""
    groups: dict[tuple[str, str, date], list[TcaObservation]] = {}
    for observation in observations:
        trading_date = observation.decision_ts.date()
        dimensions = {
            "strategy": observation.strategy_id,
            "broker": observation.broker_id,
            "symbol": observation.symbol,
            "regime": observation.regime_id,
            "session": observation.benchmark_source,
        }
        for dimension, key in dimensions.items():
            groups.setdefault((dimension, key, trading_date), []).append(observation)

    rollups: list[TcaRollup] = []
    for (dimension, key, trading_date), rows in sorted(groups.items()):
        bps = [row.slippage_bps for row in rows]
        rollups.append(
            TcaRollup(
                dimension=dimension,
                key=key,
                trading_date=trading_date,
                avg_bps=sum(bps, Decimal(0)) / len(bps),
                p50_bps=_percentile(bps, 0.50),
                p95_bps=_percentile(bps, 0.95),
                total_cost_ccy=sum((row.slippage_cost_ccy for row in rows), Decimal(0)),
                fill_count=len(rows),
            )
        )
    return rollups


def detect_alerts(
    observations: Iterable[TcaObservation],
    *,
    policy: dict[str, Decimal] | None = None,
    cluster_limit: int = 3,
) -> list[SlippageBreach | SlippageCluster]:
    """Emit per-fill breaches and strategy cluster pages."""
    rows = list(observations)
    breaches: list[SlippageBreach] = []
    for row in rows:
        threshold = threshold_for(symbol=row.symbol, regime_id=row.regime_id, policy=policy)
        if row.slippage_bps > threshold:
            breaches.append(
                SlippageBreach(
                    alert_type="slippage_breach",
                    fill_id=row.fill_id,
                    tca_id=row.tca_id,
                    strategy_id=row.strategy_id,
                    symbol=row.symbol,
                    broker_id=row.broker_id,
                    regime_id=row.regime_id,
                    slippage_bps=row.slippage_bps,
                    threshold_bps=threshold,
                )
            )

    clusters: list[SlippageCluster] = []
    by_strategy: dict[str, list[SlippageBreach]] = {}
    for breach in breaches:
        by_strategy.setdefault(breach.strategy_id, []).append(breach)
    for strategy_id, strategy_breaches in sorted(by_strategy.items()):
        if len(strategy_breaches) > cluster_limit:
            clusters.append(
                SlippageCluster(
                    alert_type="slippage_cluster",
                    strategy_id=strategy_id,
                    breach_count=len(strategy_breaches),
                    cluster_limit=cluster_limit,
                    fill_ids=tuple(item.fill_id for item in strategy_breaches),
                )
            )
    return [*breaches, *clusters]


__all__ = [
    "SlippageBreach",
    "SlippageCluster",
    "TcaObservation",
    "TcaRollup",
    "build_rollups",
    "detect_alerts",
    "threshold_for",
]
