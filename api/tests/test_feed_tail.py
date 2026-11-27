"""feed.read_ticks: baca EKOR file, bukan seluruh file (t_1b2d66ab).

Insiden 26 Nov 2026: `read_ticks` mem-parse seluruh log tick hari ini + kemarin
(±200 MB, ratusan ribu baris) secara SINKRON di event loop daemon alerts.
loop beku > 300 s -> watchdog `STALE` exit 70 (restart tiap ~5 menit) dan
`psycopg_pool.getconn()` yang antre di loop yang sama melempar `PoolTimeout`
palsu -> SEV-2 `db_unavailable` -> auto-halt `STOP_NEW_ORDERS`.

Berkas ini mengunci dua sifat yang membuat itu tidak terulang:
  1. biaya start dingin KONSTAN terhadap ukuran file (hanya window yang
     diminta yang diparse, dibuktikan lewat hitungan baris yang diparse,
     bukan cuma lewat waktu dinding yang bisa flaky),
  2. perilaku hasil tidak berubah: rentang waktu, filter simbol, rotasi
     tanggal, baris setengah jadi, file yang dipotong, dan window yang
     melebar setelah pembacaan pertama.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from paper import feed

DAY = datetime(2026, 11, 25, tzinfo=timezone.utc).date()
NOW = datetime(2026, 11, 25, 12, 0, tzinfo=timezone.utc)


def _line(ts: datetime, symbol: str = "XAUUSD", bid: float = 2000.0) -> str:
    return json.dumps({
        "ts_utc": ts.strftime("%Y-%m-%dT%H:%M:%S.") + f"{ts.microsecond // 1000:03d}Z",
        "exchange_ts": int(ts.timestamp() * 1000),
        "symbol": symbol,
        "bid": bid,
        "ask": bid + 0.5,
        "spread": 0.5,
    }) + "\n"


def _write(path, rows: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(rows))


def _recent_rows(now: datetime, minutes: int, *, step_s: int = 2,
                 symbol: str = "XAUUSD") -> list[str]:
    n = int(minutes * 60 / step_s)
    return [
        _line(now - timedelta(minutes=minutes) + timedelta(seconds=step_s * i), symbol)
        for i in range(n)
    ]


def _big_log(tmp_path, *, old_mb: int, now: datetime, recent_min: int = 20) -> Path:
    """Log berukuran `old_mb` MB berisi tick LAMA + `recent_min` menit tick baru."""
    path = tmp_path / "log" / f"ticks_{now.date().isoformat()}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    filler = (_line(now - timedelta(days=2)) * 2000).encode()
    with path.open("wb") as fh:
        written = 0
        target = old_mb * 1024 * 1024
        while written < target:
            fh.write(filler)
            written += len(filler)
        fh.write("".join(_recent_rows(now, recent_min)).encode())
    return path


def _count_parsed(monkeypatch) -> dict:
    """Hitung baris yang benar-benar diparse (bukti biaya, bebas flakiness)."""
    counter = {"n": 0}
    real = feed._parse_tick_line

    def counting(line):
        counter["n"] += 1
        return real(line)

    monkeypatch.setattr(feed, "_parse_tick_line", counting)
    return counter


# ------------------------------------------------------------ biaya konstan

def test_cold_read_tail_only_constant_cost_on_100mb_file(tmp_path, monkeypatch):
    """File >100 MB: start dingin <1 s dan hanya memparse ekor yang dibutuhkan."""
    monkeypatch.setattr(feed, "HFM_DIR", tmp_path)
    feed._TICK_CACHE.clear()
    path = _big_log(tmp_path, old_mb=110, now=NOW)
    assert path.stat().st_size > 100 * 1024 * 1024
    total_lines = path.stat().st_size  # ~700 ribu baris; cukup dibanding hitungan parse

    counter = _count_parsed(monkeypatch)
    t0 = time.perf_counter()
    ticks = feed.read_ticks(16, NOW, symbol="XAUUSD")
    elapsed = time.perf_counter() - t0

    assert len(ticks) == 16 * 60 // 2, len(ticks)
    assert all(t["ts_utc"] >= NOW - timedelta(minutes=16) for t in ticks)
    assert elapsed < 1.0, f"start dingin {elapsed:.2f}s (DoD: <1 s untuk >100 MB)"
    # 110 MB / ~150 B per baris ≈ 700 ribu baris. Yang diparse hanya blok batas
    # (<=512 KB) + window 16 menit (~480 baris).
    assert counter["n"] < 20_000, f"{counter['n']} baris diparse dari ~{total_lines} byte"


def test_cost_does_not_grow_with_file_size(tmp_path, monkeypatch):
    """Bandingkan file 110 MB vs file kecil: hasil sama, biaya parse sebanding."""
    monkeypatch.setattr(feed, "HFM_DIR", tmp_path)
    recent = _recent_rows(NOW, 20)

    big_dir = tmp_path / "big"
    big = _big_log(big_dir, old_mb=110, now=NOW)
    small_dir = tmp_path / "small"
    small = small_dir / "log" / f"ticks_{NOW.date().isoformat()}.jsonl"
    _write(small, recent)
    assert big.stat().st_size > 100 * 1024 * 1024 > small.stat().st_size

    monkeypatch.setattr(feed, "HFM_DIR", big_dir)
    feed._TICK_CACHE.clear()
    c_big = _count_parsed(monkeypatch)
    t0 = time.perf_counter()
    big_ticks = feed.read_ticks(16, NOW, symbol="XAUUSD")
    big_s = time.perf_counter() - t0

    monkeypatch.setattr(feed, "HFM_DIR", small_dir)
    feed._TICK_CACHE.clear()
    c_small = _count_parsed(monkeypatch)
    t0 = time.perf_counter()
    small_ticks = feed.read_ticks(16, NOW, symbol="XAUUSD")
    small_s = time.perf_counter() - t0

    assert [t["ts_utc"] for t in big_ticks] == [t["ts_utc"] for t in small_ticks]
    assert big_s < 1.0 and small_s < 1.0
    # Biaya start dingin tidak boleh meledak mengikuti ukuran file: beda
    # hitungan parse hanya sebesar blok batas (512 KB), bukan 700 ribu baris.
    assert c_big["n"] - c_small["n"] < 8_000, (c_big["n"], c_small["n"])


def test_fully_old_yesterday_file_is_skipped_cheaply(tmp_path, monkeypatch):
    """Log hari kemarin yang seluruhnya lebih tua dari window: sentuh ekor, lewati."""
    monkeypatch.setattr(feed, "HFM_DIR", tmp_path)
    feed._TICK_CACHE.clear()
    yesterday = NOW - timedelta(days=1)
    prev = tmp_path / "log" / f"ticks_{yesterday.date().isoformat()}.jsonl"
    filler = (_line(yesterday - timedelta(hours=6)) * 2000).encode()
    prev.parent.mkdir(parents=True, exist_ok=True)
    with prev.open("wb") as fh:
        for _ in range(120):  # ~36 MB, jam 06:00 kemarin (jauh di luar window)
            fh.write(filler)
    today = tmp_path / "log" / f"ticks_{NOW.date().isoformat()}.jsonl"
    _write(today, _recent_rows(NOW, 20))

    counter = _count_parsed(monkeypatch)
    t0 = time.perf_counter()
    ticks = feed.read_ticks(16, NOW, symbol="XAUUSD")
    elapsed = time.perf_counter() - t0

    assert len(ticks) == 16 * 60 // 2
    assert elapsed < 1.0, elapsed
    assert counter["n"] < 10_000, counter["n"]


# ------------------------------------------------------------------ perilaku

def test_window_expands_after_narrow_first_read(tmp_path, monkeypatch):
    """Baca 16 menit lalu 120 menit: window lebar tetap lengkap (rescan batas)."""
    monkeypatch.setattr(feed, "HFM_DIR", tmp_path)
    feed._TICK_CACHE.clear()
    path = tmp_path / "log" / f"ticks_{NOW.date().isoformat()}.jsonl"
    _write(path, _recent_rows(NOW, 180))

    narrow = feed.read_ticks(16, NOW, symbol="XAUUSD")
    wide = feed.read_ticks(120, NOW, symbol="XAUUSD")
    assert len(narrow) == 16 * 60 // 2
    assert len(wide) == 120 * 60 // 2
    assert wide[0]["ts_utc"] < narrow[0]["ts_utc"]


def test_symbol_filter_and_rotation_kept(tmp_path, monkeypatch):
    """Filter simbol + file berganti tanggal tetap bekerja dari pembacaan ekor."""
    monkeypatch.setattr(feed, "HFM_DIR", tmp_path)
    feed._TICK_CACHE.clear()
    now = datetime(2026, 11, 25, 0, 10, tzinfo=timezone.utc)  # dekat tengah malam UTC
    prev_day = now.date() - timedelta(days=1)
    _write(tmp_path / "log" / f"ticks_{prev_day.isoformat()}.jsonl",
           [_line(now - timedelta(minutes=14), "XAUUSD"),
            _line(now - timedelta(minutes=12), "BTCUSD")])
    _write(tmp_path / "log" / f"ticks_{now.date().isoformat()}.jsonl",
           [_line(now - timedelta(minutes=3), "XAUUSD"),
            _line(now - timedelta(minutes=2), "BTCUSD")])

    xau = feed.read_ticks(16, now, symbol="XAUUSD")
    assert [t["symbol"] for t in xau] == ["XAUUSD", "XAUUSD"]
    assert [t["ts_utc"] for t in xau] == sorted(t["ts_utc"] for t in xau)
    assert len(feed.read_ticks(16, now)) == 4


def test_partial_trailing_line_buffered_until_complete(tmp_path, monkeypatch):
    """Baris setengah jadi (EA sedang menulis) tidak diparse, lalu masuk saat lengkap."""
    monkeypatch.setattr(feed, "HFM_DIR", tmp_path)
    feed._TICK_CACHE.clear()
    path = tmp_path / "log" / f"ticks_{NOW.date().isoformat()}.jsonl"
    first = _recent_rows(NOW, 5, step_s=60)[:2]
    last = _recent_rows(NOW, 5, step_s=60)[2]
    _write(path, first + [last[: len(last) // 2]])

    assert len(feed.read_ticks(10, NOW, symbol="XAUUSD")) == 2
    with path.open("a") as fh:
        fh.write(last[len(last) // 2:])
    ticks = feed.read_ticks(10, NOW, symbol="XAUUSD")
    assert len(ticks) == 3
    assert ticks[-1]["ts_utc"] == NOW - timedelta(minutes=5) + timedelta(minutes=2)


def test_truncated_file_does_not_return_stale_ticks(tmp_path, monkeypatch):
    """File dipotong (rotasi/ganti isi) -> cache di-reset, tidak ada tick basi."""
    monkeypatch.setattr(feed, "HFM_DIR", tmp_path)
    feed._TICK_CACHE.clear()
    path = tmp_path / "log" / f"ticks_{NOW.date().isoformat()}.jsonl"
    _write(path, _recent_rows(NOW, 10, step_s=30, symbol="BTCUSD"))
    assert len(feed.read_ticks(11, NOW, symbol="BTCUSD")) == 20

    _write(path, _recent_rows(NOW, 2, step_s=30, symbol="XAUUSD"))
    ticks = feed.read_ticks(11, NOW, symbol="XAUUSD")
    assert len(ticks) == 4
    assert feed.read_ticks(11, NOW, symbol="BTCUSD") == []


def test_warm_read_is_incremental_and_returns_copy(tmp_path, monkeypatch):
    """Panggilan berikutnya hanya menambah tick baru; list hasil bukan cache."""
    monkeypatch.setattr(feed, "HFM_DIR", tmp_path)
    feed._TICK_CACHE.clear()
    path = tmp_path / "log" / f"ticks_{NOW.date().isoformat()}.jsonl"
    _write(path, _recent_rows(NOW, 5, step_s=60))
    first = feed.read_ticks(10, NOW, symbol="XAUUSD")
    assert len(first) == 5
    first.clear()
    assert len(feed.read_ticks(10, NOW, symbol="XAUUSD")) == 5

    with path.open("a") as fh:
        fh.write(_line(NOW + timedelta(seconds=30), "XAUUSD"))
    assert len(feed.read_ticks(10, NOW + timedelta(minutes=1), symbol="XAUUSD")) == 6


def test_missing_dir_and_empty_log_are_safe(tmp_path, monkeypatch):
    monkeypatch.setattr(feed, "HFM_DIR", tmp_path)
    feed._TICK_CACHE.clear()
    assert feed.read_ticks(16, NOW, symbol="XAUUSD") == []
    path = tmp_path / "log" / f"ticks_{NOW.date().isoformat()}.jsonl"
    path.parent.mkdir(parents=True)
    path.write_text("")
    assert feed.read_ticks(16, NOW, symbol="XAUUSD") == []
    path.write_text("bukan json sama sekali\n")
    assert feed.read_ticks(16, NOW, symbol="XAUUSD") == []
