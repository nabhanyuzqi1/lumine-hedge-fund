# Copyright (c) 2026 Lumine. All rights reserved.
"""Unit tests for TCA calculation (ADR-0040)."""

from decimal import Decimal

import pytest

from lumine.trade_core.tca import (
    _mid,
    calculate_tca,
)


class TestCalculateTca:
    """Test side-aware slippage calculations."""

    def test_buy_slippage_positive(self):
        """Buy at higher price than benchmark = positive slippage cost."""
        result = calculate_tca(
            side="BUY",
            fill_price=Decimal("2750.10"),
            benchmark_price=Decimal("2750.00"),
            size=Decimal("1.0"),
            pip_value=Decimal("10.0"),
        )

        assert result.slippage == Decimal("0.10")
        assert result.slippage_bps == Decimal("0.3636")
        assert result.slippage_cost_ccy == Decimal("1.0000")
        assert result.benchmark_source == "arrival_mid"

    def test_sell_slippage_positive(self):
        """Sell at higher price than benchmark = positive slippage."""
        result = calculate_tca(
            side="SELL",
            fill_price=Decimal("2749.90"),
            benchmark_price=Decimal("2750.00"),
            size=Decimal("1.0"),
            pip_value=Decimal("10.0"),
        )

        assert result.slippage == Decimal("0.10")
        assert result.slippage_bps == Decimal("0.3636")
        assert result.slippage_cost_ccy == Decimal("1.0000")

    def test_buy_no_slippage(self):
        """Fill equals benchmark = zero slippage."""
        result = calculate_tca(
            side="BUY",
            fill_price=Decimal("2750.00"),
            benchmark_price=Decimal("2750.00"),
            size=Decimal("1.0"),
            pip_value=Decimal("10.0"),
        )

        assert result.slippage == Decimal(0)
        assert result.slippage_bps == Decimal("0.0000")
        assert result.slippage_cost_ccy == Decimal("0.0000")

    def test_large_position(self):
        """Larger position scales cost linearly."""
        result = calculate_tca(
            side="BUY",
            fill_price=Decimal("2750.50"),
            benchmark_price=Decimal("2750.00"),
            size=Decimal("10.0"),
            pip_value=Decimal("10.0"),
        )

        # 0.50 * 10 * 10 = 50.00
        assert result.slippage_cost_ccy == Decimal("50.0000")

    def test_invalid_side(self):
        """Invalid side raises ValueError."""
        with pytest.raises(ValueError, match="side must be BUY or SELL"):
            calculate_tca(
                side="HOLD",
                fill_price=Decimal("2750.00"),
                benchmark_price=Decimal("2750.00"),
                size=Decimal("1.0"),
                pip_value=Decimal("10.0"),
            )

    def test_invalid_benchmark_price(self):
        """Zero benchmark price raises error."""
        with pytest.raises(ValueError, match="benchmark price must be positive"):
            calculate_tca(
                side="BUY",
                fill_price=Decimal("2750.00"),
                benchmark_price=Decimal(0),
                size=Decimal("1.0"),
                pip_value=Decimal("10.0"),
            )

    def test_invalid_fill_price(self):
        """Zero fill price raises error."""
        with pytest.raises(ValueError, match="fill price must be positive"):
            calculate_tca(
                side="BUY",
                fill_price=Decimal(0),
                benchmark_price=Decimal("2750.00"),
                size=Decimal("1.0"),
                pip_value=Decimal("10.0"),
            )

    def test_case_insensitive_side(self):
        """Side is case-insensitive."""
        result_upper = calculate_tca(
            side="BUY",
            fill_price=Decimal("2750.10"),
            benchmark_price=Decimal("2750.00"),
            size=Decimal("1.0"),
            pip_value=Decimal("10.0"),
        )

        result_lower = calculate_tca(
            side="buy",
            fill_price=Decimal("2750.10"),
            benchmark_price=Decimal("2750.00"),
            size=Decimal("1.0"),
            pip_value=Decimal("10.0"),
        )

        assert result_upper.slippage == result_lower.slippage


class TestMid:
    """Test midpoint calculation from tick data."""

    def test_valid_mid(self):
        """Valid bid/ask produces correct midpoint."""
        class MockTick:
            bid = Decimal("2749.90")
            ask = Decimal("2750.10")

        tick = MockTick()
        mid = _mid(tick)

        assert mid == Decimal("2750.00")

    def test_invalid_bid_zero(self):
        """Zero bid raises error."""
        class MockTick:
            bid = Decimal(0)
            ask = Decimal("2750.00")

        tick = MockTick()
        with pytest.raises(ValueError, match="invalid bid/ask"):
            _mid(tick)

    def test_ask_less_than_bid(self):
        """Ask < bid is invalid."""
        class MockTick:
            bid = Decimal("2750.10")
            ask = Decimal("2750.00")

        tick = MockTick()
        with pytest.raises(ValueError, match="invalid bid/ask"):
            _mid(tick)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
