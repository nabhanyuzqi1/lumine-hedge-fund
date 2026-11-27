"""Data feeds for the paper runner: HFM tick log (spread + broker clock) and
Postgres candles (converted from broker time to true UTC)."""

from __future__ import annotations

import asyncio
import json
import os
import statistics
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

HFM_DIR = Path(os.environ.get("FUND2_HFM_DIR", Path.home() / "fund2/data/hfm_recording"))
BROKER_TS_FORMAT = "%Y.%m.%d %H:%M:%S"


def _parse_broker_ts(value: str) -> datetime:
    return datetime.strptime(value, BROKER_TS_FORMAT).replace(tzinfo=timezone.utc)


def _parse_exchange_ts(value) -> datetime:
    """exchange_ts EA v5 = epoch ms (TimeGMT, true UTC); EA v0 = string jam broker.

    Nilai None/invalid dilempar sebagai TypeError/ValueError agar baris itu
    dilewati pemanggil (perilaku sama seperti sebelumnya).
    """
    if isinstance(value, bool):
        raise TypeError("exchange_ts boolean tidak valid")
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(float(value) / 1000.0, tz=timezone.utc)
    return _parse_broker_ts(value)


_TICK_CACHE: dict[str, dict] = {}
_TICK_LOCK = threading.Lock()  # cache dipakai dari thread worker (asyncio.to_thread)
_TICK_TAIL_SLACK_MIN = 90  # simpan tick lebih lama dari window terbesar pemanggil
# Pindai ekor per blok (bukan baca seluruh file / 16 MB tetap): biaya start
# dingin sebanding window yang diminta, bukan ukuran file.
_SCAN_CHUNK_BYTES = 512 * 1024


def _parse_tick_line(line: str) -> dict | None:
    try:
        raw = json.loads(line)
        return {
            "symbol": raw.get("symbol"),
            "ts_utc": datetime.fromisoformat(str(raw["ts_utc"]).replace("Z", "+00:00")),
            "exchange_ts": _parse_exchange_ts(raw["exchange_ts"]),
            "bid": float(raw["bid"]),
            "ask": float(raw["ask"]),
            "spread": float(raw["spread"]),
        }
    except (KeyError, ValueError, TypeError, json.JSONDecodeError):
        return None


def _iter_block_lines(block: bytes, *, at_file_start: bool):
    """(offset_di_dalam_block, baris_bytes) untuk baris LENGKAP di `block`.

    Baris tanpa newline penutup (bisa jadi byte setengah jadi saat EA menulis)
    tidak pernah dihasilkan; pemanggil yang butuh baris terakhir menanganinya
    lewat buffer inkremental.
    """
    pos = 0
    if not at_file_start:
        nl = block.find(b"\n")
        if nl < 0:
            return
        pos = nl + 1
    while pos < len(block):
        nl = block.find(b"\n", pos)
        if nl < 0:
            return
        yield pos, block[pos:nl]
        pos = nl + 1


def _tick_ts(line: bytes) -> datetime | None:
    tick = _parse_tick_line(line.decode("utf-8", "ignore"))
    return tick["ts_utc"] if tick is not None else None


def _first_line_offset_at_or_after(path: Path, start: int, cutoff: datetime) -> int:
    """Offset baris pertama (mulai dari `start`) dengan ts_utc >= cutoff.

    Tidak ada baris yang memenuhi -> offset baris terakhir (bila file berakhir
    tanpa newline, offset awal baris setengah jadi itu) atau EOF. Offset yang
    dikembalikan SELALU awal baris, jadi pembaca inkremental tidak perlu
    membuang sisa baris.
    """
    with path.open("rb") as fh:
        if start > 0:
            fh.seek(start - 1)
            if fh.read(1) != b"\n":
                fh.seek(start)
                fh.readline()  # baris pertama terpotong offset lain: buang
        while True:
            line_start = fh.tell()
            raw = fh.readline()
            if not raw or not raw.endswith(b"\n"):
                return line_start
            ts = _tick_ts(raw)
            if ts is not None and ts >= cutoff:
                return line_start


