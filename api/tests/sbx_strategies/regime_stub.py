"""Stub strategi untuk test gate regime (PRD v2.2 §6): selalu entry.

ALLOWED_REGIMES = ["TREND_UP"] dipakai untuk membuktikan:
  - entry di-label RANGE/HIGH_VOLATILITY/UNKNOWN DIBLOKIR gate regime;
  - entry saat TREND_UP lolos;
  - regime TIDAK mengubah risk limit (intent sama, gate hanya filter).
"""
from __future__ import annotations

from dataclasses import dataclass

STRATEGY_ID = "regime_stub"
STRATEGY_VERSION = "0.0.1"

ALLOWED_REGIMES = ["TREND_UP"]  # PRD §6.4: strategi mendefinisikan regime izin


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
                       reason="regime_stub always-entry")
