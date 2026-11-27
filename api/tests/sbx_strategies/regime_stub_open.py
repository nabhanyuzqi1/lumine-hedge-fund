"""Stub strategi TANPA ALLOWED_REGIMES (test: regime tidak memblokir
strategi yang tidak mensyaratkan regime - PRD v2.2 §6.4)."""
from __future__ import annotations

from dataclasses import dataclass

STRATEGY_ID = "regime_stub_open"
STRATEGY_VERSION = "0.0.1"


@dataclass(frozen=True)
class OrderIntent:
    symbol: str
    side: str
    volume: float
    sl: float
    tp: float
    strategy: str = STRATEGY_ID
    reason: str = ""
    sl_distance: float = 0.0
    risk_usd: float = 0.0


@dataclass(frozen=True)
class StrategyParams:
    tf_seconds: int = 300
    force_close_utc: int = 16
    max_spread_abs: float = 0.50


def decide(context: dict, params: StrategyParams | None = None) -> OrderIntent | None:
    candles = context.get("candles") or []
    close = float(candles[-1]["close"]) if candles else 2000.0
    return OrderIntent(symbol=context.get("symbol", "XAUUSD"), side="BUY",
                       volume=0.01, sl=round(close - 2.0, 2),
                       tp=round(close + 4.0, 2),
                       reason="regime_stub_open always-entry")
