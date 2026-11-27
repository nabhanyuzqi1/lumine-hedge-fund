"""Market Regime Detection (PRD v2.2 §6): classifier deterministic berversi.

MURNI (no I/O, no clock, no RNG): semua input lewat argumen. Dipakai oleh
paper runner (live/paper) dan backtest dengan definisi yang SAMA (PRD §6.5),
jadi label di dataset yang sama selalu identik.

Label (PRD §6.2):
    TREND_UP, TREND_DOWN, RANGE, HIGH_VOLATILITY, LOW_LIQUIDITY, UNKNOWN.
NEWS_OR_EVENT_RISK: RESERVED pada versi ini - tidak pernah dikeluarkan karena
belum ada kalender/sumber event yang tervalidasi (NEWS_SOURCE_VALIDATED=False,
PRD §6.2 mensyaratkan sumber tervalidasi sebelum label dipakai).

Pohon keputusan (prioritas tetap, deterministik):
    1. Data quality gagal (bar kurang, stale, gap jam pasar, candle rusak,
       likuiditas stale) -> UNKNOWN (kondisi aman: strategi yang mensyaratkan
       regime tertentu tidak boleh entry).
    2. LOW_LIQUIDITY  : spread > max(median15 x mult, abs) atau tick rate rendah.
    3. HIGH_VOLATILITY: vol percentile >= ambang atau ATR/median-TR >= ambang.
    4. TREND_UP/DOWN  : ADX >= ambang DAN arah slope MA DAN posisi close vs MA.
    5. RANGE          : default bila data OK dan tidak ada rule lain yang
       terpicu (ADX rendah / arah tidak meyakinkan).

Hysteresis (anti flip-flop, PRD §6.4): perubahan label butuh konfirmasi
``confirm_bars`` bar berturut-turut ATAU margin confidence ``confidence_margin``
di atas label berjalan; setelah pergantian, ``cooldown_bars`` bar berikutnya
hanya boleh berganti lewat margin. Keputusan dibekukan per bar (idempoten).
UNKNOWN dari data quality SELALU lolos hysteresis (safety).

Regime adalah FILTER kelayakan entry, bukan pengubah risk limit (PRD §6.4):
modul ini tidak pernah menyentuh angka risk (volume, SL, drawdown). Gate entry
di runner/backtest: ``regime_permits_entry(label, allowed_regimes)`` - UNKNOWN
selalu memblokir entry strategi yang mendeklarasikan allowed_regimes.

RegimeParams default adalah [USULAN] (PRD §6.4): ambang confidence belum
dikalibrasi; kalibrasi menyusul lewat evaluasi confusion matrix (PRD §6.4).

Kontrak pemanggilan (sama untuk backtest dan live):

    result = regime.classify(
        symbol="XAUUSD",
        now=datetime_utc,                      # snapshot waktu (aware UTC)
        candles=[{ts, open, high, low, close}  # bar CLOSED, ascending
                 ...],
        liquidity={"ts": iso, "spread": 0.3, "fresh": True,
                   "spread_median_15m": 0.25},
        params=regime.default_params_for_symbol("XAUUSD"),
        state=regime_state_dari_loop_sebelumnya,   # None = tanpa hysteresis
        tick_rate=42.0,        # opsional (live): tick per menit window feed
        spread_p95=0.55,       # opsional: p95 spread window (fitur, bukan rule)
    )
    # result.label / result.confidence / result.ts / result.data_quality /
    # result.reason / result.features / result.state (simpan untuk loop berikut)

XAUUSD gap akhir pekan/break harian BUKAN data buruk: gap hanya dihitung di
menit jam pasar (mirror app.data_quality; dijaga sinkron oleh test).
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

REGIME_VERSION = "1.0.0"

# PRD §6.2. NEWS_OR_EVENT_RISK reserved (lihat docstring modul).
REGIME_LABELS = (
    "TREND_UP", "TREND_DOWN", "RANGE", "HIGH_VOLATILITY",
    "LOW_LIQUIDITY", "NEWS_OR_EVENT_RISK", "UNKNOWN",
)

# Label yang dikeluarkan versi ini (NEWS_OR_EVENT_RISK butuh sumber tervalidasi).
EMITTED_LABELS = ("TREND_UP", "TREND_DOWN", "RANGE", "HIGH_VOLATILITY",
                  "LOW_LIQUIDITY", "UNKNOWN")

NEWS_SOURCE_VALIDATED = False  # PRD §6.2: False -> label NEWS tidak dipakai.

# Sesi pasar (UTC) - MIRROR app.ingest.session_of; sinkronitas dijaga test.
# asia 21-07, london 07-12, london_newyork 12-16, newyork 16-21.
SESSION_BOUNDS = ((0, 7, "asia"), (7, 12, "london"),
                  (12, 16, "london_newyork"), (16, 21, "newyork"))

# Jam tutup XAUUSD (UTC) - MIRROR app.data_quality (GOLD_DAILY_BREAK/WEEKEND).
GOLD_DAILY_BREAK = (22 * 60, 23 * 60)
GOLD_WEEKEND = (4, 22 * 60 + 20, 6, 23 * 60 + 20)

# Ambang spread absolut per simbol - MIRROR app.data_quality.SPREAD_ABS_MAX.
SPREAD_ABS_MAX = {"XAUUSD": 0.50, "BTCUSD": 100.00}


@dataclass(frozen=True)
class RegimeParams:
    """Parameter classifier (PRD §6.4: classifier punya versi dan parameter).

    Semua ambang = [USULAN], belum dikalibrasi (PRD §6.4); dikalibrasi lewat
    evaluasi confusion matrix per PRD. Window dipilih agar muat di context
    300 candle paper runner (CANDLE_LIMIT=300).
    """

    min_bars: int = 220              # < ini = UNKNOWN (data tidak cukup)
    # ---- volatilitas ----
    vol_lookback: int = 60           # bar utk realized vol per titik
    vol_window: int = 150            # panjang series rolling vol utk percentile
    vol_high_pctile: float = 0.90    # >= ini -> kandidat HIGH_VOLATILITY
    atr_period: int = 14
    atr_window: int = 150            # bar utk ATR + baseline median TR
    atr_expand_ratio: float = 1.5    # ATR / median TR >= ini = range expansion
    # ---- trend ----
    adx_period: int = 14
    adx_window: int = 100            # bar utk ADX (Wilder)
    adx_trend_min: float = 25.0
    ma_period: int = 50
    ma_slope_window: int = 20        # slope diukur selama N bar terakhir
    slope_min_atr: float = 0.04      # |slope| minimum (ATR/bar) utk fire TREND
    slope_ref_atr: float = 0.15      # slope = 1.0 confidence utk komponen slope
    # ---- likuiditas ----
    spread_median_mult: float = 2.0  # spread > mult x median15 (PRD §5.2)
    spread_abs_usd: float = 0.50     # fallback absolut (XAUUSD; BTC 100.00)
    tick_rate_min: float = 5.0       # tick/menit < ini = likuiditas rendah
    max_liquidity_age_s: float = 120.0
    # ---- data quality ----
    gap_fail_open_min: float = 15.0  # gap jam pasar > 15 mnt -> UNKNOWN
    max_gap_ratio: float = 0.05      # > 5% menit pasar hilang -> UNKNOWN
    max_stale_factor: float = 2.5    # usia bar > 2.5 x tf (+60s) -> UNKNOWN
    # ---- hysteresis (PRD §6.4) ----
    confirm_bars: int = 2            # bar konfirmasi utk ganti label
    confidence_margin: float = 0.15  # switch langsung di atas margin
    cooldown_bars: int = 3           # pasca-ganti: hanya switch via margin


@dataclass(frozen=True)
class RegimeResult:
    """Keluaran classifier (PRD §6.4): label, confidence, timestamp,
    data quality, alasan (+ fitur lengkap utk audit dan state hysteresis)."""

    label: str
    confidence: float
    ts: str                    # ISO UTC: close bar terakhir (anchor deterministik)
    data_quality: dict
    reason: str
    features: dict
    classifier_version: str = REGIME_VERSION
    state: dict = field(default_factory=dict)


def default_params_for_symbol(symbol: str) -> RegimeParams:
    """Default per simbol: hanya ambang spread absolut yang beda (A9)."""
    spread_abs = SPREAD_ABS_MAX.get(str(symbol).upper(), SPREAD_ABS_MAX["XAUUSD"])
    return RegimeParams(spread_abs_usd=float(spread_abs))

# ---------------------------------------------------------------- helpers

def _clip01(x: float) -> float:
    return max(0.0, min(1.0, x))


def _parse_ts(value) -> datetime:
    """ISO string / datetime -> aware UTC datetime."""
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    ts = str(value).replace("Z", "+00:00")
    parsed = datetime.fromisoformat(ts)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _session_of(dt: datetime) -> str:
    """Sesi pasar UTC; mirror app.ingest.session_of (dijaga sinkron test)."""
    h = dt.hour
    if h < 7 or h >= 21:
        return "asia"
    if h < 12:
        return "london"
    if h < 16:
        return "london_newyork"
    return "newyork"


def _minute_of_day(dt: datetime) -> int:
    return dt.hour * 60 + dt.minute


def _market_closed_minutes(symbol: str, ts: datetime) -> bool:
    """True bila menit ts di luar jam pasar spot (mirror app.data_quality)."""
    if str(symbol).upper() != "XAUUSD":
        return False  # crypto 24/7 dianggap buka
    mod = _minute_of_day(ts)
    wd = ts.weekday()
    start_d, start_m, end_d, end_m = GOLD_WEEKEND
    in_weekend = False
    if start_d <= end_d:
        if start_d < wd < end_d:
            in_weekend = True
        elif wd == start_d and mod >= start_m:
            in_weekend = True
        elif wd == end_d and mod <= end_m:
            in_weekend = True
    if in_weekend:
        return True
    lo, hi = GOLD_DAILY_BREAK
    return lo - 5 <= mod <= hi + 5 and wd not in (4, 5, 6)


def _open_minutes_between(symbol: str, start: datetime, end: datetime) -> int:
    """Menit pasar BUKA dalam (start, end): akhir pekan/break bukan gap."""
    n = 0
    cur = start + timedelta(minutes=1)
    while cur < end:
        if not _market_closed_minutes(symbol, cur):
            n += 1
        cur += timedelta(minutes=1)
    return n


def _finite(x) -> bool:
    return isinstance(x, (int, float)) and math.isfinite(float(x))


def _parse_candles(candles: list[dict]) -> tuple[list[dict] | None, str | None]:
    """Parse + validasi dasar candle. Return (list, error).

    Error non-None = data tidak layak klasifikasi (-> UNKNOWN). List keluaran
    berisi dict baru {ts, open, high, low, close} (context tak dimutasi).
    """
    out = []
    prev_ts = None
    for c in candles or []:
        try:
            ts = _parse_ts(c["ts"])
            o, h, l, cl = (float(c["open"]), float(c["high"]),
                           float(c["low"]), float(c["close"]))
        except (KeyError, TypeError, ValueError):
            return None, "candle rusak/tidak lengkap"
        if not (math.isfinite(o) and math.isfinite(h)
                and math.isfinite(l) and math.isfinite(cl)):
            return None, "harga non-finite (NaN/Inf)"
        if o <= 0 or h <= 0 or l <= 0 or cl <= 0:
            return None, "harga <= 0"
        if h < l - 1e-12 or h < max(o, cl) - 1e-12 or l > min(o, cl) + 1e-12:
            return None, "candle melanggar OHLC"
        if prev_ts is not None and ts <= prev_ts:
            return None, "timestamp tidak naik ketat (duplikat/urutan)"
        prev_ts = ts
        out.append({"ts": ts, "open": o, "high": h, "low": l, "close": cl})
    if not out:
        return None, "tidak ada candle"
    return out, None


def _median_step_seconds(candles: list[dict]) -> int:
    """Deteksi tf dari median jeda antar bar (detik)."""
    diffs = [(candles[i]["ts"] - candles[i - 1]["ts"]).total_seconds()
             for i in range(1, min(len(candles), 21))]
    diffs = [d for d in diffs if d > 0]
    if not diffs:
        return 0
    return int(statistics.median(diffs))


# ------------------------------------------------------------- indicators

def _true_ranges(candles: list[dict]) -> list[float]:
    trs = []
    for i in range(1, len(candles)):
        h, l, pc = candles[i]["high"], candles[i]["low"], candles[i - 1]["close"]
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    return trs


def _wilder_smooth(values: list[float], period: int) -> float | None:
    """RMA Wilder: seed = SMA period pertama, lalu rekursif. Deterministik
    pada window yang diberikan."""
    if len(values) < period:
        return None
    sm = sum(values[:period]) / period
    for v in values[period:]:
        sm = sm - sm / period + v / period  # RMA Wilder: (sm*(n-1)+v)/n
    return sm


def atr(candles: list[dict], period: int = 14) -> float | None:
    """ATR Wilder pada seluruh candle yang diberikan (bar tertutup)."""
    trs = _true_ranges(candles)
    return _wilder_smooth(trs, period)


def _wilder_series(values: list[float], period: int) -> list[float]:
    """Series RMA Wilder: seed SMA period pertama, lalu rekursif per bar."""
    if len(values) < period:
        return []
    out = [sum(values[:period]) / period]
    for v in values[period:]:
        out.append(out[-1] - out[-1] / period + v / period)  # RMA Wilder
    return out


def adx(candles: list[dict], period: int = 14) -> float | None:
    """ADX Wilder standar: DX series lalu RMA period (butuh >= 2*period+1 bar)."""
    n = len(candles)
    if n < 2 * period + 1:
        return None
    plus_dm, minus_dm, trs = [], [], []
    for i in range(1, n):
        h, l, ph, pl, pc = (candles[i]["high"], candles[i]["low"],
                            candles[i - 1]["high"], candles[i - 1]["low"],
                            candles[i - 1]["close"])
        up, down = h - ph, pl - l
        plus_dm.append(up if (up > down and up > 0) else 0.0)
        minus_dm.append(down if (down > up and down > 0) else 0.0)
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    sm_tr = _wilder_series(trs, period)
    sm_p = _wilder_series(plus_dm, period)
    sm_m = _wilder_series(minus_dm, period)
    if not sm_tr or sm_tr[-1] <= 0:
        return None
    dx_series = []
    for a, b, t in zip(sm_p, sm_m, sm_tr):
        if t <= 0:
            dx_series.append(0.0)
            continue
        di_p, di_m = 100.0 * a / t, 100.0 * b / t
        denom = di_p + di_m
        dx_series.append(100.0 * abs(di_p - di_m) / denom if denom > 0 else 0.0)
    if len(dx_series) < 2 * period:
        return None
    return _wilder_smooth(dx_series, period)


def realized_vol(candles: list[dict], lookback: int) -> float | None:
    """Std log-return close pada ``lookback`` bar terakhir (per bar)."""
    closes = [c["close"] for c in candles[-(lookback + 1):]]
    if len(closes) < 3:
        return None
    rets = [math.log(closes[i] / closes[i - 1])
            for i in range(1, len(closes)) if closes[i - 1] > 0 and closes[i] > 0]
    if len(rets) < 2:
        return None
    return statistics.stdev(rets)


def rolling_vol_percentile(candles: list[dict], lookback: int, window: int) -> float | None:
    """Percentile realized vol saat ini terhadap series rolling vol
    (``window`` titik, masing-masing atas ``lookback`` bar)."""
    current = realized_vol(candles[-(lookback + 1):], lookback)
    if current is None:
        return None
    series = []
    for i in range(len(candles) - window - lookback, len(candles) - lookback + 1):
        if i < 1:
            continue
        v = realized_vol(candles[:i + lookback], lookback)
        if v is not None:
            series.append(v)
    if not series:
        return None
    less = sum(1 for v in series if v < current)
    return less / len(series)

# ----------------------------------------------------------- data quality

def _check_data_quality(*, symbol: str, now: datetime, candles: list[dict],
                        liquidity: dict | None,
                        params: RegimeParams) -> tuple[dict, str | None]:
    """Gate data quality (PRD §6.4: data tidak lengkap/stale -> UNKNOWN).

    Return (dq_dict, fail_reason); fail_reason None = lolos semua cek.
    Gap dihitung hanya pada menit jam pasar (akhir pekan/break bukan gap).
    """
    n = len(candles)
    tf = _median_step_seconds(candles)
    last = candles[-1]
    last_close = last["ts"] + timedelta(seconds=tf)
    age_s = (now - last_close).total_seconds()

    dq: dict = {
        "bars": n,
        "tf_seconds": tf,
        "last_bar_ts": last["ts"].isoformat(),
        "last_bar_close_ts": last_close.isoformat(),
        "last_bar_age_s": round(age_s, 1),
    }
    fail = None
    if tf <= 0:
        fail = "tf tidak terdeteksi dari candle"
    elif n < params.min_bars:
        fail = f"bar {n} < min_bars {params.min_bars}"
    elif last_close > now:
        fail = "bar terakhir belum closed"
    elif age_s > params.max_stale_factor * tf + 60:
        fail = f"bar stale: usia {age_s:.0f}s > {params.max_stale_factor * tf + 60:.0f}s"

    # ---- gap antar bar (hanya menit jam pasar) ----
    worst_gap = 0.0
    missing_open = 0.0
    normal_open = 0.0
    prev = None
    for c in candles:
        if prev is not None:
            delta_s = (c["ts"] - prev).total_seconds()
            if delta_s > 1.5 * tf and tf > 0:
                om = _open_minutes_between(symbol, prev, c["ts"])
                missing_open += om
                worst_gap = max(worst_gap, float(om))
                normal_open += om  # seluruh menit buka di rentang ini
            else:
                normal_open += delta_s / 60.0
        prev = c["ts"]
    gap_ratio = (missing_open / normal_open) if normal_open > 0 else 0.0
    dq["gap_open_minutes"] = round(missing_open, 1)
    dq["worst_gap_open_minutes"] = round(worst_gap, 1)
    dq["gap_ratio"] = round(gap_ratio, 4)
    if fail is None and worst_gap > params.gap_fail_open_min:
        fail = f"gap jam pasar {worst_gap:.0f}m > {params.gap_fail_open_min:.0f}m"
    if fail is None and gap_ratio > params.max_gap_ratio:
        fail = f"ratio menit pasar hilang {gap_ratio:.2%} > {params.max_gap_ratio:.0%}"

    # ---- likuiditas ----
    liq = liquidity or {}
    spread = liq.get("spread")
    liq_ts = liq.get("ts")
    fresh = liq.get("fresh")
    liq_age = None
    if liq_ts is not None:
        try:
            liq_age = (now - _parse_ts(liq_ts)).total_seconds()
        except (TypeError, ValueError):
            liq_age = None
    dq["spread"] = round(float(spread), 6) if _finite(spread) else None
    dq["liquidity_fresh"] = fresh if isinstance(fresh, bool) else None
    dq["liquidity_age_s"] = round(liq_age, 1) if liq_age is not None else None
    if fail is None and not _finite(spread):
        fail = "spread tidak tersedia/non-finite"
    elif fail is None and float(spread) < 0:
        fail = "spread negatif"
    elif fail is None and fresh is False:
        fail = "likuiditas tidak fresh"
    elif fail is None and liq_age is not None and liq_age > params.max_liquidity_age_s:
        fail = f"likuiditas stale: usia {liq_age:.0f}s > {params.max_liquidity_age_s:.0f}s"

    dq["status"] = "FAIL" if fail else "PASS"
    return dq, fail


# ---------------------------------------------------------------- features

def _compute_features(*, candles: list[dict], params: RegimeParams,
                      spread: float, median15, spread_p95, tick_rate) -> dict:
    """Semua fitur dari bar CLOSED saja (tanpa look-ahead)."""
    last = candles[-1]
    atr_win = candles[-params.atr_window:]
    atr_val = atr(atr_win, params.atr_period)
    trs = _true_ranges(atr_win)
    median_tr = statistics.median(trs) if trs else 0.0
    atr_ratio = (atr_val / median_tr) if (atr_val is not None and median_tr > 0) else None

    adx_win = candles[-params.adx_window:]
    adx_val = adx(adx_win, params.adx_period)

    closes = [c["close"] for c in candles]
    ma_now = (sum(closes[-params.ma_period:]) / params.ma_period
              if len(closes) >= params.ma_period else None)
    ma_ref = None
    if len(closes) >= params.ma_period + params.ma_slope_window:
        seg = closes[-(params.ma_period + params.ma_slope_window):-params.ma_slope_window]
        ma_ref = sum(seg) / len(seg)
    slope_atr = None
    if ma_now is not None and ma_ref is not None and atr_val and atr_val > 0:
        slope_atr = (ma_now - ma_ref) / (params.ma_slope_window * atr_val)

    rv = realized_vol(candles, params.vol_lookback)
    vol_pctile = rolling_vol_percentile(candles, params.vol_lookback, params.vol_window)

    return {
        "close": round(last["close"], 6),
        "atr": round(atr_val, 6) if atr_val is not None else None,
        "atr_median_tr": round(median_tr, 6) if trs else None,
        "atr_ratio": round(atr_ratio, 4) if atr_ratio is not None else None,
        "adx": round(adx_val, 2) if adx_val is not None else None,
        "ma": round(ma_now, 6) if ma_now is not None else None,
        "ma_slope_atr_per_bar": round(slope_atr, 4) if slope_atr is not None else None,
        "realized_vol": round(rv, 8) if rv is not None else None,
        "vol_pctile": round(vol_pctile, 4) if vol_pctile is not None else None,
        "spread": round(spread, 6),
        "spread_median_15m": round(float(median15), 6) if _finite(median15) else None,
        "spread_p95": round(float(spread_p95), 6) if _finite(spread_p95) else None,
        "tick_rate_per_min": round(float(tick_rate), 3) if _finite(tick_rate) else None,
        "session": _session_of(last["ts"] + timedelta(
            seconds=_median_step_seconds(candles))),
    }


# ---------------------------------------------------------- decision tree

def _decide(f: dict, params: RegimeParams) -> tuple[str, float, str]:
    """Pohon keputusan prioritas tetap. Return (label, confidence, alasan).

    Confidence = skor komponen [0.5..1.0] saat rule terpicu, lalu dikali
    faktor ketersediaan fitur opsional (lihat classify). Prioritas:
    LOW_LIQUIDITY > HIGH_VOLATILITY > TREND_UP/TREND_DOWN > RANGE.
    """
    spread = f["spread"]
    median15 = f["spread_median_15m"]
    thr = max(params.spread_median_mult * (median15 if median15 is not None else 0.0),
              params.spread_abs_usd)
    tick = f["tick_rate_per_min"]

    # 1. LOW_LIQUIDITY
    if spread > thr or (tick is not None and tick < params.tick_rate_min):
        excess = _clip01((spread - thr) / thr) if thr > 0 else 0.0
        deficit = (_clip01((params.tick_rate_min - tick) / params.tick_rate_min)
                   if tick is not None else 0.0)
        conf = 0.5 + 0.3 * excess + 0.2 * deficit
        if spread > thr:
            why = (f"spread {spread:.2f} > threshold {thr:.2f} "
                   f"(median15 {median15}, abs {params.spread_abs_usd:.2f})")
        else:
            why = f"tick rate {tick:.1f}/min < {params.tick_rate_min:.1f}/min"
        return "LOW_LIQUIDITY", conf, why

    # 2. HIGH_VOLATILITY (vol percentile atau range expansion)
    vol_pct, atr_r = f["vol_pctile"], f["atr_ratio"]
    vol_fire = vol_pct is not None and vol_pct >= params.vol_high_pctile
    exp_fire = atr_r is not None and atr_r >= params.atr_expand_ratio
    if vol_fire or exp_fire:
        c_vol = (_clip01((vol_pct - params.vol_high_pctile)
                         / (1.0 - params.vol_high_pctile)) if vol_pct is not None else 0.0)
        c_exp = (_clip01((atr_r - params.atr_expand_ratio) / params.atr_expand_ratio)
                 if atr_r is not None else 0.0)
        conf = 0.5 + 0.3 * c_vol + 0.2 * c_exp
        why = (f"vol pctile {vol_pct:.2f} >= {params.vol_high_pctile} "
               f"(rv {f['realized_vol']}), ATR/medianTR {atr_r} "
               f">= {params.atr_expand_ratio}")
        return "HIGH_VOLATILITY", conf, why

    # 3. TREND_UP / TREND_DOWN (ADX + arah slope MA + posisi close vs MA)
    adx_val, slope, close, ma = (f["adx"], f["ma_slope_atr_per_bar"],
                                 f["close"], f["ma"])
    if (adx_val is not None and adx_val >= params.adx_trend_min
            and slope is not None and ma is not None
            and abs(slope) >= params.slope_min_atr):
        if slope > 0 and close > ma:
            conf = (0.5 + 0.3 * _clip01((adx_val - params.adx_trend_min)
                                        / params.adx_trend_min)
                    + 0.2 * _clip01(abs(slope) / params.slope_ref_atr))
            return "TREND_UP", conf, (
                f"ADX {adx_val:.1f} >= {params.adx_trend_min}, slope MA "
                f"{slope:+.2f} ATR/bar > 0, close {close:.2f} > MA "
                f"{ma:.2f}")
        if slope < 0 and close < ma:
            conf = (0.5 + 0.3 * _clip01((adx_val - params.adx_trend_min)
                                        / params.adx_trend_min)
                    + 0.2 * _clip01(abs(slope) / params.slope_ref_atr))
            return "TREND_DOWN", conf, (
                f"ADX {adx_val:.1f} >= {params.adx_trend_min}, slope MA "
                f"{slope:+.2f} ATR/bar < 0, close {close:.2f} < MA "
                f"{ma:.2f}")

    # 4. RANGE (default bila data OK)
    c_adx = (_clip01((params.adx_trend_min - adx_val) / params.adx_trend_min)
             if adx_val is not None else 0.5)
    c_slope = (1.0 - _clip01(abs(slope) / params.slope_ref_atr)
               if slope is not None else 0.5)
    conf = 0.5 + 0.3 * c_adx + 0.2 * c_slope
    note = ""
    if adx_val is not None and adx_val >= params.adx_trend_min:
        note = " (ADX tinggi tapi arah tidak meyakinkan)"
    return "RANGE", conf, (
        f"ADX {adx_val if adx_val is not None else 'n/a'}, slope MA "
        f"{slope if slope is not None else 'n/a'} ATR/bar, tanpa sinyal "
        f"trend/vol/likuiditas{note}")

# --------------------------------------------------------------- classify

def _dq_conf_factor(features: dict) -> float:
    """Faktor ketersediaan fitur opsional (PRD §6.4: confidence harus
    dikalibrasi; fitur opsional yang absen menurunkan confidence, TIDAK
    mengubah label - supaya backtest (tanpa tick feed) dan live memakai
    definisi label yang sama)."""
    factor = 1.0
    if features.get("spread_median_15m") is None:
        factor *= 0.9   # input rule LOW_LIQUIDITY -> penalty terbesar
    if features.get("tick_rate_per_min") is None:
        factor *= 0.95  # fitur live-only (backtest tidak punya tick feed)
    if features.get("spread_p95") is None:
        factor *= 0.95  # fitur pelengkap (laporan, belum rule)
    return factor


def _unknown_result(reason: str, dq: dict, anchor_close_ts) -> RegimeResult:
    """UNKNOWN = kondisi aman (PRD §6.2). Selalu lolos hysteresis."""
    st = {
        "last_bar_ts": (dq.get("last_bar_ts") if dq else None),
        "label": "UNKNOWN",
        "confidence": 0.0,
        "reason": reason,
        "candidate": None,
        "candidate_count": 0,
        "cooldown_left": 0,
        "classifier_version": REGIME_VERSION,
    }
    if anchor_close_ts is None and dq:
        anchor_close_ts = dq.get("last_bar_close_ts")
        if isinstance(anchor_close_ts, str):
            anchor_close_ts = _parse_ts(anchor_close_ts)
    return RegimeResult(label="UNKNOWN", confidence=0.0,
                        ts=anchor_close_ts.isoformat() if anchor_close_ts else "",
                        data_quality=dq or {"status": "FAIL"},
                        reason=reason, features={}, state=st)


def classify(*, symbol: str, now: datetime, candles: list[dict],
             liquidity: dict | None, params: RegimeParams | None = None,
             state: dict | None = None, tick_rate=None,
             spread_p95=None) -> RegimeResult:
    """Klasifikasikan regime pasar pada snapshot data (PRD v2.2 §6).

    Murni: hasil hanya fungsi dari argumen. ``candles`` wajib bar CLOSED
    ascending; fitur hanya membaca bar tertutup -> tanpa look-ahead.
    ``state`` = hasil.state dari pemanggilan sebelumnya (hysteresis); None =
    tanpa hysteresis (label mentah). Keputusan dibekukan per bar: memanggil
    ulang pada bar yang sama mengembalikan keputusan yang sama.
    """
    p = params or default_params_for_symbol(symbol)
    parsed, err = _parse_candles(candles)
    if err is not None:
        return _unknown_result(err, {"status": "FAIL", "bars": len(candles or []),
                                     "error": err}, None)

    dq, fail = _check_data_quality(symbol=symbol, now=now, candles=parsed,
                                   liquidity=liquidity, params=p)
    if fail is not None:
        return _unknown_result(fail, dq, None)

    anchor = parsed[-1]["ts"]
    tf = dq["tf_seconds"]
    anchor_close = anchor + timedelta(seconds=tf)

    # Keputusan dibekukan per bar (idempoten; anti re-evaluasi dalam bar).
    if state and state.get("label") and state.get("last_bar_ts") == anchor.isoformat():
        features = _compute_features(candles=parsed, params=p,
                                     spread=float(liquidity.get("spread")),
                                     median15=(liquidity or {}).get("spread_median_15m"),
                                     spread_p95=spread_p95, tick_rate=tick_rate)
        return RegimeResult(label=str(state["label"]),
                            confidence=float(state.get("confidence", 0.0)),
                            ts=anchor_close.isoformat(), data_quality=dq,
                            reason=str(state.get("reason", "")),
                            features=features, state=dict(state))

    features = _compute_features(candles=parsed, params=p,
                                 spread=float(liquidity.get("spread")),
                                 median15=(liquidity or {}).get("spread_median_15m"),
                                 spread_p95=spread_p95, tick_rate=tick_rate)
    raw_label, raw_conf, raw_reason = _decide(features, p)
    conf = round(min(1.0, max(0.0, raw_conf * _dq_conf_factor(features))), 4)

    # ---- hysteresis / cooldown (PRD §6.4: anti flip-flop) ----
    cur = str(state["label"]) if state and state.get("label") else None
    cur_conf = float(state.get("confidence", 0.0)) if state else 0.0
    cand = state.get("candidate") if state else None
    cand_count = int(state.get("candidate_count", 0)) if state else 0
    cooldown = int(state.get("cooldown_left", 0)) if state else 0

    if cur is None:
        final_label, final_conf, final_reason = raw_label, conf, raw_reason
        cooldown_out = p.cooldown_bars
    elif raw_label == cur:
        final_label, final_conf, final_reason = raw_label, conf, raw_reason
        cand, cand_count = None, 0
        cooldown_out = max(0, cooldown - 1)
    else:
        immediate = conf >= cur_conf + p.confidence_margin
        can_confirm = (cand == raw_label and cand_count + 1 >= p.confirm_bars
                       and cooldown == 0)
        if immediate or can_confirm:
            final_label, final_conf, final_reason = raw_label, conf, raw_reason
            cand, cand_count = None, 0
            cooldown_out = p.cooldown_bars
        else:
            final_label, final_conf = cur, cur_conf
            final_reason = (
                f"{raw_reason} [hysteresis: hold {cur}; butuh "
                f"{p.confirm_bars} bar konfirmasi "
                f"({cand_count + 1}/{p.confirm_bars} untuk {raw_label}) "
                f"atau margin confidence {p.confidence_margin}]")
            if cand == raw_label:
                cand_count += 1
            else:
                cand, cand_count = raw_label, 1
            cooldown_out = max(0, cooldown - 1)

    state_out = {
        "last_bar_ts": anchor.isoformat(),
        "label": final_label,
        "confidence": final_conf,
        "reason": final_reason,
        "candidate": cand,
        "candidate_count": cand_count,
        "cooldown_left": cooldown_out,
        "classifier_version": REGIME_VERSION,
    }
    return RegimeResult(label=final_label, confidence=final_conf,
                        ts=anchor_close.isoformat(), data_quality=dq,
                        reason=final_reason, features=features, state=state_out)


# ------------------------------------------------------------------- gate

def regime_permits_entry(label: str, allowed_regimes) -> bool:
    """Gate entry strategi (PRD §6.2/§6.5).

    allowed_regimes kosong = strategi tidak mensyaratkan regime -> entry
    tidak diblokir regime. Bila strategi mensyaratkan: label HARUS ada di
    allowed DAN bukan UNKNOWN (UNKNOWN selalu blokir - kondisi aman).
    """
    allowed = [str(x) for x in (allowed_regimes or [])]
    if not allowed:
        return True
    return label != "UNKNOWN" and label in allowed


def allowed_regimes_for(strategy_module) -> list[str]:
    """Baca ALLOWED_REGIMES dari modul strategi (default [] = tanpa syarat).

    Strategi mendeklarasikan regime yang diizinkan (PRD §6.4) sebagai list
    pola di modulnya, mis. ALLOWED_REGIMES = ["TREND_UP", "RANGE"].
    """
    return [str(x) for x in (getattr(strategy_module, "ALLOWED_REGIMES", None) or [])]
