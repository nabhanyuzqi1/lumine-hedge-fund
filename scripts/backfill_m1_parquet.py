#!/usr/bin/env python3
"""Backfill candle M1 dari parquet tick pipeline (perbaikan insiden 24 Nov).

Insiden: `_ensure_months` gagal pada deployment `candles` tabel biasa
(InvalidObjectDefinition '"candles" is not partitioned') sehingga tulis M1
(ingest API) dan rollup M5 berhenti; tick tetap ter-flush ke parquet karena
jalur parquet tidak menyentuh DB. Skrip ini memutar kembali tick parquet
melalui agregasi yang SAMA dengan IngestPipeline._agg_m1 (bucket menit dari
waktu kedatangan, OHLC dari bid, volume = jumlah tick) lalu upsert idempotent
ke candles (SQL sama dengan _flush_db).

Backfill TIDAK menyentuh order/posisi; hanya candle M1 (rollup M5/M15/H1
dijalankan terpisah via `python -m app.candle_rollup --once`).

Pemakaian:
  api/.venv/bin/python scripts/backfill_m1_parquet.py \
      [--day 2026-11-23] [--symbol XAUUSD] [--from 2026-11-23T08:50] \
      [--to 2026-11-23T18:45] [--dry-run]

Exit 0 sukses; 2 bila parquet hari itu tidak ada.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

API_DIR = Path(__file__).resolve().parents[1] / "api"
if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))

import pandas as pd  # noqa: E402

from app import db  # noqa: E402

PARQUET_DIR = Path(os.environ.get(
    "TICKS_PARQUET_DIR", str(API_DIR.parent / "data" / "parquet")))


def parse_utc(s: str) -> datetime:
    dt = datetime.fromisoformat(s)
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


def build_m1_bars(df: pd.DataFrame, symbol: str) -> list[dict]:
    """Agregasi tick -> bar M1, identik dengan IngestPipeline._agg_m1.

    Bucket menit dari ts kedatangan (true UTC); OHLC dari bid; volume =
    jumlah tick dalam menit itu. Tick loncatan >MAX_QUOTE_JUMP_PCT dari
    baseline sehat ditolak (guard sama dengan IngestPipeline._quote_jumps —
    kutipan basi EA 2001.10 meracuni low bar, insiden 23 Nov 2026); level
    baru dianggap asli setelah MAX_JUMP_CONFIRM_TICKS tick beruntun.
    """
    from app.ingest import MAX_JUMP_CONFIRM_TICKS, MAX_QUOTE_JUMP_PCT

    g = df[df["symbol"] == symbol].sort_values("ts_utc")
    if g.empty:
        return []
    base: float | None = None
    cand_price, cand_n = None, 0
    keep: list[tuple[str, float]] = []
    for ts, bid in zip(g["ts_utc"], g["bid"].astype(float)):
        if base is None or base <= 0:
            base = bid
            keep.append((ts, bid))
            continue
        if abs(bid - base) / base <= MAX_QUOTE_JUMP_PCT / 100.0:
            base = bid
            cand_price, cand_n = None, 0
            keep.append((ts, bid))
            continue
        if cand_price is not None and abs(bid - cand_price) / cand_price <= 0.001:
            cand_n += 1
            if cand_n >= MAX_JUMP_CONFIRM_TICKS:
                base = bid
                cand_price, cand_n = None, 0
                keep.append((ts, bid))
            continue
        cand_price, cand_n = bid, 1
    rows = [(ts, bid) for ts, bid in keep]
    if not rows:
        return []
    t = pd.DataFrame(rows, columns=["ts_utc", "bid"])
    t["minute"] = pd.to_datetime(t["ts_utc"], utc=True).dt.floor("min")
    bars = []
    for minute, grp in t.groupby("minute"):
        bid = grp["bid"].astype(float)
        bars.append({
            "symbol": symbol, "timeframe": "M1", "ts": minute.to_pydatetime(),
            "open": float(bid.iloc[0]), "high": float(bid.max()),
            "low": float(bid.min()), "close": float(bid.iloc[-1]),
            "volume": int(len(grp)),
        })
    bars.sort(key=lambda b: b["ts"])
    return bars


async def write_bars(bars: list[dict]) -> int:
    """Upsert idempotent, SQL sama dengan IngestPipeline._flush_db."""
    if not bars:
        return 0
    await db.init_pool()
    async with db.pool().connection() as conn:
        cur = conn.cursor()
        await cur.executemany(
            """
            INSERT INTO candles (symbol, timeframe, ts, open, high, low, close, volume)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (symbol, timeframe, ts) DO UPDATE SET
                open = EXCLUDED.open, high = EXCLUDED.high, low = EXCLUDED.low,
                close = EXCLUDED.close, volume = EXCLUDED.volume
            """,
            [(b["symbol"], b["timeframe"], b["ts"], b["open"], b["high"],
              b["low"], b["close"], b["volume"]) for b in bars],
        )
        await cur.close()
        await conn.commit()
    return len(bars)


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--day", default=datetime.now(timezone.utc).date().isoformat())
    parser.add_argument("--symbol", default="XAUUSD")
    parser.add_argument("--from", dest="start", default=None)
    parser.add_argument("--to", dest="end", default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    path = PARQUET_DIR / f"ticks_{args.day}.parquet"
    if not path.exists():
        print(f"parquet tidak ada: {path}")
        return 2
    df = pd.read_parquet(path)
    start = parse_utc(args.start) if args.start else None
    end = parse_utc(args.end) if args.end else None
    if start is not None:
        df = df[df["ts_utc"] >= start.isoformat().replace("+00:00", "Z")]
    if end is not None:
        df = df[df["ts_utc"] < end.isoformat().replace("+00:00", "Z")]
    bars = build_m1_bars(df, args.symbol)
    print(f"tick {len(df)} (dipakai {sum(b['volume'] for b in bars)}) -> bar M1 {len(bars)} "
          f"({bars[0]['ts'].isoformat() if bars else '-'} .. "
          f"{bars[-1]['ts'].isoformat() if bars else '-'}) utk {args.symbol}")
    if args.dry_run:
        for b in bars[:3] + bars[-3:]:
            print(" ", b)
        return 0
    written = await write_bars(bars)
    print(f"upsert {written} bar M1 selesai")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
