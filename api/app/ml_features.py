"""Feature engineering ML P3 (t_f2p3a1) — dipakai bersama training, backtest,
dan live decide() agar paritas sinyal terjaga (satu kode, satu konvensi).

Semua fitur point-in-time: dihitung hanya dari bar <= t (bar terakhir pada
``candles`` adalah bar yang baru saja CLOSE). Tick volume TIDAK dipakai karena
runner paper live mengirim ``volume: 0`` (paper/runner.py load_candles) —
fitur berbasis volume akan memecah paritas backtest vs paper.

Likuiditas dari: spread pada context (live: tick nyata; backtest: model sesi
CostModel), estimator Corwin-Schultz dari OHLC, dan kompresi range.
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

import numpy as np

MIN_BARS = 250  # lookback terdalam: ret_240/donchian 240 + margin

# Urutan fitur = urutan kolom model. Jangan ubah tanpa retrain.
FEATURE_NAMES = [
    "ret_1", "ret_6", "ret_12", "ret_48", "ret_120", "ret_240",
    "rv_12", "rv_48", "rv_120",
    "atr_ratio", "atr_rel",
    "sma20_dist", "sma50_dist", "sma200_dist",
    "rsi_14", "macd_norm", "donchian_pos",
    "body_ratio", "range_atr", "upper_wick_atr", "lower_wick_atr",
    "hour_sin", "hour_cos", "dow_sin", "dow_cos",
    "spread_usd", "spread_rel", "cs_spread_12", "range_comp_12",
]


def _candles_to_arrays(candles: list[dict]):
    close = np.array([float(c["close"]) for c in candles], dtype=float)
    high = np.array([float(c["high"]) for c in candles], dtype=float)
    low = np.array([float(c["low"]) for c in candles], dtype=float)
    op = np.array([float(c["open"]) for c in candles], dtype=float)
    return op, high, low, close


def atr_series(op, high, low, close) -> np.ndarray:
    """TR lalu rolling mean 14 (ATR sederhana, deterministik)."""
    n = len(close)
    tr = np.empty(n)
    tr[0] = high[0] - low[0]
    pc = close[:-1]
    tr[1:] = np.maximum(high[1:] - low[1:],
                        np.maximum(np.abs(high[1:] - pc), np.abs(low[1:] - pc)))
    if n < 14:
        return np.full(n, np.nan)
    atr = np.full(n, np.nan)
    csum = np.cumsum(tr)
    atr[13:] = (csum[13:] - np.concatenate(([0.0], csum[:-14]))) / 14.0
    return atr


def _rsi_wilder(closes: np.ndarray, period: int = 14) -> float:
    """RSI Wilder; seed = nilai perubahan pertama (konvensi ewm adjust=False,
    identik dengan jalur batch pandas — paritas batch/per-bar teruji)."""
    if len(closes) < period + 1:
        return np.nan
    delta = np.diff(closes)
    gain = np.clip(delta, 0.0, None)
    loss = np.clip(-delta, 0.0, None)
    alpha = 1.0 / period
    avg_g = float(gain[0])
    avg_l = float(loss[0])
    for i in range(1, len(delta)):
        avg_g = alpha * gain[i] + (1.0 - alpha) * avg_g
        avg_l = alpha * loss[i] + (1.0 - alpha) * avg_l
    if avg_l == 0:
        return 100.0
    rs = avg_g / avg_l
    return 100.0 - 100.0 / (1.0 + rs)


def _ema(values: np.ndarray, span: int) -> float:
    """EMA di-seed dengan nilai pertama window (konvensi tetap, sama di
    training dan serve karena keduanya memakai window 300 bar yang sama)."""
    alpha = 2.0 / (span + 1.0)
    out = float(values[0])
    for v in values[1:]:
        out = alpha * float(v) + (1.0 - alpha) * out
    return out


def _corwin_schultz_12(high: np.ndarray, low: np.ndarray, close: float) -> float:
    """Estimator spread Corwin-Schultz (2012) dari high-low 2 bar berurutan;
    median 12 estimasi terakhir, dinormalisasi close. Nilai negatif dipotong 0."""
    if len(high) < 13:
        return np.nan
    ests = []
    for i in range(len(high) - 12, len(high)):
        h1, l1, h2, l2 = high[i - 1], low[i - 1], high[i], low[i]
        if h1 <= 0 or l1 <= 0 or h2 <= 0 or l2 <= 0:
            continue
        beta = math.log(h1 / l1) ** 2 + math.log(h2 / l2) ** 2
        gamma = math.log(max(h1, h2) / min(l1, l2)) ** 2
        alpha = (math.sqrt(2 * beta) - math.sqrt(beta)) / 3 - math.sqrt(gamma / 25)
        s = 2 * (math.exp(alpha) - 1) / (math.exp(alpha) + 1)
        ests.append(max(s, 0.0))
    if not ests:
        return np.nan
    return float(np.median(ests)) / close


def compute_features(candles: list[dict], *, spread: float | None = None,
                     spread_median: float | None = None) -> dict:
    """Fitur untuk bar terakhir (baru saja close). candles ascending, tz-aware.

    spread/spread_median: dari context liquidity (opsional; backtest memakai
    spread sesi teramati CostModel). Fitur apa pun yang lookback-nya kurang
    -> NaN (LightGBM menangani NaN; decide() menolak candle < MIN_BARS).
    """
    names = FEATURE_NAMES
    nan = {k: np.nan for k in names}
    n = len(candles)
    if n < 2:
        return nan
    op, high, low, close = _candles_to_arrays(candles)
    last = candles[-1]
    ts = last["ts"]
    if isinstance(ts, str):
        ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    out = dict(nan)

    # returns log
    lc = np.log(close)
    for k, w in (("ret_1", 1), ("ret_6", 6), ("ret_12", 12), ("ret_48", 48),
                 ("ret_120", 120), ("ret_240", 240)):
        if n >= w + 1:
            out[k] = float(lc[-1] - lc[-1 - w])
    # realized vol (std ret_1, ddof=0)
    r1 = np.diff(lc)
    for k, w in (("rv_12", 12), ("rv_48", 48), ("rv_120", 120)):
        if len(r1) >= w:
            out[k] = float(np.std(r1[-w:]))
    # ATR
    atr = atr_series(op, high, low, close)
    atr_last = atr[-1]
    if not np.isnan(atr_last):
        out["atr_ratio"] = float(atr_last / close[-1])
        if n >= 134:
            tail = atr[-120:]
            if not np.isnan(tail).any():
                out["atr_rel"] = float(atr_last / np.median(tail))
    # SMA distance
    for k, w in (("sma20_dist", 20), ("sma50_dist", 50), ("sma200_dist", 200)):
        if n >= w:
            out[k] = float(close[-1] / close[-w:].mean() - 1.0)
    # RSI, MACD, Donchian
    out["rsi_14"] = _rsi_wilder(close, 14)
    if n >= 26 and not np.isnan(atr_last):
        macd = _ema(close, 12) - _ema(close, 26)
        out["macd_norm"] = float(macd / atr_last)
    if n >= 240:
        hi240 = float(high[-240:].max())
        lo240 = float(low[-240:].min())
        if hi240 > lo240:
            out["donchian_pos"] = float((close[-1] - lo240) / (hi240 - lo240))
    # candle shape bar terakhir
    rng = high[-1] - low[-1]
    if not np.isnan(atr_last) and atr_last > 0:
        out["range_atr"] = float(rng / atr_last)
        out["upper_wick_atr"] = float((high[-1] - max(op[-1], close[-1])) / atr_last)
        out["lower_wick_atr"] = float((min(op[-1], close[-1]) - low[-1]) / atr_last)
    if rng > 0:
        out["body_ratio"] = float((close[-1] - op[-1]) / rng)
    # waktu (UTC, siklik)
    out["hour_sin"] = math.sin(2 * math.pi * ts.hour / 24.0)
    out["hour_cos"] = math.cos(2 * math.pi * ts.hour / 24.0)
    out["dow_sin"] = math.sin(2 * math.pi * ts.weekday() / 7.0)
    out["dow_cos"] = math.cos(2 * math.pi * ts.weekday() / 7.0)
    # likuiditas: spread context + Corwin-Schultz + kompresi range
    if spread is not None:
        out["spread_usd"] = float(spread)
        out["spread_rel"] = float(spread / close[-1])
    out["cs_spread_12"] = _corwin_schultz_12(high, low, float(close[-1]))
    if not np.isnan(atr_last) and atr_last > 0 and n >= 12:
        out["range_comp_12"] = float((high[-12:] - low[-12:]).mean() / atr_last)
    # spread_median dipakai sebagai filter di decide(), bukan fitur model
    _ = spread_median
    return out


def feature_vector(feats: dict) -> list[float]:
    """Urutkan dict fitur jadi vektor sesuai FEATURE_NAMES (NaN tetap NaN)."""
    return [float(feats[k]) for k in FEATURE_NAMES]


def compute_features_batch(candles: list[dict], spread_fn=None) -> list[dict]:
    """Versi batch (pandas, C-speed) dari compute_features untuk SELURUH seri.

    Semantik identik dengan jalur per-bar (trailing window), diuji paritasnya
    di tests/test_ml_gbm.py::test_batch_matches_per_bar. spread_fn(ts_close)
    -> spread teramati (CostModel.filter_spread_at) seperti yang dilihat
    decide(); None -> fitur spread NaN.
    """
    import pandas as pd

    n = len(candles)
    nan_row = {k: np.nan for k in FEATURE_NAMES}
    if n < 2:
        return [dict(nan_row, ts=c["ts"]) for c in candles]
    ts = [c["ts"] if isinstance(c["ts"], datetime)
          else datetime.fromisoformat(str(c["ts"]).replace("Z", "+00:00"))
          for c in candles]
    idx = pd.DatetimeIndex(ts)
    close = pd.Series([float(c["close"]) for c in candles], index=idx)
    high = pd.Series([float(c["high"]) for c in candles], index=idx)
    low = pd.Series([float(c["low"]) for c in candles], index=idx)
    op = pd.Series([float(c["open"]) for c in candles], index=idx)
    f = {}
    lc = np.log(close)
    f["ret_1"] = lc.diff(1)
    f["ret_6"] = lc.diff(6)
    f["ret_12"] = lc.diff(12)
    f["ret_48"] = lc.diff(48)
    f["ret_120"] = lc.diff(120)
    f["ret_240"] = lc.diff(240)
    r1 = lc.diff(1)
    f["rv_12"] = r1.rolling(12, min_periods=12).std(ddof=0)
    f["rv_48"] = r1.rolling(48, min_periods=48).std(ddof=0)
    f["rv_120"] = r1.rolling(120, min_periods=120).std(ddof=0)
    pc = close.shift(1)
    tr = pd.concat([high - low, (high - pc).abs(), (low - pc).abs()], axis=1).max(axis=1)
    tr.iloc[0] = high.iloc[0] - low.iloc[0]
    atr = tr.rolling(14, min_periods=14).mean()
    f["atr_ratio"] = atr / close
    f["atr_rel"] = atr / atr.rolling(120, min_periods=120).median()
    for w in (20, 50, 200):
        f[f"sma{w}_dist"] = close / close.rolling(w, min_periods=w).mean() - 1.0
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)
    ag = gain.ewm(alpha=1 / 14, adjust=False).mean()
    al = loss.ewm(alpha=1 / 14, adjust=False).mean()
    rsi = 100.0 - 100.0 / (1.0 + ag / al)
    rsi = rsi.where(delta.notna())
    f["rsi_14"] = rsi
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    f["macd_norm"] = (ema12 - ema26) / atr
    hi240 = high.rolling(240, min_periods=240).max()
    lo240 = low.rolling(240, min_periods=240).min()
    f["donchian_pos"] = (close - lo240) / (hi240 - lo240)
    rng = high - low
    f["body_ratio"] = (close - op) / rng
    f["range_atr"] = rng / atr
    f["upper_wick_atr"] = (high - pd.concat([op, close], axis=1).max(axis=1)) / atr
    f["lower_wick_atr"] = (pd.concat([op, close], axis=1).min(axis=1) - low) / atr
    hours = pd.Series([t.hour for t in ts], index=idx, dtype=float)
    dows = pd.Series([t.weekday() for t in ts], index=idx, dtype=float)
    f["hour_sin"] = np.sin(2 * np.pi * hours / 24.0)
    f["hour_cos"] = np.cos(2 * np.pi * hours / 24.0)
    f["dow_sin"] = np.sin(2 * np.pi * dows / 7.0)
    f["dow_cos"] = np.cos(2 * np.pi * dows / 7.0)
    if spread_fn is not None:
        sp = pd.Series([spread_fn(t + timedelta(seconds=300)) for t in ts], index=idx)
        f["spread_usd"] = sp
        f["spread_rel"] = sp / close
    h1, l1 = high.shift(1), low.shift(1)
    with np.errstate(divide="ignore", invalid="ignore"):
        beta = np.log(high / low) ** 2 + np.log(h1 / l1) ** 2
        gamma = np.log(pd.concat([h1, high], axis=1).max(axis=1)
                       / pd.concat([l1, low], axis=1).min(axis=1)) ** 2
    alpha_cs = (np.sqrt(2 * beta) - np.sqrt(beta)) / 3 - np.sqrt(gamma / 25)
    cs = 2 * (np.exp(alpha_cs) - 1) / (np.exp(alpha_cs) + 1)
    f["cs_spread_12"] = cs.clip(lower=0.0).rolling(12, min_periods=12).median() / close
    f["range_comp_12"] = rng.rolling(12, min_periods=12).mean() / atr
    frame = pd.DataFrame(f, columns=FEATURE_NAMES)
    out = []
    vals = frame.to_numpy(dtype=float)
    for i, c in enumerate(candles):
        row = dict(nan_row)
        row["ts"] = c["ts"]
        for j, k in enumerate(FEATURE_NAMES):
            v = vals[i, j]
            if v == v:  # bukan NaN
                row[k] = float(v)
        out.append(row)
    return out


