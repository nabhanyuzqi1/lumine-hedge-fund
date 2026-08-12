# Copyright (c) 2026 Lumine. All rights reserved.
"""Unit tests for TCA rollups and execution-quality alerts."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from lumine.trade_core.tca_quality import (
    SlippageCluster,
    TcaObservation,
    build_rollups,
    detect_alerts,
    threshold_for,
)


def _observation(
    fill_id: str,
    bps: str,
    *,
    strategy: str = "s1",
    regime: str = "normal",
) -> TcaObservation:
    return TcaObservation(
        tca_id=f"tca-{fill_id}",
        fill_id=fill_id,
        strategy_id=strategy,
        symbol="XAUUSD",
        broker_id="broker-a",
        regime_id=regime,
        benchmark_source="arrival_mid",
        decision_ts=datetime(2026, 8, 13, 9, 0, tzinfo=UTC),
        slippage_bps=Decimal(bps),
        slippage_cost_ccy=Decimal("2.00"),
    )


def test_rollups_cover_all_adr_dimensions() -> None:
    rows = build_rollups([_observation("f1", "2"), _observation("f2", "8")])

    assert {(row.dimension, row.key) for row in rows} == {
        ("strategy", "s1"),
        ("broker", "broker-a"),
        ("symbol", "XAUUSD"),
        ("regime", "normal"),
        ("session", "arrival_mid"),
    }
    strategy = next(row for row in rows if row.dimension == "strategy")
    assert strategy.avg_bps == Decimal(5)
    assert strategy.p50_bps == Decimal(5)
    assert strategy.p95_bps == Decimal("7.7")
    assert strategy.total_cost_ccy == Decimal("4.00")
    assert strategy.fill_count == 2


def test_threshold_defaults_and_policy_override() -> None:
    assert threshold_for(symbol="XAUUSD", regime_id="normal") == Decimal(5)
    assert threshold_for(symbol="XAUUSD", regime_id="high_vol") == Decimal(10)
    assert threshold_for(
        symbol="XAUUSD", regime_id="normal", policy={"XAUUSD:normal": Decimal(3)}
    ) == Decimal(3)


def test_alerts_emit_breach_and_cluster_page() -> None:
    rows = [_observation(f"f{i}", "6") for i in range(4)]

    alerts = detect_alerts(rows, cluster_limit=3)

    breaches = [alert for alert in alerts if alert.alert_type == "slippage_breach"]
    clusters = [alert for alert in alerts if alert.alert_type == "slippage_cluster"]
    assert len(breaches) == 4
    assert len(clusters) == 1
    cluster = clusters[0]
    assert isinstance(cluster, SlippageCluster)
    assert cluster.strategy_id == "s1"
    assert cluster.fill_ids == ("f0", "f1", "f2", "f3")
