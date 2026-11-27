#!/usr/bin/env python3
"""Profil spread per jam + kalibrasi ambang spread per simbol (PRD 5.2, t_f2mp4).

Sumber: parquet tick per simbol dari HFM recorder
(data/hfm_recording/parquet/ticks_<SYMBOL>_YYYY-MM-DD.parquet).

Output:
  - tabel profil per jam (UTC): median + p95 + session, dicetak ke stdout
    (jurnal systemd) — "profil spread harian tercetak";
  - JSON data/hfm_recording/spread_profile_<SYMBOL>.json (riwayat di-append);
  - settings DB: `spread_profile_<SYMBOL>` (profil per jam) dan
    `spread_calibration_<SYMBOL>` (usulan ambang, formula PRD 5.2:
    gate = max(2 x median 15 menit, ambang_absolut)).

Metode ambang absolut dari data:
  - median_15m  = median dari median spread per bucket 15 menit;
  - p95_15m     = persentil-95 dari median per bucket 15 menit;
  - ambang_abs  = p95_15m dibulatkan KE ATAS ke kelipatan 5 USD;
  - gate        = max(2 x median_15m, ambang_abs).

Run:
  cd ~/fund2 && api/.venv/bin/python scripts/spread_profile.py
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

BASE = Path(__file__).resolve().parent.parent
PARQUET_DIR = BASE / "data" / "hfm_recording" / "parquet"
PROFILE_JSON_DIR = BASE / "data" / "hfm_recording"
DEFAULT_SYMBOLS = ("BTCUSD", "XAUUSD")
SESSIONS = ("asia", "london", "london_newyork", "newyork")
BUCKET_15M = "15min"
ROUND_ABS_TO = 5  # ambang absolut dibulatkan ke kelipatan 5 USD


def session_of(dt: datetime) -> str:
    """Jendela sesi pasar (UTC): asia 21-07, london 07-12,
    london_newyork 12-16, newyork 16-21."""
    h = dt.hour
    if h < 7 or h >= 21:
        return "asia"
    if h < 12:
        return "london"
    if h < 16:
        return "london_newyork"
    return "newyork"


def load_ticks(symbol: str, days: int | None = None) -> pd.DataFrame:
    """Baca semua parquet tick per simbol; return DataFrame dengan ts_utc
    sebagai datetime UTC dan spread sebagai float."""
    files = sorted(PARQUET_DIR.glob(f"ticks_{symbol}_*.parquet"))
    if days is not None:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
        files = [f for f in files if f.stem[len(f"ticks_{symbol}_"):] >= cutoff]
    if not files:
        return pd.DataFrame()
    df = pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)
    df["ts_utc"] = pd.to_datetime(df["ts_utc"], utc=True)
    df["spread"] = df["spread"].astype(float)
    return df.sort_values("ts_utc").reset_index(drop=True)


def hourly_profile(df: pd.DataFrame) -> list[dict]:
    """Median + p95 spread per jam UTC (0-23) + sesi, dari semua tick."""
    if df.empty:
        return []
    out = []
    grouped = df.groupby(df["ts_utc"].dt.hour, observed=True)
    for hour, g in grouped:
        ts = g["ts_utc"].iloc[0].to_pydatetime()
        out.append({
            "hour_utc": int(hour),
            "session": session_of(ts.replace(hour=int(hour))),
            "n_ticks": int(len(g)),
            "median_spread": round(float(g["spread"].median()), 4),
            "p95_spread": round(float(g["spread"].quantile(0.95)), 4),
        })
    return out


def bucket_medians_15m(df: pd.DataFrame) -> pd.Series:
    """Median spread per bucket 15 menit (basis kalibrasi ambang)."""
    if df.empty:
        return pd.Series(dtype=float)
    bucket = df["ts_utc"].dt.floor(BUCKET_15M)
    return df.groupby(bucket, observed=True)["spread"].median()


def calibrate_threshold(df: pd.DataFrame) -> dict:
    """Usulan ambang spread per simbol dari data (PRD 5.2)."""
    med = bucket_medians_15m(df)
    if med.empty:
        return {}
    median_15m = float(med.median())
    p95_15m = float(med.quantile(0.95))
    abs_raw = p95_15m
    abs_thr = math.ceil(abs_raw / ROUND_ABS_TO) * ROUND_ABS_TO
    gate = max(2.0 * median_15m, abs_thr)
    return {
        "formula": "gate = max(2 x median_15menit, ambang_absolut); "
                   "ambang_absolut = p95(median 15 menit) dibulatkan ke atas "
                   f"ke kelipatan {ROUND_ABS_TO} USD",
        "n_buckets_15m": int(len(med)),
        "median_15m_usd": round(median_15m, 4),
        "p95_15m_usd": round(p95_15m, 4),
        "threshold_abs_usd": round(float(abs_thr), 4),
        "gate_spread_usd": round(float(gate), 4),
        "window_start": df["ts_utc"].iloc[0].isoformat(),
        "window_end": df["ts_utc"].iloc[-1].isoformat(),
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "source": "hfm_recorder parquet ticks_<SYMBOL>_<tanggal>.parquet",
    }


def print_profile(symbol: str, profile: list[dict], calib: dict) -> None:
    print(f"\n=== Profil spread per jam {symbol} (UTC, median / p95 USD) ===")
    print(f"{'jam':>3} {'sesi':<14} {'n_tick':>8} {'median':>10} {'p95':>10}")
    for row in profile:
        print(f"{row['hour_utc']:>3} {row['session']:<14} {row['n_ticks']:>8} "
              f"{row['median_spread']:>10.4f} {row['p95_spread']:>10.4f}")
    if calib:
        print(f"-- Kalibrasi ambang {symbol} (PRD 5.2) --")
        print(f"   median 15 menit : {calib['median_15m_usd']:.4f} USD "
              f"({calib['n_buckets_15m']} bucket)")
        print(f"   p95 15 menit    : {calib['p95_15m_usd']:.4f} USD")
        print(f"   ambang absolut  : {calib['threshold_abs_usd']:.4f} USD")
        print(f"   gate spread     : max(2 x {calib['median_15m_usd']:.4f}, "
              f"{calib['threshold_abs_usd']:.4f}) = {calib['gate_spread_usd']:.4f} USD")
        print(f"   window          : {calib['window_start']} .. {calib['window_end']}")


def save_json(symbol: str, profile: list[dict], calib: dict) -> None:
    PROFILE_JSON_DIR.mkdir(parents=True, exist_ok=True)
    path = PROFILE_JSON_DIR / f"spread_profile_{symbol}.json"
    history = []
    if path.exists():
        try:
            history = json.loads(path.read_text())
        except json.JSONDecodeError:
            history = []
    history.append({
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "hourly_profile": profile,
        "calibration": calib,
    })
    path.write_text(json.dumps(history, indent=2))


def upsert_settings(dsn: str, symbol: str, profile: list[dict], calib: dict) -> None:
    import psycopg

    with psycopg.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO settings (key, value, updated_at) VALUES (%s, %s, now()) "
                "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, "
                "updated_at = now()",
                (f"spread_profile_{symbol}", json.dumps({
                    "symbol": symbol,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                    "hourly_profile": profile,
                })))
            if calib:
                cur.execute(
                    "INSERT INTO settings (key, value, updated_at) VALUES (%s, %s, now()) "
                    "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, "
                    "updated_at = now()",
                    (f"spread_calibration_{symbol}", json.dumps(calib)))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--symbols", nargs="+", default=list(DEFAULT_SYMBOLS))
    ap.add_argument("--days", type=int, default=None,
                    help="batasi ke N hari terakhir (default: semua data)")
    ap.add_argument("--no-db", action="store_true", help="jangan tulis settings")
    args = ap.parse_args()

    dsn = os.environ.get("DATABASE_URL") or ""
    if not dsn and not args.no_db:
        env = BASE / "api" / ".env"
        if env.exists():
            for line in env.read_text().splitlines():
                if line.startswith("DATABASE_URL="):
                    dsn = line.split("=", 1)[1].strip()
    if not dsn and not args.no_db:
        print("DATABASE_URL tidak ditemukan; pakai --no-db", file=sys.stderr)
        return 2

    for symbol in args.symbols:
        df = load_ticks(symbol, args.days)
        if df.empty:
            print(f"[{symbol}] tidak ada data parquet, lewati")
            continue
        profile = hourly_profile(df)
        calib = calibrate_threshold(df)
        print_profile(symbol, profile, calib)
        save_json(symbol, profile, calib)
        if not args.no_db:
            upsert_settings(dsn, symbol, profile, calib)
            print(f"[{symbol}] settings spread_profile_{symbol} & "
                  f"spread_calibration_{symbol} terpasang")
    return 0


if __name__ == "__main__":
    sys.exit(main())
