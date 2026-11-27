#!/usr/bin/env python3
"""Muat sejarah candle Dukascopy (dari m1 raw) ke tabel candles (PRD 5.1/5.4).

Agregasi m1 BID -> M5/M15/H1, validasi sanity, lalu upsert ke Postgres
(ON CONFLICT (symbol, timeframe, ts) DO UPDATE, partisi bulanan dibuat
otomatis). Snapshot parquet juga ditulis untuk audit.

Run:
  cd ~/fund2/api && .venv/bin/python ../scripts/load_dukascopy_history.py \
      --tfs M5 M15 H1
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "api"))

from app import db  # noqa: E402
from paper import dukascopy  # noqa: E402

BASE = Path(__file__).resolve().parent.parent
RAW_DIR = BASE / "data" / "dukascopy" / "m1" / "raw"
SNAPSHOT = BASE / "data" / "dukascopy" / "snapshot"


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tfs", nargs="+", default=["M5", "M15", "H1"])
    ap.add_argument("--symbol", default="XAUUSD")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    bid, ask = dukascopy.load_m1(RAW_DIR)
    print(f"raw m1: bid={len(bid)} ask={len(ask)} baris")
    series = dukascopy.spread_series(bid, ask)
    print(f"spread series: {len(series)} menit "
          f"({series[0][0]:%Y-%m-%d %H:%M} .. {series[-1][0]:%Y-%m-%d %H:%M} UTC)")
    from paper.costs import duka_session_medians
    print("median spread Duka per sesi:", duka_session_medians(series))

    await db.init_pool()
    try:
        async with db.pool().connection() as conn:
            for tf in args.tfs:
                candles = dukascopy.aggregate(bid, tf)
                check = dukascopy.validate_candles(candles)
                print(f"{tf}: {check}")
                if check["problems"]:
                    print(f"  VALIDASI GAGAL {tf}: {check['problems']}", file=sys.stderr)
                    sys.exit(1)
                if args.dry_run:
                    continue
                written = await dukascopy.upsert_candles(conn, args.symbol, tf, candles)
                print(f"  upsert {written} bar ({args.symbol} {tf})")
    finally:
        await db.close_pool()

    if not args.dry_run:
        SNAPSHOT.mkdir(parents=True, exist_ok=True)
        import pyarrow as pa
        import pyarrow.parquet as pq
        rows_ts, rows_o, rows_h, rows_l, rows_c, rows_v = [], [], [], [], [], []
        for c in dukascopy.aggregate(bid, "M1"):
            rows_ts.append(c["ts"].isoformat())
            rows_o.append(c["open"]); rows_h.append(c["high"])
            rows_l.append(c["low"]); rows_c.append(c["close"]); rows_v.append(c["volume"])
        table = pa.table({"ts": rows_ts, "open": rows_o, "high": rows_h,
                          "low": rows_l, "close": rows_c, "volume": rows_v})
        out = SNAPSHOT / "xauusd_m1_bid.parquet"
        pq.write_table(table, out)
        print(f"snapshot m1: {out} ({table.num_rows} baris)")


if __name__ == "__main__":
    asyncio.run(main())
