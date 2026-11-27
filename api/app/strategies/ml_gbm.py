"""Strategy ML P3: LightGBM triple-barrier (t_f2p3a1). Track B (PRD 5.3).

Kontrak decide() identik dengan strategy #1/#2 (lihat strategies/README.md):
murni, tanpa I/O, tanpa jam, tanpa RNG. Model dilatih OFFLINE oleh
app/ml_walkforward.py; modul ini hanya mengimpor bundle model via
set_model_bundle() (runner) atau model_path (live, belum dipakai di kartu ini).

Guard identik dengan mean_reversion: fresh liquidity, filter spread
max(2 x median 15m, absolut), satu posisi, satu trade per hari, window entry
07:00-16:00 UTC, hari kerja, candle >= MIN_BARS. SL/TP = mult x ATR14;
volume = risk 0.5% / jarak SL (sama dengan baseline).

Prediksi bisa dipercepat runner via prime_prediction_cache(): cache di-key
(barrier_key, ts_iso bar terakhir) — nilai cache dihasilkan oleh jalur
komputasi fitur yang sama (compute_features), jadi paritas tetap.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import numpy as np

from ..ml_features import MIN_BARS, compute_features, feature_vector

STRATEGY_ID = "ml_gbm"
STRATEGY_NAME = "ML LightGBM triple-barrier"
STRATEGY_VERSION = "1.0.0"
TRACK = "B"  # ML (PRD 5.3)
CONTEXT_BARS = 300  # sama dengan CANDLE_LIMIT runner live

XAUUSD_USD_PER_LOT_PER_USD = 100.0

_MODEL: dict | None = None
_PRED_CACHE: dict[tuple, tuple[float, float]] = {}


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
    tf_seconds: int = 300  # M5
    sl_mult: float = 1.5   # SL = sl_mult x ATR14
    rr: float = 1.0        # TP = rr x SL (label barrier memakai nilai sama)
    threshold: float = 0.60  # ambang probabilitas menang
    entry_start_utc: int = 7
    entry_end_utc: int = 16
    force_close_utc: int = 16
    min_sl_distance_usd: float = 0.50
    max_sl_distance_usd: float = 15.00
    risk_per_trade: float = 0.005
    max_volume: float = 0.10
    min_volume: float = 0.01
    volume_step: float = 0.01
    usd_per_lot_per_usd: float = XAUUSD_USD_PER_LOT_PER_USD
    max_spread_abs: float = 0.50
    spread_median_multiplier: float = 2.0
    max_candle_age_s: float = 120.0
    max_liquidity_age_s: float = 120.0
    one_trade_per_day: bool = True
    min_bars: int = MIN_BARS


def set_model_bundle(bundle: dict | None) -> None:
    """bundle = {'long': {barrier_key: booster}, 'short': {...},
    'feature_names': [...]}. None = clear (dipakai test)."""
    global _MODEL
    _MODEL = bundle


def clear_prediction_cache() -> None:
    _PRED_CACHE.clear()


def prime_prediction_cache(rows: list[tuple]) -> None:
    """rows: (barrier_key, ts_iso, p_long, p_short) — dari batch predict runner."""
    for key, ts_iso, p_long, p_short in rows:
        _PRED_CACHE[(key, ts_iso)] = (float(p_long), float(p_short))


def barrier_key_of(params: StrategyParams) -> str:
    return f"sl{params.sl_mult:g}_rr{params.rr:g}"


def _parse_ts(value) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    ts = str(value).replace("Z", "+00:00")
    parsed = datetime.fromisoformat(ts)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _spread_threshold(liquidity: dict, risk: dict, p: StrategyParams) -> float:
    absolute = float(risk.get("max_spread", p.max_spread_abs))
    median = liquidity.get("spread_median_15m")
    if median is None:
        return absolute
    return max(p.spread_median_multiplier * float(median), absolute)


def _size_volume(sl_distance: float, risk: dict, p: StrategyParams) -> float | None:
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


def _predict(feats: dict, key: str, now: datetime, last_ts_iso: str) -> tuple[float, float] | None:
    cached = _PRED_CACHE.get((key, last_ts_iso))
    if cached is not None:
        return cached
    if _MODEL is None:
        return None
    vec = np.array([feature_vector(feats)], dtype=float)
    try:
        p_long = float(_MODEL["long"][key].predict(vec)[0])
        p_short = float(_MODEL["short"][key].predict(vec)[0])
    except KeyError:
        return None
    return p_long, p_short


def decide(context: dict, params: StrategyParams | None = None) -> OrderIntent | None:
    """BUY/SELL saat probabilitas menang > ambang, guard sama dengan baseline."""
    p = params or StrategyParams()
    now = _parse_ts(context["now"])
    if now.weekday() >= 5:
        return None
    candles = context.get("candles") or []
    if len(candles) < p.min_bars:
        return None
    last = candles[-1]
    last_close_ts = _parse_ts(last["ts"]) + timedelta(seconds=p.tf_seconds)
    if last_close_ts > now:
        return None
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
    if context.get("positions"):
        return None
    if p.one_trade_per_day and int(context.get("trades_today", 0)) >= 1:
        return None

    # window entry (bar terakhir, hari ini, UTC) — sama dengan mean_reversion
    last_ts = _parse_ts(last["ts"])
    last_minutes = last_ts.hour * 60 + last_ts.minute
    day = now.date()
    if not (day == last_ts.date()
            and p.entry_start_utc * 60 <= last_minutes < p.entry_end_utc * 60):
        return None

    feats = compute_features(
        candles, spread=float(spread),
        spread_median=liquidity.get("spread_median_15m"))
    atr = feats.get("atr_ratio")
    close = float(last["close"])
    if atr is None or not np.isfinite(atr):
        return None
    atr_abs = atr * close
    sl_dist = p.sl_mult * atr_abs
    if not (p.min_sl_distance_usd <= sl_dist <= p.max_sl_distance_usd):
        return None
    key = barrier_key_of(p)
    probs = _predict(feats, key, now, last_ts.isoformat())
    if probs is None:
        return None
    p_long, p_short = probs

    if p_long > p.threshold:
        side = "BUY"
        sl = close - sl_dist
        tp = close + p.rr * sl_dist
    elif p_short > p.threshold:
        side = "SELL"
        sl = close + sl_dist
        tp = close - p.rr * sl_dist
    else:
        return None
    volume = _size_volume(sl_dist, risk, p)
    if volume is None:
        return None
    return OrderIntent(
        symbol=context.get("symbol", "XAUUSD"),
        side=side,
        volume=volume,
        sl=round(sl, 2),
        tp=round(tp, 2),
        reason=(f"{side} ml_gbm {key}: p_long={p_long:.3f} p_short={p_short:.3f} "
                f"thr={p.threshold} atr={atr_abs:.2f} sl_dist={sl_dist:.2f}"),
        sl_distance=round(sl_dist, 2),
        risk_usd=round(float(risk.get("equity", 0.0))
                       * float(risk.get("risk_per_trade", p.risk_per_trade)), 2),
    )

