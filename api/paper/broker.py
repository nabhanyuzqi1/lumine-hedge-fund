"""Paper broker: fills and exits for simulated positions.

Same rules the live execution layer must apply later (documented in the
strategy skill): market orders fill at the opposite quote side, SL/TP are
checked on every price update, and if a bar gaps through both levels the SL
wins (conservative). A time exit (E1) flattens at force_close_utc.

Contract size per POSISI (multipair P2): XAUUSD 100 oz/lot (default,
perilaku lama), BTCUSD 1 BTC/lot (t_f2mp1). force_close_hour_utc=None
menonaktifkan time exit (strategi 24/7 seperti BTC).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timezone

XAUUSD_USD_PER_LOT_PER_USD = 100.0


@dataclass
class PaperPosition:
    order_id: str
    side: str  # BUY | SELL
    volume: float
    entry_price: float
    sl: float
    tp: float
    opened_at: datetime
    strategy: str = "london_breakout"
    contract_size: float = XAUUSD_USD_PER_LOT_PER_USD  # unit per lot (XAU 100 oz, BTC 1)


@dataclass
class CloseEvent:
    reason: str  # SL | TP | TIME
    price: float
    profit: float
    closed_at: datetime


def unrealized(pos: PaperPosition, bid: float, ask: float) -> float:
    exit_price = bid if pos.side == "BUY" else ask
    return _pnl(pos, exit_price)


def _pnl(pos: PaperPosition, exit_price: float) -> float:
    diff = (exit_price - pos.entry_price) if pos.side == "BUY" else (pos.entry_price - exit_price)
    return round(diff * pos.contract_size * pos.volume, 2)


class PaperBroker:
    """Stateless calculator: callers own the position and persistence."""

    def __init__(self, force_close_hour_utc: int | None = 16):
        self.force_close_hour_utc = force_close_hour_utc

    def fill(self, intent, bid: float, ask: float, now: datetime) -> PaperPosition:
        """Market fill: BUY at ask, SELL at bid (zero slippage in paper mode)."""
        if intent.side not in ("BUY", "SELL"):
            raise ValueError(f"invalid side {intent.side!r}")
        if intent.sl is None or intent.tp is None:
            raise ValueError("SL and TP are mandatory")
        entry = ask if intent.side == "BUY" else bid
        return PaperPosition(
            order_id=getattr(intent, "order_id", "") or "",
            side=intent.side,
            volume=float(intent.volume),
            entry_price=entry,
            sl=float(intent.sl),
            tp=float(intent.tp),
            opened_at=now,
            strategy=getattr(intent, "strategy", "london_breakout"),
        )

    def on_price(self, pos: PaperPosition, bid: float, ask: float, now: datetime) -> CloseEvent | None:
        """Check SL / TP / time exit against one tick."""
        if self._time_exit_due(now):
            exit_price = bid if pos.side == "BUY" else ask
            return CloseEvent("TIME", exit_price, _pnl(pos, exit_price), now)
        if pos.side == "BUY":
            if bid <= pos.sl:
                return CloseEvent("SL", pos.sl, _pnl(pos, pos.sl), now)
            if bid >= pos.tp:
                return CloseEvent("TP", pos.tp, _pnl(pos, pos.tp), now)
        else:
            if ask >= pos.sl:
                return CloseEvent("SL", pos.sl, _pnl(pos, pos.sl), now)
            if ask <= pos.tp:
                return CloseEvent("TP", pos.tp, _pnl(pos, pos.tp), now)
        return None

    def on_bar(self, pos: PaperPosition, bar_open: float, bar_high: float, bar_low: float,
               bar_close: float, spread: float, now: datetime,
               slippage: float = 0.0) -> CloseEvent | None:
        """Conservative OHLC-bar exit check (backtest / replay).

        BUY exits on bid = price - spread/2; SELL exits on ask = price + spread/2.
        A gap through SL fills at the open; SL wins when a bar touches both levels.
        """
        half = spread / 2.0
        if self._time_exit_due(now):
            if pos.side == "BUY":
                exit_price = max(bar_close - half - slippage, 0.0)
            else:
                exit_price = bar_close + half + slippage
            return CloseEvent("TIME", round(exit_price, 2), _pnl(pos, exit_price), now)
        if pos.side == "BUY":
            if bar_open - half <= pos.sl:
                exit = max(bar_open - half - slippage, 0.0)
                return CloseEvent("SL", round(exit, 2), _pnl(pos, exit), now)
            if bar_low - half <= pos.sl:
                exit = max(pos.sl - slippage, 0.0)
                return CloseEvent("SL", round(exit, 2), _pnl(pos, exit), now)
            if bar_high - half >= pos.tp:
                exit = pos.tp - slippage
                return CloseEvent("TP", round(exit, 2), _pnl(pos, exit), now)
        else:
            if bar_open + half >= pos.sl:
                exit = bar_open + half + slippage
                return CloseEvent("SL", round(exit, 2), _pnl(pos, exit), now)
            if bar_high + half >= pos.sl:
                exit = pos.sl + slippage
                return CloseEvent("SL", round(exit, 2), _pnl(pos, exit), now)
            if bar_low + half <= pos.tp:
                exit = pos.tp + slippage
                return CloseEvent("TP", round(exit, 2), _pnl(pos, exit), now)
        return None

    def _time_exit_due(self, now: datetime) -> bool:
        if self.force_close_hour_utc is None:
            return False  # strategi 24/7 (BTC): tanpa time exit harian
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        now = now.astimezone(timezone.utc)
        return now.time() >= time(self.force_close_hour_utc, 0)
