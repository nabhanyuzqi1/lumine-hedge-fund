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
        assert Direction.BUY == "buy"

    def test_sell_is_sell(self) -> None:
        assert Direction.SELL == "sell"

    def test_is_str_enum(self) -> None:
        assert isinstance(Direction.BUY, str)


class TestOrderType:
    def test_known_values(self) -> None:
        assert OrderType.MARKET == "market"
        assert OrderType.LIMIT == "limit"
        assert OrderType.STOP == "stop"

    def test_is_str_enum(self) -> None:
        assert isinstance(OrderType.MARKET, str)


class TestDecisionOutcome:
    def test_all_outcomes(self) -> None:
        assert DecisionOutcome.STRONG_BUY == "strong_buy"
        assert DecisionOutcome.BUY == "buy"
        assert DecisionOutcome.NEUTRAL == "neutral"
        assert DecisionOutcome.SELL == "sell"
        assert DecisionOutcome.STRONG_SELL == "strong_sell"
        assert DecisionOutcome.HALT == "halt"

    def test_halt_is_safe_state(self) -> None:
        """HALT represents kill-switch or safe-state trigger."""
        assert DecisionOutcome.HALT == "halt"


class TestRiskVerdict:
    def test_known_verdicts(self) -> None:
        assert RiskVerdict.APPROVED == "approved"
        assert RiskVerdict.REDUCED == "reduced"
        assert RiskVerdict.REJECTED == "rejected"


class TestLineageStatus:
    def test_lifecycle_states(self) -> None:
        assert LineageStatus.PROPOSED == "proposed"
        assert LineageStatus.RISK_APPROVED == "risk_approved"
        assert LineageStatus.RISK_REJECTED == "risk_rejected"
        assert LineageStatus.DISPATCHED == "dispatched"
        assert LineageStatus.FILLED == "filled"
        assert LineageStatus.PARTIALLY_FILLED == "partially_filled"
        assert LineageStatus.REJECTED == "rejected"
        assert LineageStatus.CANCELLED == "cancelled"


class TestAgentRole:
    def test_agent_roles(self) -> None:
        assert AgentRole.TECHNICAL_ANALYST == "technical_analyst"
        assert AgentRole.MACRO_ANALYST == "macro_analyst"
        assert AgentRole.NEWS_ANALYST == "news_analyst"
        assert AgentRole.SMC_ANALYST == "smc_analyst"
        assert AgentRole.IC_FORUM == "ic_forum"
        assert AgentRole.CIO == "cio"
        assert AgentRole.RISK_OFFICER == "risk_officer"
        assert AgentRole.PORTFOLIO_MANAGER == "portfolio_manager"


class TestStreamType:
    def test_stream_types(self) -> None:
        assert StreamType.MARKET_DATA == "market_data"
        assert StreamType.ANALYST_OUTPUTS == "analyst_outputs"
        assert StreamType.IC_DECISIONS == "ic_decisions"
        assert StreamType.CIO_PROPOSALS == "cio_proposals"
        assert StreamType.RISK_ASSESSMENTS == "risk_assessments"
        assert StreamType.EXECUTION_ORDERS == "execution_orders"


class TestInstrument:
    def test_xauusd_is_defined(self) -> None:
        assert Instrument.XAUUSD == "XAUUSD"


class TestTimeframe:
    def test_all_timeframes(self) -> None:
        assert Timeframe.M1 == "M1"
        assert Timeframe.M5 == "M5"
        assert Timeframe.M15 == "M15"
        assert Timeframe.M30 == "M30"
        assert Timeframe.H1 == "H1"
        assert Timeframe.H4 == "H4"
        assert Timeframe.D1 == "D1"
        assert Timeframe.W1 == "W1"
        assert Timeframe.MN1 == "MN1"
