#!/usr/bin/env python3
"""Unduh candle m1 XAUUSD Dukascopy (BID+ASK) untuk backtest P2 (PRD 5.2/5.4).

Sumber: https://datafeed.dukascopy.com/datafeed/XAUUSD/{YYYY}/{MM-1}/{DD}/
        {BID|ASK}_candles_min_1.bi5  (LZMA-alone; record 24 byte: int32 offset
        detik dari 00:00 UTC, int32 open/close/low/high dalam 1/1000 USD,
        float32 volume). Request di-pin ke node lama 194.8.15.180 via
        --resolve karena edge AWS baru mem-balas 429 untuk IP host ini.

Pacing: 3 worker, jeda antar-request, retry backoff pada 429/timeout.
Resume: file bi5 yang sudah ada dan valid dilewati.

Run:
  .venv/bin/python scripts/fetch_dukascopy_m1.py --start 2024-11-01 --end 2026-11-21
"""
from __future__ import annotations

import argparse
import concurrent.futures as futures
import lzma
import struct
import sys
import time
from datetime import date, timedelta
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
RAW_DIR = BASE / "data" / "dukascopy" / "m1" / "raw"
RAW_DIR.mkdir(parents=True, exist_ok=True)
HOST = "https://datafeed.dukascopy.com/datafeed/XAUUSD"
# Pin ke node lama (194.8.15.180): edge AWS baru mem-balas 429 untuk IP ini,
# node lama melayani normal. SNI/Host tetap datafeed.dukascopy.com.
RESOLVE = ["--resolve", "datafeed.dukascopy.com:443:194.8.15.180"]


def _http_get(url: str, timeout: float = 25) -> bytes:
    import subprocess
    cmd = ["curl", "-s", "-m", str(timeout), *RESOLVE, "-w", "\\n%{http_code}", url]
    out = subprocess.run(cmd, capture_output=True, timeout=timeout + 10).stdout
    body, _, code = out.rpartition(b"\n")
    if code.strip() != b"200":
        raise OSError(f"http {code.strip().decode() or '?'}")
    return body


def fetch(url: str, dest: Path, *, attempts: int = 8) -> str:
    """Unduh satu bi5; return: ok|cached|empty|nodata|fail.

    Node kadang mem-balas 404 sesaat (load balancer); 404 di-retry, dan bila
    konsisten (mis. akhir pean/hari libur) diklasifikasikan nodata.
    """
    if dest.exists() and dest.stat().st_size > 0:
        try:
            lzma.LZMADecompressor(lzma.FORMAT_ALONE).decompress(dest.read_bytes())
            return "cached"
        except Exception:
            dest.unlink()
    delay = 3.0
    not_found = 0
    for attempt in range(attempts):
        try:
            body = _http_get(url)
            lzma.LZMADecompressor(lzma.FORMAT_ALONE).decompress(body)  # validasi
            dest.write_bytes(body)
            return "ok"
        except Exception as exc:  # noqa: BLE001
            msg = str(exc)
            if "404" in msg:
                not_found += 1
                time.sleep(0.8 * (attempt + 1))
                continue
            if "429" in msg or "Too Many" in msg:
                time.sleep(delay)
                delay = min(delay * 2.5, 60.0)
                continue
            if attempt == attempts - 1:
                return f"fail: {msg}"
            time.sleep(1.5 * (attempt + 1))
    if not_found >= attempts - 1:
        return "nodata"
    return "fail: retries-exhausted"


def daterange(start: date, end: date):
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


def url_for(day: date, side: str) -> str:
    return f"{HOST}/{day.year}/{day.month - 1:02d}/{day.day:02d}/{side}_candles_min_1.bi5"


RECORD = struct.Struct(">iiiiif")


def parse_bi5(path: Path, day: date, side: str) -> list[tuple]:
    """-> list[(ts_utc_epoch, open, close, low, high, volume)]."""
    out = lzma.LZMADecompressor(lzma.FORMAT_ALONE).decompress(path.read_bytes())
    import datetime as dt
    day0 = dt.datetime(day.year, day.month, day.day, tzinfo=dt.timezone.utc).timestamp()
    rows = []
    for i in range(0, len(out), RECORD.size):
        off, o, c, l, h, v = RECORD.unpack(out[i:i + RECORD.size])
        rows.append((day0 + off, o / 1000.0, c / 1000.0, l / 1000.0, h / 1000.0, v))
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2024-11-01")
    ap.add_argument("--end", default="2026-11-21")
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--delay", type=float, default=0.15)
    args = ap.parse_args()

    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end)
    days = list(daterange(start, end))
    jobs = []
    for day in days:
        for side in ("BID", "ASK"):
            dest = RAW_DIR / f"{day}_{side.lower()}.bi5"
            jobs.append((day, side, url_for(day, side), dest))
    print(f"{len(jobs)} file ({len(days)} hari x BID/ASK)", flush=True)

    stats = {"ok": 0, "cached": 0, "empty": 0, "nodata": 0, "fail": 0}
    fails: list[str] = []
    done = 0
    with futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        futs = {pool.submit(fetch, url, dest): (day, side) for day, side, url, dest in jobs}
        for fut in futures.as_completed(futs):
            day, side = futs[fut]
            status = fut.result()
            dest = RAW_DIR / f"{day}_{side.lower()}.bi5"
            if status in ("ok", "cached"):
                n = len(lzma.LZMADecompressor(lzma.FORMAT_ALONE).decompress(dest.read_bytes())) // RECORD.size
                key = "empty" if n == 0 else status
            elif status == "nodata":
                key = "nodata"
            else:
                key = "fail"
                fails.append(f"{day} {side} {status}")
            stats[key] += 1
            done += 1
            if done % 50 == 0:
                print(f"[{done}/{len(jobs)}] {stats}", flush=True)
            time.sleep(args.delay)
    print("FINAL", stats, flush=True)
    if fails:
        print("FAILS:", *fails[:20], sep="\n", flush=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
