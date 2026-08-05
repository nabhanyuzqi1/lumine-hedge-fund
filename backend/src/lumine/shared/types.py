# Copyright (c) 2026 Lumine. All rights reserved.
"""Shared type aliases and enums used across all Lumine modules."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated

# ── Domain identifiers ────────────────────────────────────────────────────────

type TradeId = str
type OrderId = str
type LineageId = str
type AgentId = str
type StrategyId = str
type PortfolioId = str
type PromptVersion = str  # e.g. "technical_analyst@v1"

# ── Precision types ───────────────────────────────────────────────────────────

# Price in instrument quote currency (e.g. 2734.50 for XAUUSD)
Price = Annotated[float, "price"]
# Volume in lots (e.g. 0.01, 0.10, 1.00)
Volume = Annotated[float, "volume"]
# P&L in account base currency
Pnl = Annotated[float, "pnl"]
# Exposure as fraction of equity (0.02 = 2%)
ExposureRatio = Annotated[float, "exposure_ratio"]
# Timestamp with timezone awareness
Timestamp = datetime

# ── Enums ─────────────────────────────────────────────────────────────────────


class Direction(StrEnum):
    """Trade direction."""

    BUY = "buy"
    SELL = "sell"


class OrderType(StrEnum):
    """Order type dispatched to MT5 bridge."""

    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"


class DecisionOutcome(StrEnum):
    """Final decision outcome from the investment committee."""

    STRONG_BUY = "strong_buy"
    BUY = "buy"
    NEUTRAL = "neutral"
    SELL = "sell"
    STRONG_SELL = "strong_sell"
    HALT = "halt"  # Kill-switch or safe-state triggered


class RiskVerdict(StrEnum):
    """Risk engine verdict on a proposal."""

    APPROVED = "approved"
    REDUCED = "reduced"  # Volume adjusted down
    REJECTED = "rejected"


class LineageStatus(StrEnum):
    """Status of a lineage record (D3-7)."""

    PROPOSED = "proposed"
    RISK_APPROVED = "risk_approved"
    RISK_REJECTED = "risk_rejected"
    DISPATCHED = "dispatched"
    FILLED = "filled"
    PARTIALLY_FILLED = "partially_filled"
    REJECTED = "rejected"  # By broker
    CANCELLED = "cancelled"


class AgentRole(StrEnum):
    """Agent role in the hierarchy (D4-1)."""

    TECHNICAL_ANALYST = "technical_analyst"
    MACRO_ANALYST = "macro_analyst"
    NEWS_ANALYST = "news_analyst"
    SMC_ANALYST = "smc_analyst"
    IC_FORUM = "ic_forum"
    CIO = "cio"
    RISK_OFFICER = "risk_officer"
    PORTFOLIO_MANAGER = "portfolio_manager"


class StreamType(StrEnum):
    """SSE stream types (D9-7)."""

    MARKET_DATA = "market_data"
    ANALYST_OUTPUTS = "analyst_outputs"
    IC_DECISIONS = "ic_decisions"
    CIO_PROPOSALS = "cio_proposals"
    RISK_ASSESSMENTS = "risk_assessments"
    EXECUTION_ORDERS = "execution_orders"


class Instrument(StrEnum):
    """Tradable instruments."""

    XAUUSD = "XAUUSD"
    # Future: EURUSD, GBPUSD, US30, NAS100, BTCUSD, etc.


class Timeframe(StrEnum):
    """MT5 timeframes."""

    M1 = "M1"
    M5 = "M5"
    M15 = "M15"
    M30 = "M30"
    H1 = "H1"
    H4 = "H4"
    D1 = "D1"
    W1 = "W1"
    MN1 = "MN1"
