#!/usr/bin/env python3
"""Backfill candle M5 dari raw Dukascopy lokal (rentang terbatas).

Latar (23 Nov 2026, gate DoD P2): ekspor seed EA dari broker demo HFM hanya
menghasilkan M5 2024-11-01 .. 2026-01-18 dan 2026-10-27 .. 2026-11-20; rentang
2026-01-18 .. 2026-10-27 kosong di DB. Raw Dukascopy m1 2 tahun (data/dukascopy/
m1/raw) sudah terunduh dan validasi OHLC-nya bersih, dipakai untuk mengisi
rentang kosong tersebut tanpa memanggil API (API Dukascopy sedang 429).

Aturan:
  - Agregasi m1 BID -> M5 (paper.dukascopy.aggregate), validasi sanity, lalu
    upsert ON CONFLICT (symbol, timeframe, ts) DO UPDATE hanya untuk rentang
    [--start, --end). Bar di luar rentang tidak disentuh.
  - Bar existing di dalam rentang di-backup ke --backup (JSON) agar bisa
    dipulihkan.
  - Setelah ini, M15 dilengkapi via scripts/backfill_m15_from_m5.py (rollup,
    ON CONFLICT DO NOTHING).

Pemakaian:
  cd ~/fund2/api && .venv/bin/python ../scripts/backfill_m5_from_dukascopy.py \
      --start 2026-01-18T00:00:00+00:00 --end 2026-10-27T00:00:00+00:00
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "api"))

from app import db  # noqa: E402
from paper import dukascopy  # noqa: E402

BASE = Path(__file__).resolve().parent.parent
RAW_DIR = BASE / "data" / "dukascopy" / "m1" / "raw"


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", required=True, help="ISO UTC, mis. 2026-01-18T00:00:00+00:00")
    ap.add_argument("--end", required=True, help="ISO UTC, eksklusif")
    ap.add_argument("--symbol", default="XAUUSD")
    ap.add_argument("--tf", default="M5")
    ap.add_argument("--backup", default="")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    start = datetime.fromisoformat(args.start)
    end = datetime.fromisoformat(args.end)

    bid, _ask = dukascopy.load_m1(RAW_DIR)
    candles = dukascopy.aggregate(bid, args.tf)
    fill = [c for c in candles if start <= c["ts"] < end]
    print(f"raw m1: {len(bid)} baris | {args.tf} total: {len(candles)} | "
          f"rentang isi: {len(fill)} bar")
    check = dukascopy.validate_candles(fill)
    print("validate:", check)
    if check["problems"]:
        print(f"VALIDASI GAGAL {args.tf}: {check['problems']}", file=sys.stderr)
        sys.exit(1)
    if args.dry_run:
        return

    await db.init_pool()
    try:
        async with db.pool().connection() as conn:
            if args.backup:
                rows = await (await conn.execute(
                    "SELECT ts, open, high, low, close, volume FROM candles "
                    "WHERE symbol = %s AND timeframe = %s AND ts >= %s AND ts < %s "
                    "ORDER BY ts", (args.symbol, args.tf, start, end))).fetchall()
                backup = [{k: str(v) for k, v in dict(r).items()} for r in rows]
                Path(args.backup).write_text(json.dumps(backup, indent=1))
                print(f"backup bar existing dalam rentang: {len(backup)} -> {args.backup}")
            written = await dukascopy.upsert_candles(conn, args.symbol, args.tf, fill)
            print(f"upsert {written} bar ({args.symbol} {args.tf})")
    finally:
        await db.close_pool()


if __name__ == "__main__":
    asyncio.run(main())
