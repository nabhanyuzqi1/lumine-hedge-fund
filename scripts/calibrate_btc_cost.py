#!/usr/bin/env python3
"""Kalibrasi biaya backtest BTCUSD (PRD 5.2, t_f2mp4).

Rumus PRD 5.2: biaya backtest = spread sumber gratis (Dukascopy) x faktor
koreksi (rasio median HFM/Dukascopy per sesi) + haircut keamanan 20%.

- Spread Dukascopy: candle m1 BTCUSD (BID/ASK bi5, skala harga 1/10 USD)
  dari data/dukascopy/m1_btc/raw/ (unduh dengan --fetch).
- Spread HFM: liquidity_samples (agregat 5 detik dari tick EA) di DB,
  dibatasi ke window overlap dengan data Dukascopy yang tersedia.
- Faktor per sesi di-cap 3.0 (pengaman sampel tipis, paper.costs).

Output: settings `backtest_cost_calibration_BTCUSD` + laporan
docs/KALIBRASI_BTCUSD.md. Aman dijalankan ulang harian (idempoten).

Run:
  cd ~/fund2 && api/.venv/bin/python scripts/calibrate_btc_cost.py [--fetch]
"""
from __future__ import annotations

import argparse
import json
import lzma
import struct
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE / "api"))

from paper import costs, dukascopy  # noqa: E402

RAW_DIR = BASE / "data" / "dukascopy" / "m1_btc" / "raw"
DUKA_HOST = "https://datafeed.dukascopy.com/datafeed/BTCUSD"
DUKA_RESOLVE = ["--resolve", "datafeed.dukascopy.com:443:194.8.15.180"]
RECORD = struct.Struct(">iiiiif")
BTC_PRICE_SCALE = 10  # Dukascopy BTCUSD: harga dalam 1/10 USD (diverifikasi)
SYMBOL = "BTCUSD"


def _load_env_dsn() -> str:
    import os

    dsn = os.environ.get("DATABASE_URL")
    if dsn:
        return dsn
    env = BASE / "api" / ".env"
    for line in env.read_text().splitlines():
        if line.startswith("DATABASE_URL="):
            return line.split("=", 1)[1].strip()
    raise SystemExit("DATABASE_URL tidak ditemukan")


