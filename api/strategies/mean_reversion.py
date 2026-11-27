"""Strategy #2: Bollinger mean reversion, re-entry trigger (Fund2 PRD P2).

Pure decide(): no I/O, no clock, no RNG. The caller supplies everything in
``context``; the same function is used by the paper runner and the backtest
(signal parity by construction). Format identical to strategy #1
(strategies/london_breakout.py).

Contract (see strategies/mean_reversion/SKILL.md; format: strategies/README.md):

    context = {
        "symbol": "XAUUSD",
        "now": "2026-11-23T08:05:00+00:00",          # true UTC, ISO8601
        "candles": [ {\"ts\": iso, \"open\", \"high\", \"low\", \"close\", \"volume\"},
                     ... ],                           # CLOSED bars, ascending, ts UTC
        \"liquidity\": {\"ts\": iso, \"bid\", \"ask\", \"spread\", \"spread_median_15m\",
                      \"fresh\": bool},
        \"positions\": [ {...} ],                       # OPEN positions, read-only
        \"trades_today\": 0,                            # entries opened today
        \"risk\": {\"equity\", \"risk_per_trade\", \"max_volume\", \"max_spread\"},
    }

    decide(context) -> OrderIntent | None

Entry logic: price pierces the Bollinger band (SMA20 +/- 2.5 sigma) and
re-enters the band -> trade back toward the mean. SL beyond the recent swing,
TP at the SMA. Same risk gates, spread filter and staleness guards as
strategy #1.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

STRATEGY_ID = "mean_reversion"
STRATEGY_NAME = "Mean Reversion (Bollinger re-entry)"
STRATEGY_VERSION = "1.0.0"
TRACK = "A"  # rule-based (Bollinger re-entry); Track B = ML, C = RL (PRD 5.3)

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
    period: int = 20  # SMA / sigma window (closed bars)
    num_std: float = 2.5  # band width in sigma
    entry_start_utc: int = 7  # 07:00 UTC (London open)
    entry_end_utc: int = 16  # 16:00 UTC (NY morning close)
    force_close_utc: int = 16  # engine-enforced time exit (E1), same as #1
    min_sd_usd: float = 0.50  # dead-market guard
    max_sd_usd: float = 30.00  # sanity cap (news spike)
    reentry_buffer_usd: float = 0.10  # prior close must pierce beyond band + buffer
    sl_lookback: int = 2  # bars for the swing stop: pierce bar + trigger bar
    sl_buffer_usd: float = 0.10  # stop beyond the swing extreme
    min_rr: float = 0.6  # (TP - entry) / SL distance floor
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


def _bands(closes: list[float]) -> tuple[float, float]:
    """Population mean and sigma over the window (deterministic)."""
    n = len(closes)
    mean = sum(closes) / n
    variance = sum((c - mean) ** 2 for c in closes) / n
    return mean, math.sqrt(variance)


# ---------------------------------------------------------------- decide


def decide(context: dict, params: StrategyParams | None = None) -> OrderIntent | None:
    """Return an OrderIntent when a band re-entry fires, else None.

    Entry: M5 close pierces the Bollinger band (SMA +/- num_std x sigma over
    the last ``period`` closed bars) and the next close re-enters the band,
    inside the entry window (07:00-16:00 UTC). SL beyond the low/high of the
    last ``sl_lookback`` bars (pierce + trigger), TP at the SMA. Spread filter
    and staleness guards per PRD 5.2. Read-only over context.
    """
    p = params or StrategyParams()
    now = _parse_ts(context["now"])
    if now.weekday() >= 5:  # weekend: market closed
        return None

    candles = _candle_list(context.get("candles") or [])
    if len(candles) < max(p.period, 2):
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

    # trigger bar: last closed candle inside the entry window, today (UTC)
    day = now.date()
    last_minutes = last["ts"].hour * 60 + last["ts"].minute
    if not (
        day == last["ts"].date()
        and p.entry_start_utc * 60 <= last_minutes < p.entry_end_utc * 60
    ):
        return None

    window = candles[-p.period:]
    mean, sd = _bands([c["close"] for c in window])
    if sd < p.min_sd_usd or sd > p.max_sd_usd:
        return None
    lower = mean - p.num_std * sd
    upper = mean + p.num_std * sd
    buffer = p.reentry_buffer_usd

    if prev["close"] <= lower - buffer and last["close"] >= lower:
        side, ref = "BUY", last["close"]
        swing = min(c["low"] for c in candles[-p.sl_lookback:])
        sl = swing - p.sl_buffer_usd
        if ref - sl < p.min_sl_distance_usd:
            sl = ref - p.min_sl_distance_usd
    elif prev["close"] >= upper + buffer and last["close"] <= upper:
        side, ref = "SELL", last["close"]
        swing = max(c["high"] for c in candles[-p.sl_lookback:])
        sl = swing + p.sl_buffer_usd
        if sl - ref < p.min_sl_distance_usd:
            sl = ref + p.min_sl_distance_usd
    else:
        return None

    sl_distance = (ref - sl) if side == "BUY" else (sl - ref)
    if sl_distance < p.min_sl_distance_usd - 1e-9 or sl_distance > p.max_sl_distance_usd:
        return None  # SL would violate the risk gate distance bounds
    tp = mean  # target: reversion to the mean
    if side == "BUY" and tp <= ref:
        return None  # mean already behind us, no room to revert
    if side == "SELL" and tp >= ref:
        return None
    rr = (tp - ref) / sl_distance if side == "BUY" else (ref - tp) / sl_distance
    if rr < p.min_rr:
        return None  # target too close to justify the stop

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
            f"{side} mean reversion: close {ref:.2f} re-entered band "
            f"[{lower:.2f}, {upper:.2f}] (SMA {mean:.2f}, sigma {sd:.2f}), "
            f"spread {float(spread):.2f}, SL dist {sl_distance:.2f}, RR {rr:.2f}"
        ),
        sl_distance=round(sl_distance, 2),
        risk_usd=round(float(risk.get("equity", 0.0)) * float(risk.get("risk_per_trade", p.risk_per_trade)), 2),
    )
