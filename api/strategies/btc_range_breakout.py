"""Strategy #3: BTCUSD 24/7 range breakout + filter volatilitas (PRD 5.3, P2 multipair).

Pure decide(): no I/O, no clock, no RNG. The caller supplies everything in
``context``; the same function is used by the paper runner and the backtest
(signal parity by construction). Format identical to strategies #1/#2
(strategies/README.md).

Contract (see strategies/btc_range_breakout/SKILL.md; format: strategies/README.md):

    context = {
        "symbol": "BTCUSD",
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

Entry logic: close menembus channel Donchian `range_lookback` bar H1
(excluding bar pemicu) dengan buffer, breakout PERTAMA (close sebelumnya
masih di dalam channel), setelah lolos filter volatilitas ATR. Crypto jalan
terus: guard weekend tidak berlaku (reject_weekend=False) dan tanpa time
exit harian (force_close_utc=None) - posisi ditutup SL/TP oleh broker kertas.
SL = atr_sl_mult x ATR(14) (struktur volatilitas, bukan sisi berlawanan
channel yang bisa melebihi batas risk gate), TP = rr x jarak SL.

BTCUSD contract (t_f2mp1, verifikasi 8 deal live 22 Nov): 1.0 lot = 1 BTC,
jadi pergerakan harga 1.00 USD = 1 USD/lot. SL distance gate per-simbol:
[100, 1000] USD (A2 BTCUSD; floor 100 juga di atas stops level broker ~50).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

STRATEGY_ID = "btc_range_breakout"
STRATEGY_NAME = "BTC Range Breakout 24/7"
STRATEGY_VERSION = "1.0.0"
TRACK = "A"  # A=rule-based | B=ML | C=RL (PRD 5.3)

# BTCUSD contract (t_f2mp1): 1.0 lot = 1 BTC -> 1.00 USD price move = 1 USD/lot.
BTCUSD_USD_PER_LOT_PER_USD = 1.0

# Sejarah lintas hari yang dibutuhkan decide() (Donchian 24 bar + ATR 14 +
# prev bar + margin) -> engine backtest & runner memberikan rolling window
# ini, bukan hanya candle hari berjalan (strategi #1/#2 cukup harian).
CONTEXT_BARS = 64


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

    tf_seconds: int = 3600  # H1: sejarah BTC terpanjang yang tersedia (Apr 2026)
    # ---- logika entry ----
    range_lookback: int = 24  # channel Donchian 24 bar H1 (1 hari)
    breakout_buffer_usd: float = 50.0  # close harus melewati channel + buffer
    atr_period: int = 14  # ATR filter volatilitas + dasar SL
    atr_min_usd: float = 150.0  # pasar mati: ATR di bawah ini tidak entry
    atr_max_usd: float = 900.0  # volatilitas ekstrem: tidak entry
    atr_sl_mult: float = 1.5  # SL = atr_sl_mult x ATR
    rr: float = 1.5  # TP = rr x jarak SL
    max_trades_per_day: int = 1
    # ---- guard standar (adaptasi BTC 24/7, lihat SKILL.md) ----
    reject_weekend: bool = False  # crypto jalan terus: weekend TIDAK ditolak
    force_close_utc: int | None = None  # tanpa time exit harian (E1 XAU tidak berlaku)
    min_sl_distance_usd: float = 100.0  # A2 BTCUSD (floor > stops level broker ~50)
    max_sl_distance_usd: float = 1000.0  # A2 BTCUSD
    risk_per_trade: float = 0.005  # fallback when context risk omits it
    max_volume: float = 0.10  # PRD 5.6 hard cap per order
    min_volume: float = 0.01
    volume_step: float = 0.01
    usd_per_lot_per_usd: float = BTCUSD_USD_PER_LOT_PER_USD
    max_spread_abs: float = 100.0  # A9 BTCUSD (fallback absolute threshold)
    spread_median_multiplier: float = 2.0  # PRD 5.2: max(2 x median 15m, abs)
    max_candle_age_s: float = 120.0  # age measured from bar CLOSE
    max_liquidity_age_s: float = 120.0


# ---------------------------------------------------------------- helpers
# Guard standar: sama dengan strategi lain, kecuali weekend (BTC 24/7).


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
    """Risk-based volume: equity x risk% / (SL distance x USD-per-lot-per-USd).

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