def fetch_duka_days(days_back: int = 3) -> None:
    """Unduh candle m1 Dukascopy utk hari-hari terakhir (hari ini belum
    lengkap di sumber, jadi hanya hari penuh yang berhasil)."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    today = datetime.now(timezone.utc).date()
    for back in range(1, days_back + 1):
        day = today - timedelta(days=back)
        # URL Dukascopy memakai bulan 0-indexed.
        url = (f"{DUKA_HOST}/{day.year}/{day.month - 1:02d}/{day.day:02d}")
        for side in ("bid", "ask"):
            dest = RAW_DIR / f"{day.isoformat()}_{side}.bi5"
            if dest.exists() and dest.stat().st_size > 0:
                try:
                    lzma.LZMADecompressor(lzma.FORMAT_ALONE).decompress(dest.read_bytes())
                    continue  # sudah valid
                except Exception:
                    dest.unlink()
            for attempt in range(5):
                cmd = ["curl", "-s", "-m", "40", *DUKA_RESOLVE, "-o", str(dest),
                       "-w", "%{http_code}", f"{url}/{side.upper()}_candles_min_1.bi5"]
                code = subprocess.run(cmd, capture_output=True, timeout=60).stdout.decode()
                if code == "200" and dest.exists() and dest.stat().st_size > 0:
                    try:
                        lzma.LZMADecompressor(lzma.FORMAT_ALONE).decompress(dest.read_bytes())
                        break
                    except Exception:
                        dest.unlink()
                time.sleep(3 + 2 * attempt)
            else:
                print(f"[duka] {dest.name}: tidak tersedia")


def parse_m1(path: Path) -> list[tuple]:
    """Parse bi5 m1 Dukascopy; skala harga BTCUSD 1/10 USD."""
    out = lzma.LZMADecompressor(lzma.FORMAT_ALONE).decompress(path.read_bytes())
    date_part = path.stem.rpartition("_")[0]
    day = datetime.strptime(date_part, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp()
    rows = []
    for i in range(0, len(out) - len(out) % RECORD.size, RECORD.size):
        off, o, c, l, h, v = RECORD.unpack(out[i:i + RECORD.size])
        rows.append((day + off, o / BTC_PRICE_SCALE, c / BTC_PRICE_SCALE,
                     l / BTC_PRICE_SCALE, h / BTC_PRICE_SCALE, v))
    return rows


def load_duka_spread() -> list[tuple[datetime, float]]:
    bid: list[tuple] = []
    ask: list[tuple] = []
    for path in sorted(RAW_DIR.glob("*.bi5")):
        date_part, _, side = path.stem.rpartition("_")
        if side not in ("bid", "ask"):
            continue
        try:
            rows = parse_m1(path)
        except Exception as exc:  # noqa: BLE001
            print(f"[duka] {path.name} gagal di-parse: {exc!r}")
            continue
        (bid if side == "bid" else ask).extend(rows)
    bid.sort(key=lambda r: r[0])
    ask.sort(key=lambda r: r[0])
    return dukascopy.spread_series(bid, ask)


def hfm_medians(dsn: str, window_start: datetime, window_end: datetime) -> tuple[dict, int]:
    """Median spread_avg per sesi dari liquidity_samples (window overlap)."""
    import psycopg

    with psycopg.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT session, spread_avg FROM liquidity_samples "
                "WHERE symbol = %s AND window_start >= %s AND window_start < %s",
                (SYMBOL, window_start, window_end))
            rows = [{"session": s, "spread_avg": float(v)} for s, v in cur.fetchall()]
    return costs.hfm_session_medians(rows), len(rows)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--fetch", action="store_true",
                    help="unduh candle m1 Dukascopy hari-hari terakhir dulu")
    ap.add_argument("--no-db", action="store_true")
    args = ap.parse_args()

    if args.fetch:
        fetch_duka_days()

    duka_series = load_duka_spread()
    if not duka_series:
        print("Tidak ada data Dukascopy; jalankan dengan --fetch", file=sys.stderr)
        return 1
    duka_start, duka_end = duka_series[0][0], duka_series[-1][0]
    print(f"duka m1 spread: {len(duka_series)} menit, "
          f"{duka_start:%Y-%m-%d %H:%M} .. {duka_end:%Y-%m-%d %H:%M} UTC")

    duka_medians = costs.duka_session_medians(duka_series)

    dsn = _load_env_dsn()
    hfm_medians_by_session, n_hfm = hfm_medians(dsn, duka_start,
                                                duka_end + timedelta(minutes=1))
    print(f"HFM liquidity_samples: {n_hfm} sampel dalam window overlap")
    for s in costs.SESSIONS:
        d = duka_medians.get(s)
        h = hfm_medians_by_session.get(s)
        if d and h:
            print(f"  {s:<14} duka={d:8.2f}  hfm={h:8.2f}  faktor={h / d:.3f}")
        else:
            print(f"  {s:<14} duka={d}  hfm={h}")

    model = costs.build_cost_model(duka_medians, hfm_medians_by_session,
                                   source="dukascopy_m1_btc+hfm_liquidity_samples")
    model.notes.append(
        f"window overlap {duka_start:%Y-%m-%d %H:%M}..{duka_end:%Y-%m-%d %H:%M} UTC; "
        f"{n_hfm} sampel HFM 5-detik")
    payload = model.as_dict()
    payload["window_start"] = duka_start.isoformat()
    payload["window_end"] = duka_end.isoformat()
    payload["computed_at"] = datetime.now(timezone.utc).isoformat()
    payload["hfm_samples"] = n_hfm
    payload["symbol"] = SYMBOL

    print("\n=== Cost model BTCUSD (PRD 5.2: duka x faktor + haircut 20%) ===")
    for s in costs.SESSIONS:
        print(f"  {s:<14} faktor={payload['factor_by_session'][s]:<7.3f} "
              f"filter={payload['filter_spread_by_session'][s]:<9.3f} "
              f"biaya={payload['spread_by_session'][s]:<9.3f} USD")
    for note in model.notes:
        print(f"  note: {note}")

    if not args.no_db:
        import psycopg

        with psycopg.connect(dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO settings (key, value, updated_at) VALUES (%s, %s, now()) "
                    "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, "
                    "updated_at = now()",
                    (f"backtest_cost_calibration_{SYMBOL}", json.dumps(payload)))
        print(f"[db] settings backtest_cost_calibration_{SYMBOL} terpasang")

    (BASE / "data" / "dukascopy" / "m1_btc" / "cost_calibration_BTCUSD.json").write_text(
        json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
