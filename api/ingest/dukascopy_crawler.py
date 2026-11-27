"""CLI crawler Dukascopy -> candles M1 (t_3c65f152).

Run (dari ~/fund2/api):
  # BTCUSD: tick per jam, 2 tahun (sekuensial, resume otomatis)
  .venv/bin/python -m ingest.dukascopy_crawler --symbols BTCUSD \
      --start 2024-11-24 --end 2026-11-24

  # XAUUSD: candle m1 harian dari raw existing (tanpa network)
  .venv/bin/python -m ingest.dukascopy_crawler --symbols XAUUSD --day-raw \
      --start 2024-11-01 --end 2026-11-22

  # XAUUSD: gap tick akhir pekan -> Senin 00:00 UTC
  .venv/bin/python -m ingest.dukascopy_crawler --symbols XAUUSD \
      --start 2026-11-21 --end 2026-11-24

  # ringkasan state + DB
  .venv/bin/python -m ingest.dukascopy_crawler --summary

  # preflight data quality (paper.preflight.run_preflight)
  .venv/bin/python -m ingest.dukascopy_crawler --preflight XAUUSD BTCUSD
"""
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
from pathlib import Path

from .dukascopy_store import (crawl_ticks, crawl_days, install_signal_handlers,
                              load_day_raw, crawl_bitstamp)
from .dukascopy_report import cmd_preflight, cmd_summary

API_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = API_DIR.parent / "data" / "dukascopy"
STATE_DIR = DATA_DIR / "ticks2y"


def _parse_dt(s: str) -> datetime:
    return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)


async def async_main(args) -> None:
    from app import db

    await db.init_pool()
    try:
        if args.summary:
            await cmd_summary(args.symbols, STATE_DIR)
            return
        if args.preflight is not None:
            symbols = args.preflight or args.symbols
            for symbol in symbols:
                await cmd_preflight(symbol, STATE_DIR)
            return
        for symbol in args.symbols:
            state_path = STATE_DIR / f"state_{symbol}.jsonl"
            from .dukascopy_store import StateLog
            state = StateLog(state_path)
            try:
                if args.day_raw:
                    stats = await load_day_raw(symbol, Path(args.raw_dir),
                                               _parse_dt(args.start),
                                               _parse_dt(args.end), state)
                elif args.day_candles:
                    stats = await crawl_days(symbol, _parse_dt(args.start),
                                             _parse_dt(args.end), state,
                                             delay=args.delay,
                                             attempts=args.attempts,
                                             flush_bars=args.flush_bars)
                elif args.bitstamp:
                    stats = await crawl_bitstamp(symbol, _parse_dt(args.start),
                                                 _parse_dt(args.end), state,
                                                 delay=args.delay,
                                                 attempts=args.attempts,
                                                 flush_bars=args.flush_bars)
                else:
                    stats = await crawl_ticks(symbol, _parse_dt(args.start),
                                              _parse_dt(args.end), state,
                                              delay=args.delay,
                                              attempts=args.attempts,
                                              flush_bars=args.flush_bars,
                                              limit_hours=args.limit_hours)
            finally:
                state.close()
            print(f"[{symbol}] HASIL {stats}", flush=True)
    finally:
        await db.close_pool()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--symbols", nargs="+", default=["BTCUSD"])
    ap.add_argument("--start", default="2024-11-24",
                    help="tanggal mulai UTC (inklusif, default 2024-11-24)")
    ap.add_argument("--end", default="2026-11-24",
                    help="tanggal akhir UTC (eksklusif, default 2026-11-24)")
    ap.add_argument("--delay", type=float, default=0.35,
                    help="jeda antar request jam (detik, default 0.35)")
    ap.add_argument("--attempts", type=int, default=5)
    ap.add_argument("--flush-bars", type=int, default=3000)
    ap.add_argument("--limit-hours", type=int, default=0,
                    help="batasi jumlah jam (smoke test; 0 = semua)")
    ap.add_argument("--day-raw", action="store_true",
                    help="muat candle m1 harian dari raw existing (tanpa network)")
    ap.add_argument("--day-candles", action="store_true",
                    help="crawl candle m1 harian (1 req/hari, fallback tick jam)")
    ap.add_argument("--bitstamp", action="store_true",
                    help="crawl M1 dari Bitstamp (BTCUSD; Dukascopy tak "
                         "menyediakan crypto - lihat bitstamp_client.py)")
    ap.add_argument("--raw-dir", default=str(DATA_DIR / "m1" / "raw"))
    ap.add_argument("--summary", action="store_true",
                    help="ringkasan state + hit DB, tanpa crawl")
    ap.add_argument("--preflight", nargs="*", default=None,
                    help="jalankan preflight M1 dari DB (default: --symbols)")
    args = ap.parse_args()
    install_signal_handlers()
    asyncio.run(async_main(args))


if __name__ == "__main__":
    main()