def _tail_start_for(path: Path, cutoff: datetime) -> int:
    """Awal baris pertama yang mungkin berisi tick ts_utc >= cutoff.

    Pindai mundur per blok 512 KB dari EOF: berhenti di blok yang tick
    tertuanya sudah < cutoff, lalu cari baris batasnya. File 100 MB yang
    seluruhnya lebih tua dari cutoff (log hari kemarin) hanya menyentuh satu
    blok ekor lalu dilewati; sebelumnya seluruh file diparse tiap panggilan.
    """
    try:
        size = path.stat().st_size
    except OSError:
        return 0
    if size == 0:
        return 0
    cand = 0
    pos = size
    while pos > 0:
        start = max(0, pos - _SCAN_CHUNK_BYTES)
        try:
            with path.open("rb") as fh:
                fh.seek(start)
                block = fh.read(pos - start)
        except OSError:
            return 0
        oldest = None
        for _, line in _iter_block_lines(block, at_file_start=(start == 0)):
            oldest = _tick_ts(line)
            if oldest is not None:
                break
        if start == 0 or (oldest is not None and oldest < cutoff):
            cand = start
            break
        pos = start
    return _first_line_offset_at_or_after(path, cand, cutoff)


def _read_incremental(path: Path, cutoff: datetime, keep_after: datetime) -> list[dict]:
    """Baca HANYA byte baru sejak panggilan terakhir untuk file ini.

    Sebelumnya read_ticks mem-parse seluruh file hari ini + kemarin (±100-200
    MB, ratusan ribu baris) setiap panggilan, tiap 15 detik, per simbol: itu
    yang menahan ~60% CPU dan membuat host kehabisan CPU (insiden 26 Nov 2026).
    Sekarang file dibaca inkremental dari offset terakhir, dan start dingin
    mencari batas window dengan pindai mundur (bukan 16 MB tetap), sisa baris
    setengah jadi disimpan di buffer, tick lama dipangkas.

    `cutoff` = awal window yang diminta pemanggil; `keep_after` = batas
    retensi cache (lebih tua dari cutoff supaya panggilan berikutnya dengan
    window lebih lebar tidak perlu memindai ulang). Cache menyimpan
    `from_ts`: tick tertua yang dijamin ada; panggilan yang minta lebih tua
    dari itu memicu pemindaian ulang.
    """
    key = str(path)
    with _TICK_LOCK:
        st = _TICK_CACHE.get(key)
        try:
            info = path.stat()
        except OSError:
            return list(st["ticks"]) if st else []
        if (st is None or st["inode"] != info.st_ino
                or info.st_size < st["offset"] or st["from_ts"] > cutoff):
            start_at = _tail_start_for(path, cutoff)
            st = {"inode": info.st_ino, "offset": start_at, "buf": "",
                  "ticks": [], "from_ts": cutoff}
            _TICK_CACHE[key] = st
        if info.st_size > st["offset"]:
            try:
                with path.open("rb") as fh:
                    fh.seek(st["offset"])
                    chunk = fh.read()
            except OSError:
                return list(st["ticks"])
            st["offset"] += len(chunk)
            text = st["buf"] + chunk.decode("utf-8", "ignore")
            lines = text.split("\n")
            st["buf"] = lines.pop()  # baris terakhir bisa belum lengkap
            for line in lines:
                if not line:
                    continue
                tick = _parse_tick_line(line)
                if tick is not None:
                    st["ticks"].append(tick)
        if st["ticks"]:
            st["ticks"] = [t for t in st["ticks"] if t["ts_utc"] >= keep_after]
        st["from_ts"] = max(st["from_ts"], keep_after)
        return list(st["ticks"])


