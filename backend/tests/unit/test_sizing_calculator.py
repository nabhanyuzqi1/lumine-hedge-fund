# Copyright (c) 2026 Lumine. All rights reserved.
"""Unit tests for the deterministic sizing calculator (ADR-0016)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from lumine.trade_core.sizing_calculator import (
    SizingError,
    base_volume,
    calculate_size,
    clamp_volume,
    normalized_stop_price,
    stop_distance,
)


class TestBaseVolume:
    def test_risk_targeted_volume(self) -> None:
        # equity 100k, risk 1% = 1000; stop 20 * 10 = 200 per lot → 5 lots.
        volume = base_volume(
            equity=Decimal(100000),
            risk_per_trade=Decimal("0.01"),
            stop_distance_pips=Decimal(20),
            pip_value=Decimal(10),
        )
        assert volume == Decimal("5.00")

    def test_floors_down_never_rounds_into_risk(self) -> None:
        volume = base_volume(
            equity=Decimal(100000),
            risk_per_trade=Decimal("0.01"),
            stop_distance_pips=Decimal(3),
            pip_value=Decimal(10),
        )
        # 1000 / 30 = 33.333… → floor to 33.33 (not 33.34).
        assert volume == Decimal("33.33")

    @pytest.mark.parametrize(
        ("equity", "risk", "stop", "pip"),
        [
            (Decimal(0), Decimal("0.01"), Decimal(10), Decimal(10)),
            (Decimal(100000), Decimal(0), Decimal(10), Decimal(10)),
            (Decimal(100000), Decimal("0.01"), Decimal(0), Decimal(10)),
            (Decimal(100000), Decimal("0.01"), Decimal(10), Decimal(0)),
        ],
    )
    def test_invalid_inputs_raise(
        self,
        equity: Decimal,
        risk: Decimal,
        stop: Decimal,
        pip: Decimal,
    ) -> None:
        with pytest.raises(SizingError):
            base_volume(equity, risk, stop, pip)


class TestStopDistance:
    def test_atr_times_multiplier(self) -> None:
        assert stop_distance(Decimal(15), Decimal(2)) == Decimal(30)


class TestClamp:
    def test_clamps_low_and_high(self) -> None:
        assert clamp_volume(Decimal("0.001"), Decimal("0.01"), Decimal(100)) == Decimal("0.01")
        assert clamp_volume(Decimal(500), Decimal("0.01"), Decimal(100)) == Decimal(100)
        assert clamp_volume(Decimal("1.5"), Decimal("0.01"), Decimal(100)) == Decimal("1.5")


class TestCalculateSize:
    def test_buy_stop_below_entry(self) -> None:
        result = calculate_size(
            entry_price=Decimal("2734.50"),
            atr_14=Decimal(15),
            equity=Decimal(100000),
            risk_per_trade=Decimal("0.01"),
            atr_multiplier=Decimal(2),
            pip_value=Decimal(10),
            side="BUY",
        )
        assert result.stop_distance == Decimal(30)
        assert result.stop_price == Decimal("2704.50")
        assert result.final_volume > 0

    def test_sell_stop_above_entry(self) -> None:
        result = calculate_size(
            entry_price=Decimal("2734.50"),
            atr_14=Decimal(15),
            equity=Decimal(100000),
            risk_per_trade=Decimal("0.01"),
            atr_multiplier=Decimal(2),
            pip_value=Decimal(10),
            side="SELL",
        )
        assert result.stop_price == Decimal("2764.50")

    def test_policy_multiplier_scales_final_volume(self) -> None:
        base = calculate_size(
            entry_price=Decimal(2700),
            atr_14=Decimal(10),
            equity=Decimal(100000),
            risk_per_trade=Decimal("0.01"),
            atr_multiplier=Decimal(2),
            pip_value=Decimal(10),
        )
        scaled = calculate_size(
            entry_price=Decimal(2700),
            atr_14=Decimal(10),
            equity=Decimal(100000),
            risk_per_trade=Decimal("0.01"),
            atr_multiplier=Decimal(2),
            pip_value=Decimal(10),
            risk_adjustment_multiplier=Decimal("0.5"),
        )
        assert scaled.final_volume == (base.final_volume * Decimal("0.5")).quantize(Decimal("0.01"))

    def test_bad_side_rejected(self) -> None:
        with pytest.raises(SizingError):
            normalized_stop_price(Decimal(2700), Decimal(20), "SIDEWAYS")
