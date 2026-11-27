"""Tests: tidak ada bar M1 datar baru saat tick berhenti / pasar tutup.

Konteks bug live: 353.500 dari 1,086,155 bar M1 XAUUSD bernilai O=H=L=C
dengan volume 0 (32%), termasuk jendela 11-22 00:00-07:00 yang seluruhnya
datar pada harga 3538.17500. Penyebabnya tick-gap filler: kutipan terakhir
yang membeku digulung terus menjadi bar baru, tiap menit, sepanjang pasar
tutup. Bar datar itu lalu di-rollup ke M5/M15/H1 sehingga histogram volume
chart terlihat acak.

DoD perilaku:
- tick berhenti lama (>= FREEZE_TIMEOUT_S) dengan harga sama: TIDAK ada bar
  baru, bar terakhir dibiarkan utuh (volume/close aslinya dipertahankan);
- pasar CLOSED menurut laporan EA: TIDAK ada bar baru walau tick tetap masuk
  dengan harga membeku;
- saat tick pertama sesi baru datang dengan harga bergerak: bar baru lahir
  normal (open = harga baru), jadi tidak ada lubang yang menempel;
- penghitung bars_suppressed_closed naik sebagai bukti observabilitas.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app import ingest, kill_switch, market_status

UTC = timezone.utc


class _Clock:
    def __init__(self, start: datetime) -> None:
        self.t = start

    def __call__(self) -> datetime:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t = self.t + timedelta(seconds=seconds)


def _m1(p, symbol="XAUUSD"):
    return {k: v for k, v in p._candles.items() if k[0] == symbol and k[1] == "M1"}


@pytest.fixture(autouse=True)
def _clean_registry():
    market_status.clear()
    yield
    market_status.clear()
    kill_switch._ea_seen_mono = None


def _prime(p) -> None:
    """Kutipan pertama selalu ditahan freeze guard (belum ada pembanding)."""
    p.add_tick("XAUUSD", 1999.0, 1999.3)


def test_long_gap_with_frozen_price_creates_no_bar(tmp_path, monkeypatch):
    p = ingest.reset_pipeline(parquet_dir=tmp_path)
    clock = _Clock(datetime(2026, 11, 21, 10, 0, 10, tzinfo=UTC))
    monkeypatch.setattr(ingest, "utcnow", clock)
    _prime(p)
    p.add_tick("XAUUSD", 2000.0, 2000.3)          # bar 10:00 lahir
    assert len(_m1(p)) == 1
    p.add_tick("XAUUSD", 2000.5, 2000.8)          # masih menit yang sama
    before = dict(p._m1_current["XAUUSD"])

    clock.advance(ingest.FREEZE_TIMEOUT_S + 60)   # feed mati 11 menit
    p.add_tick("XAUUSD", 2000.5, 2000.8)          # harga sama persis (beku)
    assert len(_m1(p)) == 1, "bar datar baru dibuat dari kutipan beku"
    assert p._m1_current["XAUUSD"] == before, "bar terakhir sebelum jeda dirusak"
    assert p._m1_current["XAUUSD"]["close"] == 2000.5
    # Dua lapis penjaga, keduanya sah: freeze guard (> FREEZE_TIMEOUT_S) dan
    # supresi bar-datar milik agregator. Yang wajib: tidak ada bar baru.
    assert p.ticks_frozen_skipped + p.bars_suppressed_closed >= 1


def test_price_move_after_long_gap_opens_new_bar(tmp_path, monkeypatch):
    p = ingest.reset_pipeline(parquet_dir=tmp_path)
    clock = _Clock(datetime(2026, 11, 21, 10, 0, 10, tzinfo=UTC))
    monkeypatch.setattr(ingest, "utcnow", clock)
    _prime(p)
    p.add_tick("XAUUSD", 2000.0, 2000.3)
    clock.advance(ingest.FREEZE_TIMEOUT_S + 60)
    p.add_tick("XAUUSD", 2010.0, 2010.3)          # sesi baru: harga bergerak
    bars = _m1(p)
    assert len(bars) == 2
    newest = max(bars)
    assert bars[newest]["open"] == 2010.0
    assert bars[newest]["high"] == 2010.0
    assert bars[newest]["volume"] == 1


def test_closed_market_suppresses_new_bars_even_with_ticks(tmp_path, monkeypatch):
    """Pasar CLOSED (laporan EA): tick beku tidak lagi jadi bar baru."""
    p = ingest.reset_pipeline(parquet_dir=tmp_path)
    clock = _Clock(datetime(2026, 11, 21, 10, 0, 10, tzinfo=UTC))
    monkeypatch.setattr(ingest, "utcnow", clock)
    market_status.record_report(symbol="XAUUSD", market_status="CLOSED",
                                market_close_reason="session")
    _prime(p)
    p.add_tick("XAUUSD", 2000.0, 2000.3)
    assert len(_m1(p)) == 1

    for _ in range(3):                            # tiga menit tick beku berturut
        clock.advance(60)
        p.add_tick("XAUUSD", 2000.0, 2000.3)
    assert len(_m1(p)) == 1
    assert p.bars_suppressed_closed == 3
    assert p._m1_current["XAUUSD"]["close"] == 2000.0


def test_open_market_quiet_minute_still_records_bar(tmp_path, monkeypatch):
    """Pasar OPEN dan gap pendek: bar menit tetap sah (bukan filler)."""
    p = ingest.reset_pipeline(parquet_dir=tmp_path)
    clock = _Clock(datetime(2026, 11, 21, 10, 0, 10, tzinfo=UTC))
    monkeypatch.setattr(ingest, "utcnow", clock)
    market_status.record_report(symbol="XAUUSD", market_status="OPEN")
    _prime(p)
    p.add_tick("XAUUSD", 2000.0, 2000.3)
    clock.advance(61)
    p.add_tick("XAUUSD", 2000.0, 2000.3)          # sepi, harga tak bergerak
    assert len(_m1(p)) == 2
    assert p.bars_suppressed_closed == 0


async def test_suppressed_ticks_never_reach_db(tmp_path, monkeypatch):
    """Bar hantu dari kutipan beku tidak pernah lahir, jadi tidak pernah di-flush."""
    p = ingest.reset_pipeline(parquet_dir=tmp_path)
    clock = _Clock(datetime(2026, 11, 22, 3, 0, 10, tzinfo=UTC))
    monkeypatch.setattr(ingest, "utcnow", clock)
    market_status.record_report(symbol="XAUUSD", market_status="CLOSED",
                                market_close_reason="session")
    _prime(p)
    p.add_tick("XAUUSD", 3538.175, 3538.535)
    baseline = p.bars_suppressed_closed + p.ticks_frozen_skipped
    for _ in range(20):                       # 20 menit pasar tutup
        clock.advance(60)
        p.add_tick("XAUUSD", 3538.175, 3538.535)
    await p.flush_now()
    # 20 tick beku: sebagian ditahan supresi bar-datar (pasar CLOSED), sisanya
    # freeze guard setelah ambang FREEZE_TIMEOUT_S. Tidak satu pun jadi bar.
    assert p.bars_suppressed_closed + p.ticks_frozen_skipped - baseline == 20
    assert p.bars_suppressed_closed >= 1
    from app import db

    async with db.pool().connection() as conn:
        cur = await conn.execute(
            "SELECT count(*) AS n FROM candles WHERE symbol='XAUUSD' AND timeframe='M1'")
        row = await cur.fetchone()
    assert int(row["n"]) == 1, "bar datar pasar tutup ikut ter-flush ke DB"


def test_feed_age_s_tracks_live_ticks_only(tmp_path, monkeypatch):
    """feed_age_s hanya diperbarui tick yang lolos guard (bukan yang ditahan)."""
    p = ingest.reset_pipeline(parquet_dir=tmp_path)
    clock = _Clock(datetime(2026, 11, 21, 10, 0, 10, tzinfo=UTC))
    monkeypatch.setattr(ingest, "utcnow", clock)
    _prime(p)
    assert p.feed_age_s("XAUUSD") is None, "kutipan pertama bukan bukti feed hidup"
    p.add_tick("XAUUSD", 2000.0, 2000.3)
    age = p.feed_age_s("XAUUSD")
    assert age is not None and age >= 0
    assert p.feed_age_s("BTCUSD") is None


def test_quiet_feed_suppresses_flat_bars_before_freeze_timeout(tmp_path, monkeypatch):
    """Feed mengulang harga terakhir >= 2 menit: bar berikutnya tidak dibuat.

    Pasar OPEN (EA bilang buka) dan gap baru 3 menit — jauh di bawah
    FREEZE_TIMEOUT_S. Tetap tidak boleh lahir bar O=H=L=C: episode beku
    5 menit sebelumnya menghasilkan 5 bar kosong beruntun.
    """
    p = ingest.reset_pipeline(parquet_dir=tmp_path)
    clock = _Clock(datetime(2026, 11, 21, 10, 0, 10, tzinfo=UTC))
    monkeypatch.setattr(ingest, "utcnow", clock)
    market_status.record_report(symbol="XAUUSD", market_status="OPEN")
    _prime(p)
    p.add_tick("XAUUSD", 2000.0, 2000.3)          # harga bergerak di menit 10:00
    clock.advance(60)
    p.add_tick("XAUUSD", 2000.0, 2000.3)          # 10:01 sepi: bar sah
    assert len(_m1(p)) == 2
    clock.advance(60)
    p.add_tick("XAUUSD", 2000.0, 2000.3)          # 10:02: beku 120s -> ditahan
    clock.advance(60)
    p.add_tick("XAUUSD", 2000.0, 2000.3)          # 10:03: tetap ditahan
    assert len(_m1(p)) == 2, "bar kosong lahir dari kutipan beku"
    assert p.bars_suppressed_closed == 2


def _xau_sessions(hours=((360, 299),)) -> dict:
    """Jadwal XAU: tiap hari kerja buka 06:00, tutup 04:59 (WIB)."""
    rows = []
    for weekday in range(5):
        for open_minute, close_minute in hours:
            rows.append({
                "symbol": "XAUUSD", "weekday": weekday,
                "open_minute": open_minute, "close_minute": close_minute,
                "timezone": "Asia/Jakarta", "enabled": True,
            })
    return {"XAUUSD": rows}


def test_add_candles_drops_flat_seed_inside_closed_window(tmp_path):
    """Seed EA: bar kosong di jeda harian / akhir pekan tidak masuk antrean."""
    p = ingest.reset_pipeline(parquet_dir=tmp_path)
    p.set_session_rows(_xau_sessions())
    flat_break = {"symbol": "XAUUSD", "timeframe": "M1",
                  "ts": "2026-11-24T22:10:00Z",          # 05:10 WIB, pasar tutup
                  "open": 2000.0, "high": 2000.0, "low": 2000.0, "close": 2000.0,
                  "volume": 0}
    flat_weekend = {"symbol": "XAUUSD", "timeframe": "M1",
                    "ts": "2026-11-21T05:00:00Z",        # Sabtu 12:00 WIB
                    "open": 2001.0, "high": 2001.0, "low": 2001.0, "close": 2001.0,
                    "volume": 1}
    assert p.add_candles([flat_break, flat_weekend]) == 2
    assert _m1(p) == {}
    assert p.candles_closed_synthetic == 2


def test_add_candles_keeps_real_bar_and_open_hour_flat(tmp_path):
    """Bar bergerak di jendela tutup tetap diterima; bar flat jam buka juga sah."""
    p = ingest.reset_pipeline(parquet_dir=tmp_path)
    p.set_session_rows(_xau_sessions())
    moving_in_break = {"symbol": "XAUUSD", "timeframe": "M1",
                       "ts": "2026-11-24T22:10:00Z",     # 05:10 WIB tapi harga bergerak
                       "open": 2000.0, "high": 2001.5, "low": 1999.5, "close": 2001.0,
                       "volume": 12}
    flat_open = {"symbol": "XAUUSD", "timeframe": "M1",
                 "ts": "2026-11-24T02:00:00Z",           # 09:00 WIB, jam buka
                 "open": 2002.0, "high": 2002.0, "low": 2002.0, "close": 2002.0,
                 "volume": 0}
    assert p.add_candles([moving_in_break, flat_open]) == 0
    assert len(_m1(p)) == 2


def test_session_rows_missing_never_rejects(tmp_path):
    """Cache jadwal kosong (start awal / DB down): fail-open, tidak menebak."""
    p = ingest.reset_pipeline(parquet_dir=tmp_path)
    flat = {"symbol": "XAUUSD", "timeframe": "M1",
            "ts": "2026-11-24T22:10:00Z",
            "open": 2000.0, "high": 2000.0, "low": 2000.0, "close": 2000.0,
            "volume": 0}
    assert p.add_candles([flat]) == 0
    assert len(_m1(p)) == 1
