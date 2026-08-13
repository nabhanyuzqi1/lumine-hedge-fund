# Copyright (c) 2026 Lumine. All rights reserved.
"""Deterministic backtest engine (B-01).

Bars in → equity curve + trades + metrics out. No stochasticity: the
strategy is a fixed rule set so results are reproducible bit-for-bit.

Strategy rules (v1):
- enter LONG when close crosses above SMA(20) with volume above its 20-bar
  average; enter SHORT on the symmetric breakdown;
- exit on the opposite cross or a hard stop (stop_pct of entry).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from lumine.api.demo_data import bars  # reuse the deterministic OHLCV series


@dataclass
class BacktestTrade:
    """One closed trade."""

    symbol: str
    side: str
    entry_ts: str
    exit_ts: str
    entry_price: Decimal
    exit_price: Decimal
    pnl_pct: Decimal


@dataclass
class BacktestMetrics:
    """Performance summary (v1)."""

    total_return_pct: Decimal
    max_drawdown_pct: Decimal
    win_rate_pct: Decimal
    trade_count: int
    sharpe_like: Decimal


@dataclass
class BacktestResult:
    """Full engine output."""

    symbol: str
    timeframe: str
    equity: list[Decimal]
    trades: list[BacktestTrade] = field(default_factory=list)
    metrics: BacktestMetrics | None = None


def _sma(values: list[Decimal], period: int) -> list[Decimal | None]:
    out: list[Decimal | None] = [None] * len(values)
    if len(values) < period:
        return out
    window = sum(values[:period])
    out[period - 1] = window / period
    for i in range(period, len(values)):
        window += values[i] - values[i - period]
        out[i] = window / period
    return out


def run_backtest(symbol: str = "XAUUSD", timeframe: str = "1h", *, stop_pct: Decimal = Decimal("0.02")) -> BacktestResult:
    """Run the v1 rule-based backtest over the deterministic demo bars."""
    rows = bars(symbol, timeframe, limit=400)
    closes = [Decimal(str(row["close"])) for row in rows]
    volumes = [Decimal(str(row["volume"])) for row in rows]
    sma20 = _sma(closes, 20)
    vol_avg = sum(volumes[:20]) / 20 if len(volumes) >= 20 else Decimal("0")

    equity: list[Decimal] = [Decimal("100000")]
    trades: list[BacktestTrade] = []
    position: str | None = None
    entry_price = Decimal("0")
    entry_ts = ""
    peak = Decimal("100000")

    for i in range(20, len(rows)):
        close = closes[i]
        sma = sma20[i]
        vol_ok = volumes[i] > vol_avg
        ts = rows[i]["ts"]

        if position is None and sma is not None and vol_ok:
            if close > sma:
                position = "LONG"
                entry_price = close
                entry_ts = ts
            elif close < sma:
                position = "SHORT"
                entry_price = close
                entry_ts = ts
        elif position is not None:
            stop_hit = abs(close - entry_price) / entry_price >= stop_pct
            cross_hit = (position == "LONG" and close < sma) or (position == "SHORT" and close > sma) if sma is not None else False
            if stop_hit or cross_hit:
                pnl = (close - entry_price) / entry_price if position == "LONG" else (entry_price - close) / entry_price
                trades.append(
                    BacktestTrade(
                        symbol=symbol,
                        side=position,
                        entry_ts=entry_ts,
                        exit_ts=ts,
                        entry_price=entry_price,
                        exit_price=close,
                        pnl_pct=pnl,
                    )
                )
                position = None

        equity.append(equity[-1] * (1 + (closes[i] - closes[i - 1]) / closes[i - 1]))
        peak = max(peak, equity[-1])

    result = BacktestResult(symbol=symbol, timeframe=timeframe, equity=equity, trades=trades)
    result.metrics = _compute_metrics(result)
    return result


def _compute_metrics(result: BacktestResult) -> BacktestMetrics:
    equity = result.equity
    start = equity[0]
    end = equity[-1]
    total_return = (end - start) / start
    peak = equity[0]
    max_dd = Decimal("0")
    for value in equity:
        peak = max(peak, value)
        if peak > 0:
            dd = (value - peak) / peak
            max_dd = min(max_dd, dd)

    if result.trades:
        wins = [t for t in result.trades if t.pnl_pct > 0]
        win_rate = Decimal(len(wins)) / Decimal(len(result.trades))
        returns = [t.pnl_pct for t in result.trades]
        mean = sum(returns, Decimal("0")) / len(returns)
        variance = sum((r - mean) ** 2 for r in returns) / len(returns)
        sharpe = mean / variance.sqrt() if variance > 0 else Decimal("0")
    else:
        win_rate = Decimal("0")
        sharpe = Decimal("0")

    return BacktestMetrics(
        total_return_pct=total_return.quantize(Decimal("0.0001")),
        max_drawdown_pct=max_dd.quantize(Decimal("0.0001")),
        win_rate_pct=win_rate.quantize(Decimal("0.0001")),
        trade_count=len(result.trades),
        sharpe_like=sharpe.quantize(Decimal("0.0001")),
    )
