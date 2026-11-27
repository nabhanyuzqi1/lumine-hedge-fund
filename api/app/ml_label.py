"""Label triple-barrier per sisi untuk training ML P3 (t_f2p3a1).

Dari close bar entry t (bar 07:00-16:00 UTC, hari kerja): SL = sl_mult x
ATR14(t), TP = rr x SL, horizon sampai force-close 16:00 UTC hari yang sama.
Bar yang menyentuh SL dan TP sekaligus dihitung SL lebih dulu (konservatif,
sama dengan PaperBroker.on_bar). Timeout -> label dari tanda close_1600 -
entry (long) / entry - close_1600 (short).

Bar tanpa horizon minimal (entry terlalu sore) dan bar dengan jarak SL di
luar batas risk gate (0.5-15 USD) dibuang: tidak pernah jadi trade nyata.
"""
from __future__ import annotations

from datetime import datetime, timezone

import numpy as np

from .ml_features import atr_series

# (sl_mult, rr): 4 konfigurasi barrier x 3 threshold = grid 12 kombinasi
BARRIER_CONFIGS = [(1.0, 1.0), (1.0, 1.5), (1.5, 1.0), (1.5, 1.5)]

ENTRY_START_UTC = 7
ENTRY_END_UTC = 16
FORCE_CLOSE_UTC = 16
MIN_HORIZON_BARS = 3
MIN_SL_DIST_USD = 0.50   # == risk gate min SL distance
MAX_SL_DIST_USD = 15.00  # == risk gate max SL distance


def barrier_key(sl_mult: float, rr: float) -> str:
    return f"sl{sl_mult:g}_rr{rr:g}"


def _minutes(ts: datetime) -> int:
    return ts.hour * 60 + ts.minute


def triple_barrier_labels(candles: list[dict], sl_mult: float, rr: float, *,
                          entry_start_utc: int = ENTRY_START_UTC,
                          entry_end_utc: int = ENTRY_END_UTC,
                          force_close_utc: int = FORCE_CLOSE_UTC,
                          min_horizon_bars: int = MIN_HORIZON_BARS,
                          min_sl_dist: float = MIN_SL_DIST_USD,
                          max_sl_dist: float = MAX_SL_DIST_USD) -> list[dict]:
    """Label per bar entry pada candles (slice window latih, bar hari penuh).

    Return list dict: {ts, close, atr, sl_dist, tp_dist, horizon, label_long,
    label_short}. candles: ascending, ts tz-aware UTC, bar terakhir close.
    """
    op, high, low, close = [], [], [], []
    for c in candles:
        op.append(float(c["open"]))
        high.append(float(c["high"]))
        low.append(float(c["low"]))
        close.append(float(c["close"]))
    op, high, low, close = (np.array(x) for x in (op, high, low, close))
    atr = atr_series(op, high, low, close)
    rows: list[dict] = []
    n = len(candles)
    if n == 0:
        return rows

    # kelompokkan indeks per hari (tanggal bar open, UTC)
    days: dict[object, list[int]] = {}
    for i, c in enumerate(candles):
        ts = c["ts"]
        if isinstance(ts, str):
            ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        days.setdefault(ts.date(), []).append(i)

    for idxs in days.values():
        idxs = sorted(idxs)
        last_i = idxs[-1]
        last_close_min = _minutes(candles[last_i]["ts"]) + 5  # menit close bar
        if last_close_min < force_close_utc * 60:
            continue  # hari pendek (libur): horizon tidak sampai force-close
        timeout_close = close[last_i]
        for i in idxs:
            ts = candles[i]["ts"]
            if isinstance(ts, str):
                ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            if ts.weekday() >= 5:
                continue
            m = _minutes(ts)
            if not (entry_start_utc * 60 <= m < entry_end_utc * 60):
                continue
            atr_i = atr[i]
            if np.isnan(atr_i) or atr_i <= 0:
                continue
            sl_dist = sl_mult * float(atr_i)
            if not (min_sl_dist <= sl_dist <= max_sl_dist):
                continue
            horizon = [j for j in idxs if j > i]
            if len(horizon) < min_horizon_bars:
                continue
            entry = close[i]
            tp_dist = rr * sl_dist
            # long
            sl_l, tp_l = entry - sl_dist, entry + tp_dist
            hit_sl_l = hit_tp_l = None
            for j in horizon:
                if low[j] <= sl_l:
                    hit_sl_l = j
                    break
                if high[j] >= tp_l:
                    hit_tp_l = j
                    break
            if hit_sl_l is not None:
                lab_l = 0
            elif hit_tp_l is not None:
                lab_l = 1
            else:
                lab_l = 1 if timeout_close > entry else 0
            # short (cermin)
            sl_s, tp_s = entry + sl_dist, entry - tp_dist
            hit_sl_s = hit_tp_s = None
            for j in horizon:
                if high[j] >= sl_s:
                    hit_sl_s = j
                    break
                if low[j] <= tp_s:
                    hit_tp_s = j
                    break
            if hit_sl_s is not None:
                lab_s = 0
            elif hit_tp_s is not None:
                lab_s = 1
            else:
                lab_s = 1 if timeout_close < entry else 0
            rows.append({
                "ts": candles[i]["ts"], "close": float(entry),
                "atr": float(atr_i), "sl_dist": round(sl_dist, 4),
                "tp_dist": round(tp_dist, 4), "horizon": len(horizon),
                "label_long": lab_l, "label_short": lab_s,
            })
    return rows
