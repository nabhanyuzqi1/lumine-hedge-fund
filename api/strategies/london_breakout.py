"""Strategy #1: London session breakout + spread filter (Fund2 PRD 5.3).

Pure decide(): no I/O, no clock, no RNG. The caller supplies everything in
``context``; the same function is used by the paper runner and the backtest
(signal parity by construction).

Contract (see strategies/london_breakout/SKILL.md; format: strategies/README.md):

    context = {
        "symbol": "XAUUSD",
        "now": "2026-11-23T08:05:00+00:00",          # true UTC, ISO8601
        "candles": [ {"ts": iso, "open", "high", "low", "close", "volume"},
                     ... ],                           # CLOSED bars, ascending, ts UTC
        "liquidity": {"ts": iso, "bid", "ask", "spread", "spread_median_15m",
                      "fresh": bool},
        "positions": [ {...} ],                       # OPEN positions, read-only
        "trades_today": 0,                            # entries opened today
        "risk": {"equity", "risk_per_trade", "max_volume", "max_spread"},
    }

    decide(context) -> OrderIntent | None
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

STRATEGY_ID = "london_breakout"
STRATEGY_NAME = "London Breakout + Spread Filter"
STRATEGY_VERSION = "1.0.0"
TRACK = "A"

# XAUUSD contract: 1.0 lot = 100 oz, so a 1.00 USD price move = 100 USD/lot.
XAUUSD_USD_PER_LOT_PER_USD = 100.0


@dataclass(frozen=True)
class OrderIntent:
    """One order proposal. SL and TP are mandatory (risk gate rejects otherwise)."""

    symbol: str
    side: str  # BUY | SELL
    volume: float  # lots
    sl: float
    tp: float
    strategy: str = STRATEGY_ID
    reason: str = ""
    sl_distance: float = 0.0
    risk_usd: float = 0.0


@dataclass(frozen=True)
class StrategyParams:
    """Strategy tunables. Owner-tunable via settings; defaults documented in SKILL.md."""

    tf_seconds: int = 300  # M5
    asia_start_utc: int = 0  # 00:00 UTC
    asia_end_utc: int = 7  # 07:00 UTC
    london_start_utc: int = 7  # 07:00 UTC
    london_end_utc: int = 12  # 12:00 UTC
    force_close_utc: int = 16  # engine-enforced time exit (E1)
    min_asia_coverage: float = 0.6  # fraction of Asia window that must have bars
    min_range_usd: float = 0.50  # dead-market guard
    max_range_usd: float = 150.00  # sanity cap (observed p-max ~112 in 2026 data)
    breakout_buffer_usd: float = 0.10
    rr: float = 1.5  # TP = rr x SL distance
    min_sl_distance_usd: float = 0.50  # == risk gate min SL distance
    max_sl_distance_usd: float = 15.00  # == risk gate max SL distance
    risk_per_trade: float = 0.005  # fallback when context risk omits it
    max_volume: float = 0.10  # PRD 5.6 hard cap per order
    min_volume: float = 0.01
    volume_step: float = 0.01
    usd_per_lot_per_usd: float = XAUUSD_USD_PER_LOT_PER_USD
    max_spread_abs: float = 0.50  # fallback absolute threshold
    spread_median_multiplier: float = 2.0  # PRD 5.2: max(2 x median 15m, abs)
    max_candle_age_s: float = 120.0  # age measured from bar CLOSE
    max_liquidity_age_s: float = 120.0
    one_trade_per_day: bool = True


# ---------------------------------------------------------------- helpers


def _parse_ts(value) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    ts = str(value).replace("Z", "+00:00")
    parsed = datetime.fromisoformat(ts)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _candle_list(context: list[dict]) -> list[dict]:
    """Parse candles into shallow copies with tz-aware UTC datetimes."""
    out = []
    for c in context:
        out.append(
            {
                "ts": _parse_ts(c["ts"]),
                "open": float(c["open"]),
                "high": float(c["high"]),
                "low": float(c["low"]),
                "close": float(c["close"]),
            }
        )
    return out


def _spread_threshold(liquidity: dict, risk: dict, p: StrategyParams) -> float:
    """PRD 5.2: reject when spread > max(2 x median 15m, absolute threshold)."""
    absolute = float(risk.get("max_spread", p.max_spread_abs))
    median = liquidity.get("spread_median_15m")
    if median is None:
        return absolute
    return max(p.spread_median_multiplier * float(median), absolute)


def _size_volume(sl_distance: float, risk: dict, p: StrategyParams) -> float | None:
    """Risk-based volume: equity x risk% / (SL distance x USD-per-lot-per-USD).

    Floored to the volume step, capped by the hard max and the settings max.
    Returns None when the risk budget cannot buy the minimum volume.
    """
    equity = float(risk.get("equity", 0.0))
    risk_pct = float(risk.get("risk_per_trade", p.risk_per_trade))
    risk_usd = equity * risk_pct
    raw = risk_usd / (sl_distance * p.usd_per_lot_per_usd)
    step = p.volume_step
    volume = math.floor(raw / step + 1e-9) * step
    cap = min(p.max_volume, float(risk.get("max_volume", p.max_volume)))
    volume = min(volume, cap)
    volume = round(volume, 2)
    if volume < p.min_volume:
        return None
    return volume


# ---------------------------------------------------------------- decide


def decide(context: dict, params: StrategyParams | None = None) -> OrderIntent | None:
    """Return an OrderIntent for the first London breakout of the day, else None.

    Entry: M5 close crosses the Asia range (00:00-07:00 UTC) during the London
    window (07:00-12:00 UTC), previous close still inside the range.
    SL: opposite side of the Asia range. TP: rr x range. Spread filter and
    staleness guards per PRD 5.2. Read-only over context.
    """
    p = params or StrategyParams()
    now = _parse_ts(context["now"])
    if now.weekday() >= 5:  # weekend: market closed
        return None

    candles = _candle_list(context.get("candles") or [])
    if len(candles) < 2:
        return None
    last, prev = candles[-1], candles[-2]

    # stale candles: age measured from bar close (ts + tf)
    last_close_ts = last["ts"] + timedelta(seconds=p.tf_seconds)
    if last_close_ts > now:
        return None  # bar not closed yet
    if (now - last_close_ts).total_seconds() > p.max_candle_age_s:
        return None

    liquidity = context.get("liquidity") or {}
    if not liquidity.get("fresh"):
        return None
    liq_ts = liquidity.get("ts")
    if liq_ts is None or (now - _parse_ts(liq_ts)).total_seconds() > p.max_liquidity_age_s:
        return None
    risk = context.get("risk") or {}
    spread = liquidity.get("spread")
    if spread is None or float(spread) > _spread_threshold(liquidity, risk, p):
        return None

    # one position at a time, one trade per day
    if context.get("positions"):
        return None
    if p.one_trade_per_day and int(context.get("trades_today", 0)) >= 1:
        return None

    # Asia range for "today" (UTC)
    day = now.date()
    asia = [
        c
        for c in candles
        if c["ts"].date() == day
        and p.asia_start_utc <= c["ts"].hour + c["ts"].minute / 60 < p.asia_end_utc
    ]
    expected_bars = (p.asia_end_utc - p.asia_start_utc) * 3600 / p.tf_seconds
    if len(asia) < math.ceil(expected_bars * p.min_asia_coverage):
        return None
    asia_high = max(c["high"] for c in asia)
    asia_low = min(c["low"] for c in asia)
    rng = asia_high - asia_low
    if rng < p.min_range_usd or rng > p.max_range_usd:
        return None

    # trigger: last closed candle inside the London window, first breakout
    last_minutes = last["ts"].hour * 60 + last["ts"].minute
    if not (
        day == last["ts"].date()
        and p.london_start_utc * 60 <= last_minutes < p.london_end_utc * 60
    ):
        return None
    buffer = p.breakout_buffer_usd
    if last["close"] > asia_high + buffer and prev["close"] <= asia_high:
        side, ref = "BUY", last["close"]
        # SL below the breakout candle (structure stop), clamped to the gate bounds
        sl = last["low"]
        if ref - sl < p.min_sl_distance_usd:
            sl = ref - p.min_sl_distance_usd
    elif last["close"] < asia_low - buffer and prev["close"] >= asia_low:
        side, ref = "SELL", last["close"]
        sl = last["high"]
        if sl - ref < p.min_sl_distance_usd:
            sl = ref + p.min_sl_distance_usd
    else:
        return None

    sl_distance = (ref - sl) if side == "BUY" else (sl - ref)
    if sl_distance < p.min_sl_distance_usd - 1e-9 or sl_distance > p.max_sl_distance_usd:
        return None  # SL would violate the risk gate distance bounds
    tp = ref + p.rr * sl_distance if side == "BUY" else ref - p.rr * sl_distance

    volume = _size_volume(sl_distance, risk, p)
    if volume is None:
        return None

    return OrderIntent(
        symbol=context.get("symbol", "XAUUSD"),
        side=side,
        volume=volume,
        sl=round(sl, 2),
        tp=round(tp, 2),
        reason=(
            f"{side} London breakout: close {ref:.2f} beyond Asia range "
            f"[{asia_low:.2f}, {asia_high:.2f}], range {rng:.2f}, "
            f"spread {float(spread):.2f}, SL dist {sl_distance:.2f}"
        ),
        sl_distance=round(sl_distance, 2),
        risk_usd=round(float(risk.get("equity", 0.0)) * float(risk.get("risk_per_trade", p.risk_per_trade)), 2),
    )
