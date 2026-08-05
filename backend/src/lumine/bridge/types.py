# Copyright (c) 2026 Lumine. All rights reserved.
"""MT5 bridge command/result contracts.

Pydantic models for the JSON envelopes exchanged between Lumine and the
MetaTrader 5 Expert Advisor via Redis.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Self

from pydantic import BaseModel, Field, model_validator


class BridgeStatus(StrEnum):
    """Lifecycle states for a bridge command/result."""

    PENDING = "pending"
    SENT = "sent"
    ACKNOWLEDGED = "acknowledged"
    FILLED = "filled"
    PARTIAL = "partial"
    REJECTED = "rejected"
    ERROR = "error"
    TIMEOUT = "timeout"


class BridgeCommand(BaseModel):
    """A command sent from Lumine to the MT5 EA.

    The EA consumes commands from the Redis LIST ``mt5:commands`` and
    replies by publishing a ``BridgeResult`` to ``mt5:results``.
    """

    command_id: str = Field(..., min_length=1)
    order_id: str | None = None
    action: str = Field(..., pattern=r"^(BUY|SELL|CLOSE|MODIFY)$")
    symbol: str = Field(..., min_length=1)
    volume: float = Field(default=0.01, ge=0.0)
    order_type: str = Field(default="market", pattern=r"^(market|limit|stop)$")
    stop_loss: float | None = None
    take_profit: float | None = None
    idempotency_key: str | None = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @model_validator(mode="after")
    def _check_command_invariants(self) -> Self:
        if self.action in {"BUY", "SELL"} and self.volume <= 0:
            msg = "volume must be positive for BUY/SELL commands"
            raise ValueError(msg)
        if (
            self.action == "BUY"
            and self.stop_loss is not None
            and self.take_profit is not None
            and self.stop_loss >= self.take_profit
        ):
            msg = "stop_loss must be below take_profit for BUY commands"
            raise ValueError(msg)
        if (
            self.action == "SELL"
            and self.stop_loss is not None
            and self.take_profit is not None
            and self.stop_loss <= self.take_profit
        ):
            msg = "stop_loss must be above take_profit for SELL commands"
            raise ValueError(msg)
        if self.idempotency_key is None:
            self.idempotency_key = self.command_id
        return self


class BridgeResult(BaseModel):
    """A result published by the MT5 EA in response to a ``BridgeCommand``."""

    command_id: str = Field(..., min_length=1)
    order_id: str | None = None
    ticket: int | None = None
    status: BridgeStatus
    fill_price: float | None = None
    fill_volume: float | None = None
    error_code: int | None = None
    error_message: str | None = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @model_validator(mode="after")
    def _check_result_invariants(self) -> Self:
        if self.status in {BridgeStatus.REJECTED, BridgeStatus.ERROR} and not self.error_message:
            msg = f"error_message is required for status {self.status.value}"
            raise ValueError(msg)
        return self
