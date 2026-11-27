"""Strategy template (Fund2 PRD 5.3): copy me, replace every TODO.

Pure decide(): no I/O, no clock, no RNG. The caller supplies everything in
``context``; the same function is used by the paper runner and the backtest
(signal parity by construction). Context is READ-ONLY: never mutate it.

Contract (see strategies/README.md; fill SKILL.md next to this module):

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

# TODO: ganti identity tripla ini (snake_case id, dipakai sebagai strategy_id
# di DB, settings key, state key paper runner, dan nama direktori skill).
STRATEGY_ID = "template"
STRATEGY_NAME = "Template Strategy"
STRATEGY_VERSION = "0.1.0"
TRACK = "A"  # A=rule-based | B=ML | C=RL (PRD 5.3)

# XAUUSD contract: 1.0 lot = 100 oz, so a 1.00 USD price move = 100 USD/lot.
# TODO: sesuaikan untuk simbol lain (BTCUSD: 1.0 lot = 1 BTC).
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
    # TODO: parameter spesifik strategi di sini (window, buffer, rr, ...).

    # ---- guard standar (jangan diubah tanpa alasan; sama dengan strategi lain
    # agar perbandingan apples-to-apples) ----
    force_close_utc: int = 16  # engine-enforced time exit (E1)
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
    max_trades_per_day: int = 1


# ---------------------------------------------------------------- helpers
# Guard standar: salin apa adanya dari strategi lain / template ini.


def _parse_ts(value) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    ts = str(value).replace("Z", "+00:00")
    parsed = datetime.fromisoformat(ts)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _candle_list(context: list[dict]) -> list[dict]:
    """Parse candles into NEW shallow copies with tz-aware UTC datetimes.

    Never sort/mutate the caller's list: build a new one (context is
    immutable per decide() call; see strategies/README.md).
    """
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


def _standard_guards(context: dict, p: StrategyParams) -> tuple[datetime, list[dict], dict] | None:
    """Guards wajib PRD 5.2/5.6. Return (now, candles, risk) or None = no entry.

    Weekend, unclosed/stale candle, stale/unfresh liquidity, spread filter,
    open position, daily trade cap. Entry logic harus memanggil ini dulu.
    """
    now = _parse_ts(context["now"])
    if now.weekday() >= 5:  # weekend: market closed
        return None

    candles = _candle_list(context.get("candles") or [])
    if not candles:
        return None
    last = candles[-1]

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

    # one position at a time, daily cap
    if context.get("positions"):
        return None
    if int(context.get("trades_today", 0)) >= p.max_trades_per_day:
        return None

    return now, candles, risk


# ---------------------------------------------------------------- decide


def decide(context: dict, params: StrategyParams | None = None) -> OrderIntent | None:
    """Return an OrderIntent when the entry fires, else None.

    TODO: tulis logika entry di bawah, murni fungsi dari (context, params).
    Pola: _standard_guards() -> hitung sinyal dari candles -> tentukan
    side/ref/sl -> validasi SL distance -> TP -> sizing -> OrderIntent.
    """
    p = params or StrategyParams()
    guarded = _standard_guards(context, p)
    if guarded is None:
        return None
    now, candles, risk = guarded

    # TODO: logika entry di sini. Contoh kerangka (hapus/timpa):
    #   if <syarat entry BUY>:
    #       side, ref, sl = "BUY", close, <structur stop>
    #   elif <syarat entry SELL>:
    #       side, ref, sl = "SELL", close, <structure stop>
    #   else:
    #       return None
    #
    #   sl_distance = (ref - sl) if side == "BUY" else (sl - ref)
    #   if sl_distance < p.min_sl_distance_usd - 1e-9 or sl_distance > p.max_sl_distance_usd:
    #       return None  # SL would violate the risk gate distance bounds
    #   tp = ref + p.rr * sl_distance if side == "BUY" else ref - p.rr * sl_distance
    #   volume = _size_volume(sl_distance, risk, p)
    #   if volume is None:
    #       return None
    #   return OrderIntent(
    #       symbol=context.get("symbol", "XAUUSD"),
    #       side=side, volume=volume, sl=round(sl, 2), tp=round(tp, 2),
    #       reason=f"... deterministik, untuk audit ...",
    #       sl_distance=round(sl_distance, 2),
    #       risk_usd=round(float(risk.get("equity", 0.0)) *
    #                      float(risk.get("risk_per_trade", p.risk_per_trade)), 2),
    #   )
    return None  # TODO: ganti dengan logika entry.
