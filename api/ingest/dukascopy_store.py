"""State resume + crawl loop + upsert DB untuk crawler Dukascopy (t_3c65f152).

Resume: JSONL per simbol, satu baris per unit selesai:
  {"s": "BTCUSD", "key": "1730000000", "st": "ok|empty|fail", "bars": 123} (jam)
  {"s": "XAUUSD", "key": "d2024-11-01", "st": "ok", "bars": 1440}          (hari)
Baris ditulis HANYA setelah bar-nya sukses di-upsert ke DB (idempotent:
ON CONFLICT DO UPDATE), jadi crash di tengah tidak merusak data.
"""
from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .dukascopy_client import (DEFAULT_DIV, KeepAliveClient, PRICE_DIV,
                               fetch_hour, hour_range, ticks_to_m1,
                               day_bytes_to_m1, day_range, fetch_day,
                               day_file_to_m1)


class StateLog:
    """Log status per unit (jam/hari) + set unit selesai, tahan crash."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.done: dict[tuple[str, str], str] = {}
        if self.path.exists():
            for line in self.path.read_text(encoding="utf-8").splitlines():
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                key = rec.get("h") if "h" in rec else rec.get("d")
                if key is not None:
                    self.done[(rec["s"], str(key))] = rec["st"]
        self._fh = open(self.path, "a", encoding="utf-8")

    def mark(self, symbol: str, key: str, status: str, bars: int) -> None:
        unit = {"s": symbol, "key": key, "st": status, "bars": bars}
        self._fh.write(json.dumps(unit) + "\n")
        self._fh.flush()
        self.done[(symbol, key)] = status

    def close(self) -> None:
        self._fh.close()


async def _flush_bars(db, dukascopy, symbol: str, bars: list[dict],
                      state: StateLog, pending: list[tuple[str, str, str, int]]) -> None:
    """Upsert buffer ke candles; tandai unit done HANYA setelah flush sukses."""
    if not pending:
        return
    for attempt in range(3):
        try:
            async with db.pool().connection() as conn:
                if bars:
                    await dukascopy.upsert_candles(conn, symbol, "M1", bars)
            break
        except Exception as exc:  # noqa: BLE001
            print(f"[{symbol}] flush DB gagal ({exc!r}) retry {attempt + 1}/3",
                  flush=True)
            await asyncio.sleep(5 * (attempt + 1))
    else:
        raise RuntimeError(f"{symbol}: flush DB gagal 3x - berhenti agar state konsisten")
    for key, status, _st2, nbars in pending:
        state.mark(symbol, key, status, nbars)
    pending.clear()
    bars.clear()


async def crawl_ticks(symbol: str, start_dt: datetime, end_dt: datetime,
                      state: StateLog, *, delay: float = 0.35,
                      attempts: int = 5, flush_bars: int = 3000,
                      limit_hours: int = 0) -> dict:
    """Crawl tick per jam (sekuensial, tanpa paralel) -> M1 -> upsert DB."""
    from app import db
    from paper import dukascopy

    div = PRICE_DIV.get(symbol, DEFAULT_DIV)
    hours = [h for h in hour_range(start_dt, end_dt)
             if state.done.get((symbol, str(h))) in (None, "fail")]
    if limit_hours:
        hours = hours[:limit_hours]
    n_total = len(hours)
    if not n_total:
        print(f"[{symbol}] semua jam sudah selesai (state) - tidak ada crawl",
              flush=True)
        return {"symbol": symbol, "hours": 0}
    print(f"[{symbol}] crawl {n_total} jam "
          f"{datetime.fromtimestamp(hours[0], tz=timezone.utc):%Y-%m-%d %H:%M}.."
          f"{datetime.fromtimestamp(hours[-1], tz=timezone.utc):%Y-%m-%d %H:%M} "
          f"UTC, delay {delay}s, attempts {attempts}", flush=True)

    client = KeepAliveClient()
    buffer: list[dict] = []
    pending: list[tuple[str, str, str, int]] = []
    n_ok = n_empty = n_fail = bars_total = 0
    t0 = time.time()
    try:
        for idx, h in enumerate(hours):
            status, raw = fetch_hour(client, symbol, h, attempts=attempts)
            bars = ticks_to_m1(h, raw, div) if status == "ok" else []
            n_ok += status == "ok"
            n_empty += status == "empty"
            n_fail += status == "fail"
            bars_total += len(bars)
            buffer.extend(bars)
            pending.append((str(h), status, status, len(bars)))
            if sum(p[3] for p in pending) >= flush_bars:
                await _flush_bars(db, dukascopy, symbol, buffer, state, pending)
            if (idx + 1) % 100 == 0 or idx + 1 == n_total:
                rate = (time.time() - t0) / (idx + 1)
                eta_m = rate * (n_total - idx - 1) / 60
                print(f"[{symbol}] {idx + 1}/{n_total} "
                      f"({(idx + 1) / n_total:.1%}) rate {rate:.2f}s/jam "
                      f"ETA {eta_m:.0f}m | bar {bars_total} | ok {n_ok} "
                      f"empty {n_empty} fail {n_fail} | "
                      f"{datetime.fromtimestamp(h, tz=timezone.utc):%Y-%m-%d %H:%M} UTC",
                      flush=True)
            if _stop_requested():
                print(f"[{symbol}] stop diminta, flush lalu keluar", flush=True)
                break
            time.sleep(delay)
        # sweep ulang jam yang fail (maks 1x) agar storm transient ter-tangkap
        failed = [int(k) for (s, k), st in state.done.items()
                  if s == symbol and k.isdigit() and st == "fail"]
        if failed and not _stop_requested():
            print(f"[{symbol}] sweep ulang {len(failed)} jam fail", flush=True)
            for h in failed:
                status, raw = fetch_hour(client, symbol, h, attempts=attempts)
                bars = ticks_to_m1(h, raw, div) if status == "ok" else []
                buffer.extend(bars)
                pending.append((str(h), status, status, len(bars)))
                if sum(p[3] for p in pending) >= flush_bars:
                    await _flush_bars(db, dukascopy, symbol, buffer, state, pending)
                time.sleep(delay)
    finally:
        await _flush_bars(db, dukascopy, symbol, buffer, state, pending)
        client.close()
    return {"symbol": symbol, "hours": n_total, "ok": n_ok, "empty": n_empty,
            "fail": n_fail, "bars": bars_total,
            "elapsed_s": round(time.time() - t0, 1)}


async def crawl_days(symbol: str, start_dt: datetime, end_dt: datetime,
                     state: StateLog, *, delay: float = 0.6,
                     attempts: int = 5, flush_bars: int = 3000,
                     fallback_hours: bool = True) -> dict:
    """Crawl candle m1 harian (1 request/hari, BID) -> upsert M1.

    24x lebih hemat request dibanding tick per jam; format & sisi BID sama
    dengan loader day-raw (paper/dukascopy.py). Hari empty (404 konsisten =
    tidak ada data) atau fail (habis retry) di-fallback ke crawl tick per jam
    untuk hari tsb agar gap terisi dari endpoint tick.
    """
    from app import db
    from paper import dukascopy

    div = PRICE_DIV.get(symbol, DEFAULT_DIV)
    days = [d for d in day_range(start_dt, end_dt)
            if state.done.get((symbol, f"d{datetime.fromtimestamp(d, tz=timezone.utc):%Y-%m-%d}"))
            in (None, "fail")]
    if not days:
        print(f"[{symbol}] semua hari sudah selesai (state) - tidak ada crawl",
              flush=True)
        return {"symbol": symbol, "days": 0}
    print(f"[{symbol}] crawl {len(days)} hari (day-candle) "
          f"{datetime.fromtimestamp(days[0], tz=timezone.utc):%Y-%m-%d}.."
          f"{datetime.fromtimestamp(days[-1], tz=timezone.utc):%Y-%m-%d} UTC, "
          f"delay {delay}s, attempts {attempts}", flush=True)

    client = KeepAliveClient()
    buffer: list[dict] = []
    pending: list[tuple[str, str, str, int]] = []
    missing: list[int] = []
    n_ok = n_empty = n_fail = bars_total = 0
    t0 = time.time()
    try:
        for idx, d in enumerate(days):
            status, raw = fetch_day(client, symbol, d, attempts=attempts)
            bars = day_bytes_to_m1(d, raw, div) if status == "ok" else []
            n_ok += status == "ok"
            n_empty += status == "empty"
            n_fail += status == "fail"
            if status in ("empty", "fail"):
                missing.append(d)
            bars_total += len(bars)
            buffer.extend(bars)
            pending.append((f"d{datetime.fromtimestamp(d, tz=timezone.utc):%Y-%m-%d}",
                            status, status, len(bars)))
            if sum(p[3] for p in pending) >= flush_bars:
                await _flush_bars(db, dukascopy, symbol, buffer, state, pending)
            if (idx + 1) % 10 == 0 or idx + 1 == len(days):
                rate = (time.time() - t0) / (idx + 1)
                eta_m = rate * (len(days) - idx - 1) / 60
                print(f"[{symbol}] hari {idx + 1}/{len(days)} "
                      f"({(idx + 1) / len(days):.1%}) rate {rate:.2f}s/hari "
                      f"ETA {eta_m:.0f}m | bar {bars_total} | ok {n_ok} "
                      f"empty {n_empty} fail {n_fail} | "
                      f"{datetime.fromtimestamp(d, tz=timezone.utc):%Y-%m-%d} UTC",
                      flush=True)
            if _stop_requested():
                print(f"[{symbol}] stop diminta, flush lalu keluar", flush=True)
                break
            time.sleep(delay)
    finally:
        await _flush_bars(db, dukascopy, symbol, buffer, state, pending)
    if fallback_hours and missing and not _stop_requested():
        print(f"[{symbol}] fallback tick per jam untuk {len(missing)} hari "
              f"empty/fail", flush=True)
        for d in missing:
            day_dt = datetime.fromtimestamp(d, tz=timezone.utc)
            await crawl_ticks(symbol, day_dt, day_dt + timedelta(days=1),
                              state, delay=delay, attempts=attempts,
                              flush_bars=flush_bars)
            if _stop_requested():
                break
    client.close()
    return {"symbol": symbol, "mode": "day-candle", "days": len(days),
            "ok": n_ok, "empty": n_empty, "fail": n_fail,
            "fallback_days": len(missing), "bars": bars_total,
            "elapsed_s": round(time.time() - t0, 1)}


async def crawl_bitstamp(symbol: str, start_dt: datetime, end_dt: datetime,
                         state: StateLog, *, delay: float = 0.15,
                         attempts: int = 5, flush_bars: int = 3000) -> dict:
    """Crawl candle M1 Bitstamp (BTC/USD asli) -> upsert DB.

    Dipakai untuk BTCUSD karena datafeed Dukascopy tidak menyediakan crypto
    (BTCUSD/ETHUSD/LTCUSD 404 di semua tahun; lihat bitstamp_client.py).
    Resume per hari: key "dYYYY-MM-DD" sama dengan state day-candle XAUUSD,
    jadi state satu format untuk semua sumber.
    """
    from app import db
    from paper import dukascopy
    from .bitstamp_client import BitstampClient, ohlc_range

    days = [d for d in day_range(start_dt, end_dt)
            if state.done.get((symbol, f"d{datetime.fromtimestamp(d, tz=timezone.utc):%Y-%m-%d}"))
            in (None, "fail")]
    if not days:
        print(f"[{symbol}] semua hari sudah selesai (state) - tidak ada crawl",
              flush=True)
        return {"symbol": symbol, "days": 0}
    print(f"[{symbol}] crawl {len(days)} hari (Bitstamp M1) "
          f"{datetime.fromtimestamp(days[0], tz=timezone.utc):%Y-%m-%d}.."
          f"{datetime.fromtimestamp(days[-1], tz=timezone.utc):%Y-%m-%d} UTC, "
          f"delay {delay}s", flush=True)

    client = BitstampClient()
    buffer: list[dict] = []
    pending: list[tuple[str, str, str, int]] = []
    bars_total = 0
    day_bars = 0
    t0 = time.time()
    try:
        for idx, d in enumerate(days):
            day_end = d + 86400
            for b in ohlc_range(client, symbol,
                                datetime.fromtimestamp(d, tz=timezone.utc),
                                datetime.fromtimestamp(day_end, tz=timezone.utc),
                                delay=delay, attempts=attempts):
                buffer.append(b)
                day_bars += 1
                bars_total += 1
                if len(buffer) >= flush_bars:
                    await _flush_bars(db, dukascopy, symbol, buffer, state, pending)
            # hari selesai (atau kosong) -> tandai done
            pending.append((f"d{datetime.fromtimestamp(d, tz=timezone.utc):%Y-%m-%d}",
                            "ok", "ok", day_bars))
            if len(buffer) >= flush_bars:
                await _flush_bars(db, dukascopy, symbol, buffer, state, pending)
            day_bars = 0
            if (idx + 1) % 14 == 0 or idx + 1 == len(days):
                rate = (time.time() - t0) / (idx + 1)
                eta_m = rate * (len(days) - idx - 1) / 60
                print(f"[{symbol}] hari {idx + 1}/{len(days)} "
                      f"({(idx + 1) / len(days):.1%}) rate {rate:.2f}s/hari "
                      f"ETA {eta_m:.0f}m | bar {bars_total} | "
                      f"{datetime.fromtimestamp(d, tz=timezone.utc):%Y-%m-%d} UTC",
                      flush=True)
            if _stop_requested():
                print(f"[{symbol}] stop diminta, flush lalu keluar", flush=True)
                break
    finally:
        await _flush_bars(db, dukascopy, symbol, buffer, state, pending)
        client.close()
    return {"symbol": symbol, "mode": "bitstamp-m1", "days": len(days),
            "bars": bars_total, "elapsed_s": round(time.time() - t0, 1)}


async def load_day_raw(symbol: str, raw_dir: Path, start_dt: datetime,
                       end_dt: datetime, state: StateLog,
                       *, flush_bars: int = 20000) -> dict:
    """Muat candle m1 harian dari raw bi5 existing (tanpa network) -> DB."""
    from app import db
    from paper import dukascopy

    div = PRICE_DIV.get(symbol, DEFAULT_DIV)
    files = sorted(p for p in Path(raw_dir).glob("*_bid.bi5")
                   if start_dt.date().isoformat() <= p.stem[:10]
                   < end_dt.date().isoformat())
    print(f"[{symbol}] day-raw: {len(files)} file di {raw_dir}", flush=True)
    buffer: list[dict] = []
    pending: list[tuple[str, str, str, int]] = []
    bars_total = corrupt = 0
    t0 = time.time()
    try:
        for p in files:
            date_iso = p.stem[:10]
            if state.done.get((symbol, f"d{date_iso}")) == "ok":
                continue
            try:
                bars = day_file_to_m1(p, div)
            except Exception as exc:  # noqa: BLE001
                print(f"[{symbol}] file korup {p.name}: {exc!r}", flush=True)
                corrupt += 1
                continue
            if bars:
                bars_total += len(bars)
                buffer.extend(bars)
                pending.append((f"d{date_iso}", "ok", "ok", len(bars)))
            if len(buffer) >= flush_bars:
                await _flush_bars(db, dukascopy, symbol, buffer, state, pending)
    finally:
        await _flush_bars(db, dukascopy, symbol, buffer, state, pending)
    first = files[0].stem[:10] if files else None
    last = files[-1].stem[:10] if files else None
    return {"symbol": symbol, "mode": "day-raw", "files": len(files),
            "corrupt": corrupt, "bars": bars_total, "first": first,
            "last": last, "elapsed_s": round(time.time() - t0, 1)}


_stop_flag = {"stop": False}


def _set_stop(signum, _frame) -> None:
    _stop_flag["stop"] = True


def _stop_requested() -> bool:
    return _stop_flag["stop"]


def install_signal_handlers() -> None:
    import signal
    signal.signal(signal.SIGTERM, _set_stop)
    signal.signal(signal.SIGINT, _set_stop)
