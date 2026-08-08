# Copyright (c) 2026 Lumine. All rights reserved.
"""Unit tests for shared/types.py — type aliases and enums."""

from __future__ import annotations

from lumine.shared.types import (
    AgentRole,
    DecisionOutcome,
    Direction,
    Instrument,
    LineageStatus,
    OrderType,
    RiskVerdict,
    StreamType,
    Timeframe,
)


class TestDirection:
    def test_buy_is_buy(self) -> None:
        assert Direction.BUY.value == "buy"

    def test_sell_is_sell(self) -> None:
        assert Direction.SELL.value == "sell"

    def test_is_str_enum(self) -> None:
        assert isinstance(Direction.BUY, str)


class TestOrderType:
    def test_known_values(self) -> None:
        assert OrderType.MARKET.value == "market"
        assert OrderType.LIMIT.value == "limit"
        assert OrderType.STOP.value == "stop"

    def test_is_str_enum(self) -> None:
        assert isinstance(OrderType.MARKET, str)


class TestDecisionOutcome:
    def test_all_outcomes(self) -> None:
        assert DecisionOutcome.STRONG_BUY.value == "strong_buy"
        assert DecisionOutcome.BUY.value == "buy"
        assert DecisionOutcome.NEUTRAL.value == "neutral"
        assert DecisionOutcome.SELL.value == "sell"
        assert DecisionOutcome.STRONG_SELL.value == "strong_sell"
        assert DecisionOutcome.HALT.value == "halt"

    def test_halt_is_safe_state(self) -> None:
        """HALT represents kill-switch or safe-state trigger."""
        assert DecisionOutcome.HALT.value == "halt"


class TestRiskVerdict:
    def test_known_verdicts(self) -> None:
        assert RiskVerdict.APPROVED.value == "approved"
        assert RiskVerdict.REDUCED.value == "reduced"
        assert RiskVerdict.REJECTED.value == "rejected"


class TestLineageStatus:
    def test_lifecycle_states(self) -> None:
        assert LineageStatus.PROPOSED.value == "proposed"
        assert LineageStatus.RISK_APPROVED.value == "risk_approved"
        assert LineageStatus.RISK_REJECTED.value == "risk_rejected"
        assert LineageStatus.DISPATCHED.value == "dispatched"
        assert LineageStatus.FILLED.value == "filled"
        assert LineageStatus.PARTIALLY_FILLED.value == "partially_filled"
        assert LineageStatus.REJECTED.value == "rejected"
        assert LineageStatus.CANCELLED.value == "cancelled"


class TestAgentRole:
    def test_agent_roles(self) -> None:
        assert AgentRole.TECHNICAL_ANALYST.value == "technical_analyst"
        assert AgentRole.MACRO_ANALYST.value == "macro_analyst"
        assert AgentRole.NEWS_ANALYST.value == "news_analyst"
        assert AgentRole.SMC_ANALYST.value == "smc_analyst"
        assert AgentRole.IC_FORUM.value == "ic_forum"
        assert AgentRole.CIO.value == "cio"
        assert AgentRole.RISK_OFFICER.value == "risk_officer"
        assert AgentRole.PORTFOLIO_MANAGER.value == "portfolio_manager"


class TestStreamType:
    def test_stream_types(self) -> None:
        assert StreamType.MARKET_DATA.value == "market_data"
        assert StreamType.ANALYST_OUTPUTS.value == "analyst_outputs"
        assert StreamType.IC_DECISIONS.value == "ic_decisions"
        assert StreamType.CIO_PROPOSALS.value == "cio_proposals"
        assert StreamType.RISK_ASSESSMENTS.value == "risk_assessments"
        assert StreamType.EXECUTION_ORDERS.value == "execution_orders"


class TestInstrument:
    def test_xauusd_is_defined(self) -> None:
        assert Instrument.XAUUSD.value == "XAUUSD"


class TestTimeframe:
    def test_all_timeframes(self) -> None:
        assert Timeframe.M1.value == "M1"
        assert Timeframe.M5.value == "M5"
        assert Timeframe.M15.value == "M15"
        assert Timeframe.M30.value == "M30"
        assert Timeframe.H1.value == "H1"
        assert Timeframe.H4.value == "H4"
        assert Timeframe.D1.value == "D1"
        assert Timeframe.W1.value == "W1"
        assert Timeframe.MN1.value == "MN1"
