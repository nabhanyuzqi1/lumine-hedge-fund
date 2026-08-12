# Copyright (c) 2026 Lumine. All rights reserved.
"""Unit tests for arrival-price transaction cost analysis."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from lumine.trade_core.tca import calculate_tca, resolve_benchmark

DECISION_TS = datetime(2026, 8, 13, 9, 0, tzinfo=UTC)


def _session(*rows: object) -> MagicMock:
    session = MagicMock()
    result = MagicMock()
    result.scalar_one_or_none.side_effect = [*rows, None]
    session.execute = AsyncMock(return_value=result)
    return session


class TestCalculateTca:
    def test_buy_slippage_is_fill_minus_arrival_mid(self) -> None:
        result = calculate_tca(
            side="BUY",
            fill_price=Decimal("2735.00"),
            benchmark_price=Decimal("2734.00"),
            size=Decimal(2),
            pip_value=Decimal(10),
            pip_size=Decimal("0.1"),
        )

        assert result.slippage == Decimal("1.00")
        assert result.slippage_bps == Decimal("3.6576")
        assert result.slippage_cost_ccy == Decimal("20.00")
        assert result.benchmark_source == "arrival_mid"

    def test_sell_slippage_is_arrival_mid_minus_fill(self) -> None:
        result = calculate_tca(
            side="SELL",
            fill_price=Decimal("2733.00"),
            benchmark_price=Decimal("2734.00"),
            size=Decimal(2),
            pip_value=Decimal(10),
            pip_size=Decimal("0.1"),
        )

        assert result.slippage == Decimal("1.00")
        assert result.slippage_bps == Decimal("3.6576")

    def test_invalid_side_and_non_positive_benchmark_fail_closed(self) -> None:
        with pytest.raises(ValueError, match="side"):
            calculate_tca(
                side="HOLD",
                fill_price=Decimal(10),
                benchmark_price=Decimal(10),
                size=Decimal(1),
                pip_value=Decimal(1),
            )

        with pytest.raises(ValueError, match="benchmark"):
            calculate_tca(
                side="BUY",
                fill_price=Decimal(10),
                benchmark_price=Decimal(0),
                size=Decimal(1),
                pip_value=Decimal(1),
            )


class TestResolveBenchmark:
    async def test_exact_tick_uses_arrival_mid(self) -> None:
        tick = SimpleNamespace(bid=Decimal("2733.50"), ask=Decimal("2734.50"), ts=DECISION_TS)
        session = _session(tick)

        result = await resolve_benchmark(session, "XAUUSD", DECISION_TS)

        assert result.price == Decimal("2734.00")
        assert result.source == "arrival_mid"
        session.execute.assert_awaited_once()

    async def test_closed_market_uses_next_session_open_tick(self) -> None:
        opening_ts = datetime(2026, 8, 14, 0, 0, tzinfo=UTC)
        opening_tick = SimpleNamespace(
            bid=Decimal("2740.00"), ask=Decimal("2740.20"), ts=opening_ts
        )
        session = _session(opening_tick)
        calendar = SimpleNamespace(
            is_closed=lambda *_args: True,
            next_session_open=lambda *_args: opening_ts,
        )

        result = await resolve_benchmark(session, "XAUUSD", DECISION_TS, calendar=calendar)

        assert result.price == Decimal("2740.10")
        assert result.source == "session_open"
        assert result.ts == opening_ts

    async def test_missing_arrival_tick_without_next_open_fails(self) -> None:
        session = _session(None)

        with pytest.raises(ValueError, match="benchmark"):
            await resolve_benchmark(session, "XAUUSD", DECISION_TS)
