# Copyright (c) 2026 Lumine. All rights reserved.
"""Backtest API router — run strategy backtests and return results."""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter

from lumine.api.middleware.auth import AuthenticatedPrincipal, require_scope
from lumine.backtest.engine import BacktestResult, run_backtest

router = APIRouter(prefix="/backtest", tags=["backtest"])


@router.get("/run")
async def run_backtest_endpoint(
    _principal: Annotated[AuthenticatedPrincipal, require_scope("backtest:read")],
    symbol: str = "XAUUSD",
    timeframe: str = "1h",
    stop_pct: float = 0.02,
) -> dict:
    """Run backtest and return equity curve + trades + metrics.

    Args:
        symbol: Trading symbol (default XAUUSD)
        timeframe: Bar timeframe (default 1h)
        stop_pct: Stop loss percentage (default 2%)

    Returns:
        BacktestResult with equity, trades, metrics
    """
    result: BacktestResult = run_backtest(
        symbol=symbol,
        timeframe=timeframe,
        stop_pct=Decimal(str(stop_pct)),
    )

    # Convert Decimal to float for JSON serialization
    return {
        "symbol": result.symbol,
        "timeframe": result.timeframe,
        "equity": [float(e) for e in result.equity],
        "trades": [
            {
                "symbol": t.symbol,
                "side": t.side,
                "entry_ts": t.entry_ts,
                "exit_ts": t.exit_ts,
                "entry_price": float(t.entry_price),
                "exit_price": float(t.exit_price),
                "pnl_pct": float(t.pnl_pct),
            }
            for t in result.trades
        ],
        "metrics": {
            "total_return_pct": float(result.metrics.total_return_pct) if result.metrics else 0.0,
            "max_drawdown_pct": float(result.metrics.max_drawdown_pct) if result.metrics else 0.0,
            "win_rate_pct": float(result.metrics.win_rate_pct) if result.metrics else 0.0,
            "trade_count": result.metrics.trade_count if result.metrics else 0,
            "sharpe_like": float(result.metrics.sharpe_like) if result.metrics else 0.0,
        } if result.metrics else None,
    }