def read_ticks(minutes: int, now: datetime, symbol: str | None = None) -> list[dict]:
    """Tick HFM ``minutes`` menit terakhir (inkremental, bukan baca ulang file).

    Each item: ts_utc (aware UTC arrival), exchange_ts (aware UTC broker clock),
    bid, ask, spread, symbol. Files rotate per UTC date; today and yesterday
    are read. ``symbol`` membatasi ke satu simbol — wajib untuk pemakai
    keputusan (runner, watcher): log tick berisi beberapa simbol dan BTCUSD
    bergerak 24/7, tanpa filter "market buka" dan tick terakhir bisa berasal
    dari simbol lain (insiden t_86507d65: XAUUSD beku akhir pekan, BTCUSD
    tetap bergerak -> is_market_open selalu True dan tick konteks salah harga).
    """
    cutoff = now - timedelta(minutes=minutes)
    keep_after = now - timedelta(minutes=max(minutes, _TICK_TAIL_SLACK_MIN))
    out: list[dict] = []
    seen_files: set[Path] = set()
    for offset_days in (0, 1):
        day = (now - timedelta(days=offset_days)).date()
        path = HFM_DIR / "log" / f"ticks_{day.isoformat()}.jsonl"
        if path in seen_files or not path.exists():
            continue
        seen_files.add(path)
        for tick in _read_incremental(path, cutoff, keep_after):
            if tick["ts_utc"] < cutoff:
                continue
            if symbol is not None and tick["symbol"] != symbol:
                continue
            out.append(tick)
    out.sort(key=lambda t: t["ts_utc"])
    return out


async def read_ticks_async(minutes: int, now: datetime,
                           symbol: str | None = None) -> list[dict]:
    """`read_ticks` tanpa memblokir event loop (I/O file di thread worker).

    Wajib dipakai dari coroutine (alerts daemon, paper runner, shadow loop):
    pemanggilan sinkron menahan seluruh event loop selama baca+parse tick,
    sehingga watcher lain yang antre di loop yang sama kena PoolTimeout palsu
    dan memicu halt STOP_NEW_ORDERS (insiden 26 Nov 2026, t_1b2d66ab).
    """
    return await asyncio.to_thread(read_ticks, minutes, now, symbol)


def latest(ticks: list[dict]) -> dict | None:
    return ticks[-1] if ticks else None


def spread_median_15m(ticks: list[dict], now: datetime) -> float | None:
    window = [t for t in ticks if now - t["ts_utc"] <= timedelta(minutes=15)]
    if not window:
        return None
    return statistics.median(t["spread"] for t in window)


def is_market_open(ticks: list[dict], now: datetime, stall_s: int = 180) -> bool:
    """Open only while the broker clock advances AND quotes still move.

    Tick akhir pekan dari EA tetap datang tiap detik dan jam broker
    (TimeGMT) tetap berjalan, tapi harga beku di close Jumat — itu pasar
    tutup, bukan buka (insiden t_86507d65). Tanpa cek harga, runner dan
    watcher menganggap pasar buka sepanjang akhir pekan.
    """
    if not ticks:
        return False
    recent = [t for t in ticks if now - t["ts_utc"] <= timedelta(seconds=stall_s)]
    if len(recent) < 5:
        return False
    clocks = {t["exchange_ts"] for t in recent}
    if len(clocks) <= 1:
        return False
    prices = {t["bid"] for t in recent}
    return len(prices) > 1


def estimate_offset_hours(ticks: list[dict], min_pairs: int = 5) -> float | None:
    """Median (exchange_ts - arrival) in whole hours over advancing ticks.

    Hasilnya hanya valid bila jam exchange = jam wall broker (EA v0 kirim
    string TimeToString). EA v5 kirim epoch TimeGMT (true UTC) sehingga
    hasilnya ~0: itu jam exchange yang UTC-anchored, BUKAN offset wall
    broker yang dibutuhkan stored_to_utc untuk membaca candle. Kasus ~0
    dikembalikan sebagai None supaya pemakai jatuh ke asumsi A1'
    (UTC+7, terukur 2026-11-22)
    (broker_utc_offset_hours) — konvensi yang sama dengan engine backtest
    (paper/backtest.py to_utc_candles) supaya paritas tidak bergeser.
    """
    pairs = []
    for prev, cur in zip(ticks, ticks[1:]):
        if cur["exchange_ts"] == prev["exchange_ts"]:
            continue
        hours = (cur["exchange_ts"] - cur["ts_utc"]).total_seconds() / 3600.0
        pairs.append(hours)
    if len(pairs) < min_pairs:
        return None
    offset = float(round(statistics.median(pairs)))
    if abs(offset) < 0.5:
        return None  # jam exchange = jam kedatangan (UTC-anchored): tidak terukur
    return offset
