#!/usr/bin/env python3
"""Backfill candle M15 dari M5 (server-side, data broker konsisten).

Latar (23 Nov 2026): broker demo HF Markets hanya menyimpan ~5.000 bar M15
(~52 hari) untuk XAUUSD, sementara M5 tersedia 2 tahun. Backtest butuh M15
2 tahun; rollup M5->M15 memberi data konsisten dengan feed broker tanpa
sumber eksternal.

Aturan:
  - Bucket 15 menit UTC: open=M5 pertama, high=max, low=min, close=M5
    terakhir, volume=sum.
  - ON CONFLICT DO NOTHING: bar M15 asli broker (seed EA) tidak pernah
    ditimpa; rollup hanya mengisi sebelum rentang broker.

Pemakaian:
  env -u DATABASE_URL .venv/bin/python scripts/backfill_m15_from_m5.py \
      [--symbols XAUUSD BTCUSD] [--dry-run]
"""

from __future__ import annotations

import argparse
import os
from datetime import datetime, timedelta
from pathlib import Path

import psycopg


def load_database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if url:
        return url
    env_file = Path(__file__).resolve().parents[1] / "api" / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if line.startswith("DATABASE_URL="):
                return line.split("=", 1)[1].strip().strip('"')
    raise SystemExit("DATABASE_URL tidak ditemukan (env atau api/.env)")


def rollup(conn, symbol: str, dry_run: bool) -> tuple[int, datetime | None, datetime | None]:
    """Rollup M5->M15 untuk satu simbol. Return (baris_baru, min_ts, max_ts)."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT ts, open, high, low, close, volume
            FROM candles
            WHERE symbol = %s AND timeframe = 'M5'
            ORDER BY ts
            """,
            (symbol,),
        )
        rows = cur.fetchall()

    buckets: dict[datetime, list[tuple]] = {}
    for ts, o, h, l, c, v in rows:
        bucket = ts.replace(minute=(ts.minute // 15) * 15, second=0, microsecond=0)
        buckets.setdefault(bucket, []).append((ts, o, h, l, c, v))

    payload = []
    for bucket, bars in sorted(buckets.items()):
        bars.sort(key=lambda r: r[0])
        payload.append(
            (
                symbol,
                "M15",
                bucket,
                bars[0][1],
                max(b[2] for b in bars),
                min(b[3] for b in bars),
                bars[-1][4],
                sum((b[5] for b in bars), 0),
            )
        )

    if dry_run:
        return len(payload), payload[0][2] if payload else None, payload[-1][2] if payload else None

    inserted = 0
    with conn.cursor() as cur:
        for row in payload:
            cur.execute(
                """
                INSERT INTO candles (symbol, timeframe, ts, open, high, low, close, volume)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (symbol, timeframe, ts) DO NOTHING
                """,
                row,
            )
            inserted += cur.rowcount
    conn.commit()
    return inserted, payload[0][2] if payload else None, payload[-1][2] if payload else None


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--symbols", nargs="+", default=["XAUUSD", "BTCUSD"])
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    conn = psycopg.connect(load_database_url())
    try:
        for symbol in args.symbols:
            inserted, lo, hi = rollup(conn, symbol, args.dry_run)
            t0 = lo.astimezone(tz=None) if lo else None
            t1 = hi.astimezone(tz=None) if hi else None
            print(f"{symbol}: {inserted} bar M15 baru, rentang {t0} .. {t1}"
                  + (" (dry-run)" if args.dry_run else ""))
    finally:
        conn.close()


if __name__ == "__main__":
    main()
