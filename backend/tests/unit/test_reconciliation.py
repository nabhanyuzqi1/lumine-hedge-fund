# Copyright (c) 2026 Lumine. All rights reserved.
"""Unit tests for reconciliation logic (ADR-0021)."""

from __future__ import annotations

from decimal import Decimal

from lumine.trade_core.reconciliation import (
    compare_fill,
    reconciliation_gate,
)


class TestCompareFill:
    def test_exact_fill_no_mismatch(self) -> None:
        result = compare_fill(
            expected_price=Decimal("2734.50"),
            fill_price=Decimal("2734.50"),
            expected_volume=Decimal("1.00"),
            fill_volume=Decimal("1.00"),
        )
        assert result.mismatch is False
        assert result.price_deviation_pct == Decimal(0)
        assert result.volume_deviation_pct == Decimal(0)

    def test_within_tolerance_no_mismatch(self) -> None:
        result = compare_fill(
            expected_price=Decimal("2734.50"),
            fill_price=Decimal("2735.00"),  # 0.018% < 0.5%
            expected_volume=Decimal("1.00"),
            fill_volume=Decimal("1.00"),
        )
        assert result.mismatch is False

    def test_price_beyond_tolerance_mismatches(self) -> None:
        result = compare_fill(
            expected_price=Decimal("2734.50"),
            fill_price=Decimal("2760.00"),  # 0.93% > 0.5%
            expected_volume=Decimal("1.00"),
            fill_volume=Decimal("1.00"),
        )
        assert result.price_mismatch is True
        assert result.mismatch is True

    def test_volume_beyond_tolerance_mismatches(self) -> None:
        result = compare_fill(
            expected_price=Decimal("2734.50"),
            fill_price=Decimal("2734.50"),
            expected_volume=Decimal("1.00"),
            fill_volume=Decimal("0.50"),  # 50% > 1%
        )
        assert result.volume_mismatch is True
        assert result.mismatch is True

    def test_custom_tolerances(self) -> None:
        result = compare_fill(
            expected_price=Decimal(1000),
            fill_price=Decimal(1001),  # 0.1%
            expected_volume=Decimal(1),
            fill_volume=Decimal(1),
            price_tolerance_pct=Decimal("0.002"),  # 0.2% — within
        )
        assert result.mismatch is False
        result = compare_fill(
            expected_price=Decimal(1000),
            fill_price=Decimal(1001),
            expected_volume=Decimal(1),
            fill_volume=Decimal(1),
            price_tolerance_pct=Decimal("0.0005"),  # 0.05% — beyond
        )
        assert result.mismatch is True


class TestReconciliationGate:
    def test_closed_promoted_to_settled_on_broker_confirmation(self) -> None:
        gate = reconciliation_gate(internal_status="CLOSED", broker_status="SETTLED")
        assert gate.settled is True
        assert gate.drift is False

    def test_closed_with_broker_still_open_is_drift(self) -> None:
        gate = reconciliation_gate(internal_status="CLOSED", broker_status="OPEN")
        assert gate.settled is False
        assert gate.drift is True

    def test_non_closed_positions_are_not_drift(self) -> None:
        gate = reconciliation_gate(internal_status="OPEN", broker_status="OPEN")
        assert gate.settled is True
        assert gate.drift is False
