# Copyright (c) 2026 Lumine. All rights reserved.
"""Domain-specific API request/response schemas for Sprint 4 routers."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


class PortfolioSummary(BaseModel):
    """High-level portfolio snapshot."""

    portfolio_id: str
    nav: Decimal
    cash: Decimal
    margin_used: Decimal
    open_pnl: Decimal
    closed_pnl: Decimal
    timestamp: datetime


class Position(BaseModel):
    """Open position view."""

    position_id: UUID
    portfolio_id: str
    symbol: str
    direction: Literal["long", "short"]
    volume: Decimal
    entry_price: Decimal
    current_price: Decimal | None = None
    stop_loss: Decimal | None = None
    take_profit: Decimal | None = None
    unrealized_pnl: Decimal
    opened_at: datetime


class ExposureSummary(BaseModel):
    """Exposure breakdown per symbol/bucket."""

    symbol: str
    notional: Decimal
    pct_of_nav: Decimal
    correlated_bucket: str | None = None


class Order(BaseModel):
    """Order lifecycle record."""

    order_id: UUID
    portfolio_id: str
    symbol: str
    side: Literal["buy", "sell"]
    order_type: Literal["market", "limit", "stop"]
    volume: Decimal
    price: Decimal | None = None
    status: Literal["pending", "filled", "partially_filled", "rejected", "cancelled"]
    filled_volume: Decimal
    rejected_reason: str | None = None
    created_at: datetime
    updated_at: datetime


class CreateOrderRequest(BaseModel):
    """Payload to submit a new order."""

    portfolio_id: str
    symbol: str = Field(default="XAUUSD")
    side: Literal["buy", "sell"]
    order_type: Literal["market", "limit", "stop"] = "market"
    volume: Decimal = Field(..., gt=0)
    price: Decimal | None = None
    stop_loss: Decimal | None = None
    take_profit: Decimal | None = None
    idempotency_key: str | None = None


class WorkflowRun(BaseModel):
    """Workflow run summary."""

    run_id: UUID
    workflow_name: str
    status: Literal["pending", "running", "completed", "failed"]
    input_payload: dict[str, Any]
    output_payload: dict[str, Any] | None = None
    started_at: datetime
    finished_at: datetime | None = None


class TriggerWorkflowRequest(BaseModel):
    """Payload to trigger an ad-hoc workflow."""

    workflow_name: str
    input_payload: dict[str, Any] = Field(default_factory=dict)


class LineageRecord(BaseModel):
    """Decision lineage audit record."""

    lineage_id: UUID
    decision_id: str
    decision_type: str
    agent_name: str
    inputs_hash: str
    outputs_hash: str
    policy_version: str
    created_at: datetime


class MarketBar(BaseModel):
    """OHLCV bar for market data endpoints."""

    symbol: str
    timeframe: str
    timestamp: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int


class Signal(BaseModel):
    """Analyst signal view."""

    signal_id: UUID
    symbol: str
    analyst: str
    direction: Literal["bullish", "bearish", "neutral"]
    confidence: float = Field(..., ge=0, le=1)
    rationale: str
    generated_at: datetime


class JournalEntry(BaseModel):
    """Trade journal entry."""

    entry_id: UUID
    trade_id: UUID
    agent_name: str
    reflection: str
    lesson: str
    created_at: datetime


class AdminKey(BaseModel):
    """API key management view."""

    key_id: str
    name: str = ""
    scopes: list[str]
    revoked: bool
    created_at: datetime


class CreateKeyRequest(BaseModel):
    """Payload to create a new API key."""

    key_id: str = Field(..., pattern=r"^[a-z0-9_-]{4,32}$")
    name: str = ""
    scopes: list[str]
    revoked: bool = False


class KillSwitchRequest(BaseModel):
    """Payload to arm/disarm the kill switch."""

    reason: str
    armed: bool = True
    tier: Literal["global", "book", "strategy"] | None = None


class KillSwitchStatus(BaseModel):
    """Current kill-switch state."""

    armed: bool
    reason: str | None = None
    tier: Literal["global", "book", "strategy"] | None = None
    updated_at: datetime | None = None


class ModifyOrderRequest(BaseModel):
    """Payload to modify a pending order (at least one field required)."""

    price: Decimal | None = Field(default=None, gt=0)
    volume: Decimal | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def _require_at_least_one_field(self) -> ModifyOrderRequest:
        if self.price is None and self.volume is None:
            msg = "at least one of price or volume must be provided"
            raise ValueError(msg)
        return self


class MarketQuote(BaseModel):
    """Current bid/ask/last snapshot for a symbol."""

    symbol: str
    bid: Decimal
    ask: Decimal
    mid: Decimal
    last: Decimal
    volume_24h: Decimal
    change_24h: Decimal
    change_pct_24h: Decimal
    timestamp: datetime


class SymbolConfig(BaseModel):
    """Instrument specification for a trading symbol."""

    symbol: str
    description: str
    base_asset: str
    quote_currency: str
    tick_size: Decimal
    lot_size: Decimal
    min_lot_size: Decimal
    max_lot_size: Decimal
    is_active: bool


class VolatilityResponse(BaseModel):
    """Rolling volatility for a symbol (fraction, e.g. 0.12 = 12%)."""

    volatility: float


class SpreadMetrics(BaseModel):
    """Spread statistics for a symbol over a period."""

    avg_spread: Decimal
    avg_pct_spread: Decimal
    min_spread: Decimal
    max_spread: Decimal


class SessionInfo(BaseModel):
    """Current trading session state for a symbol."""

    current_session: Literal["asian", "european", "american", "off"]
    next_session: Literal["asian", "european", "american", "off"]
    time_until_next: int  # seconds
    is_trading_open: bool


class FeatureSet(BaseModel):
    """Computed technical features for a symbol."""

    symbol: str
    features: dict[str, float]
    computed_at: datetime


class SimulateTradeRequest(BaseModel):
    """Payload for a what-if trade simulation."""

    symbol: str
    side: Literal["buy", "sell"]
    volume: Decimal = Field(..., gt=0)
    price: Decimal = Field(..., gt=0)


class SimulateTradeResult(BaseModel):
    """Projected portfolio impact of a hypothetical trade."""

    projected_nav: Decimal
    margin_required: Decimal
    pnl_change: Decimal


class CreatedAdminKey(BaseModel):
    """API key creation response containing the secret exactly once."""

    key_id: str
    secret: str
    scopes: list[str]
    created_at: datetime


class RpcCommandRequest(BaseModel):
    """Generic RPC command payload."""

    command: str
    parameters: dict[str, Any] = Field(default_factory=dict)


class RpcCommandResponse(BaseModel):
    """RPC command acceptance receipt."""

    command_id: UUID
    command: str
    status: Literal["accepted", "rejected"]
    reason: str | None = None
    enqueued_at: datetime


class RpcCommandResult(BaseModel):
    """RPC command execution status/result (polled by command_id)."""

    command_id: UUID
    command: str
    status: Literal["queued", "processing", "completed", "failed"]
    result: dict[str, Any] | None = None
    error: str | None = None
    enqueued_at: str | None = None
    processed_at: str | None = None


# ── B-06 additions ─────────────────────────────────────────────────────────

class EquityPoint(BaseModel):
    """One point on the portfolio equity curve."""

    ts: datetime
    nav: Decimal
    equity: Decimal
    drawdown: Decimal


class OrderHistoryEntry(BaseModel):
    """One order state transition (append-only audit)."""

    order_id: UUID
    previous_state: str
    new_state: str
    actor_role: str
    actor_id: str | None = None
    reason: str | None = None
    decision_ts: datetime


class BulkStatusRequest(BaseModel):
    """Batch order status check payload."""

    order_ids: list[UUID] = Field(min_length=1, max_length=100)


class BulkStatusResult(BaseModel):
    """Batch order status check result."""

    statuses: dict[str, str]
    total: int


class CreatePortfolioRequest(BaseModel):
    """Create a portfolio (single-portfolio v1: returns the default)."""

    name: str = "default"
    currency: str = "USD"


class CancelAllResult(BaseModel):
    """Cancel-all outcome."""

    cancelled: int
    portfolio_id: str


# ── Superadmin / System ─────────────────────────────────────────────────────

class ServiceStatus(BaseModel):
    """Status satu container/service di stack."""

    name: str
    status: str  # running / stopped / unhealthy / unknown
    health: str | None = None  # healthy / unhealthy / starting / None
    image: str | None = None
    uptime: str | None = None


class SystemInfo(BaseModel):
    """Snapshot status seluruh sistem untuk superadmin control center."""

    services: list[ServiceStatus]
    llm_gateway_url: str
    llm_gateway_configured: bool  # True jika API key terisi
    demo_data: bool
    environment: str
    version: str
    # B9: symbol aktif (enable/disable currency via superadmin).
    enabled_symbols: list[str] = ["XAUUSD"]


class SystemConfigUpdate(BaseModel):
    """Payload untuk memperbarui konfigurasi runtime via superadmin."""

    llm_gateway_api_key: str | None = None
    llm_gateway_url: str | None = None
    demo_data: bool | None = None
    llm_daily_budget_usd: float | None = None
    llm_default_model: str | None = None
    max_exposure_per_trade: float | None = None
    risk_per_trade: float | None = None
    max_daily_loss_pct: float | None = None
    # B9: daftar symbol aktif (multicurrency enable/disable). Default
    # ["XAUUSD"] — fokus matangkan 1 stream sebelum multi-stream.
    enabled_symbols: list[str] | None = None