def _atr(candles: list[dict], period: int) -> float | None:
    """Rata-rata true range `period` bar closed terakhir (bar pemicu termasuk).

    TR = max(high-low, |high-prev_close|, |low-prev_close|). Butuh
    period+1 bar (bar pertama dipakai sebagai prev_close).
    """
    if len(candles) < period + 1:
        return None
    trs = []
    for i in range(-period, 0):
        high, low = candles[i]["high"], candles[i]["low"]
        prev_close = candles[i - 1]["close"]
        trs.append(max(high - low, abs(high - prev_close), abs(low - prev_close)))
    return sum(trs) / len(trs)


def _standard_guards(context: dict, p: StrategyParams) -> tuple[datetime, list[dict], dict] | None:
    """Guards wajib PRD 5.2/5.6. Return (now, candles, risk) or None = no entry.

    Weekend (hanya bila reject_weekend - BTC 24/7 default lewat), bar belum
    closed/basi, likuiditas basi/tidak fresh, spread filter, posisi terbuka,
    batas trade harian. Entry logic harus memanggil ini dulu.
    """
    now = _parse_ts(context["now"])
    if p.reject_weekend and now.weekday() >= 5:
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
    """Return an OrderIntent when the 24/7 range breakout fires, else None.

    Entry: close bar H1 terakhir menembus channel Donchian `range_lookback`
    bar sebelumnya (breakout pertama) dengan buffer, setelah filter
    volatilitas ATR. SL = atr_sl_mult x ATR, TP = rr x jarak SL. Read-only
    over context.
    """
    p = params or StrategyParams()
    guarded = _standard_guards(context, p)
    if guarded is None:
        return None
    now, candles, risk = guarded

    need = p.range_lookback + p.atr_period + 2
    if len(candles) < need:
        return None
    last, prev = candles[-1], candles[-2]

    atr = _atr(candles, p.atr_period)
    if atr is None:
        return None
    if atr < p.atr_min_usd or atr > p.atr_max_usd:
        return None  # filter volatilitas: pasar mati atau ekstrem

    # channel Donchian `range_lookback` bar SEBELUM bar pemicu
    window = candles[-(p.range_lookback + 1):-1]
    range_high = max(c["high"] for c in window)
    range_low = min(c["low"] for c in window)
    buffer = p.breakout_buffer_usd

    if last["close"] > range_high + buffer and prev["close"] <= range_high:
        side, ref = "BUY", last["close"]
        sl = ref - p.atr_sl_mult * atr
    elif last["close"] < range_low - buffer and prev["close"] >= range_low:
        side, ref = "SELL", last["close"]
        sl = ref + p.atr_sl_mult * atr
    else:
        return None

    sl_distance = (ref - sl) if side == "BUY" else (sl - ref)
    if sl_distance < p.min_sl_distance_usd - 1e-9 or sl_distance > p.max_sl_distance_usd:
        return None  # SL would violate the per-symbol risk gate distance bounds
    tp = ref + p.rr * sl_distance if side == "BUY" else ref - p.rr * sl_distance

    volume = _size_volume(sl_distance, risk, p)
    if volume is None:
        return None

    return OrderIntent(
        symbol=context.get("symbol", "BTCUSD"),
        side=side,
        volume=volume,
        sl=round(sl, 2),
        tp=round(tp, 2),
        reason=(
            f"{side} BTC range breakout: close {ref:.2f} beyond {p.range_lookback}-bar "
            f"channel [{range_low:.2f}, {range_high:.2f}] +{buffer:.2f} buffer, "
            f"ATR{p.atr_period} {atr:.2f}, spread {float(context.get('liquidity', {}).get('spread') or 0):.2f}, "
            f"SL dist {sl_distance:.2f}"
        ),
        sl_distance=round(sl_distance, 2),
        risk_usd=round(float(risk.get("equity", 0.0)) * float(risk.get("risk_per_trade", p.risk_per_trade)), 2),
    )
