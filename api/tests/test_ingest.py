"""Ingest pipeline (PRD 5.1, P1a hari 5-6): ring buffer -> parquet 60 dtk,
candle M1 dari tick, liquidity_samples per 5 dtk, backpressure."""
from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

import pandas as pd

from app import db, ingest


class _Clock:
    """utcnow palsu supaya uji rollover menit/jendela tanpa tidur."""

    def __init__(self, start: datetime) -> None:
        self.t = start

    def __call__(self) -> datetime:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t = self.t + timedelta(seconds=seconds)


def _force_close_windows(p: ingest.IngestPipeline) -> None:
    """Paksa jendela likuiditas terbuka dianggap lewat (waktu nyata)."""
    for w in p._liq_open.values():
        w["window_start"] = time.time() - 10


def _prime_quote(p: ingest.IngestPipeline, symbol: str = "XAUUSD") -> None:
    """Tick primer berbeda harga: ditahan freeze guard (kutipan pertama
    selalu ditahan sampai terlihat bergerak), jadi tidak masuk bar/likuiditas
    — test berikutnya bisa memakai ekspektasi agregasi penuh."""
    p.add_tick(symbol, 1999.0, 1999.3)


async def test_m1_aggregation_rolls_over(monkeypatch, tmp_path):
    p = ingest.reset_pipeline(parquet_dir=tmp_path)
    clock = _Clock(datetime(2026, 11, 21, 10, 0, 58, tzinfo=timezone.utc))
    monkeypatch.setattr(ingest, "utcnow", clock)
    _prime_quote(p)

    p.add_tick("XAUUSD", 2000.0, 2000.3)
    p.add_tick("XAUUSD", 2001.0, 2001.3)
    clock.t = datetime(2026, 11, 21, 10, 1, 1, tzinfo=timezone.utc)
    p.add_tick("XAUUSD", 2002.0, 2002.3)

    bars = {k: v for k, v in p._candles.items() if k[1] == "M1"}
    assert len(bars) == 2
    k0 = ("XAUUSD", "M1", datetime(2026, 11, 21, 10, 0, tzinfo=timezone.utc))
    k1 = ("XAUUSD", "M1", datetime(2026, 11, 21, 10, 1, tzinfo=timezone.utc))
    assert bars[k0]["open"] == 2000.0
    assert bars[k0]["close"] == 2001.0
    assert bars[k0]["high"] == 2001.0
    assert bars[k0]["low"] == 2000.0
    assert bars[k0]["volume"] == 2
    assert bars[k1]["volume"] == 1
    assert bars[k1]["open"] == 2002.0


async def test_bar_berjalan_m5_ikut_tick_dalam_bucket(monkeypatch, tmp_path):
    """Candle M5+ berjalan WAJIB memuat seluruh pergerakan bucket.

    EA hanya mengirim shift=0 sekali tepat setelah bucket berganti, jadi tanpa
    agregasi tick di server bar M5 membeku di harga pembukaan dan chart
    melompat ke posisi awal candle setiap refresh.
    """
    p = ingest.reset_pipeline(parquet_dir=tmp_path)
    clock = _Clock(datetime(2026, 11, 27, 1, 0, 58, tzinfo=timezone.utc))
    monkeypatch.setattr(ingest, "utcnow", clock)
    _prime_quote(p)

    p.add_tick("XAUUSD", 3560.82, 3561.12)
    clock.t = datetime(2026, 11, 27, 1, 1, 30, tzinfo=timezone.utc)
    p.add_tick("XAUUSD", 3567.15, 3567.45)
    clock.t = datetime(2026, 11, 27, 1, 3, 10, tzinfo=timezone.utc)
    p.add_tick("XAUUSD", 3557.55, 3557.85)
    clock.t = datetime(2026, 11, 27, 1, 4, 50, tzinfo=timezone.utc)
    p.add_tick("XAUUSD", 3563.24, 3563.54)

    m5 = p._candles[("XAUUSD", "M5",
                     datetime(2026, 11, 27, 1, 0, tzinfo=timezone.utc))]
    assert m5["source"] == ingest.SOURCE_LIVE
    assert m5["open"] == 3560.82
    assert m5["high"] == 3567.15, "high M5 harus memuat puncak tick bucket"
    assert m5["low"] == 3557.55, "low M5 harus memuat dasar tick bucket"
    assert m5["close"] == 3563.24
    assert m5["volume"] == 4

    m15 = p._candles[("XAUUSD", "M15",
                      datetime(2026, 11, 27, 1, 0, tzinfo=timezone.utc))]
    assert (m15["high"], m15["low"], m15["close"]) == (3567.15, 3557.55, 3563.24)


async def test_bar_berjalan_m5_berganti_bucket(monkeypatch, tmp_path):
    """Tick di bucket berikutnya membuka bar M5 baru, bukan menumbuhkan lama."""
    p = ingest.reset_pipeline(parquet_dir=tmp_path)
    clock = _Clock(datetime(2026, 11, 27, 1, 4, 55, tzinfo=timezone.utc))
    monkeypatch.setattr(ingest, "utcnow", clock)
    _prime_quote(p)
    p.add_tick("XAUUSD", 3560.0, 3560.3)
    clock.t = datetime(2026, 11, 27, 1, 5, 1, tzinfo=timezone.utc)
    p.add_tick("XAUUSD", 3561.0, 3561.3)

    first = p._candles[("XAUUSD", "M5",
                        datetime(2026, 11, 27, 1, 0, tzinfo=timezone.utc))]
    second = p._candles[("XAUUSD", "M5",
                         datetime(2026, 11, 27, 1, 5, tzinfo=timezone.utc))]
    assert first["close"] == 3560.0 and first["volume"] == 1
    assert second["open"] == 3561.0 and second["volume"] == 1


async def test_candle_bucket_berjalan_ditandai_live(monkeypatch, tmp_path):
    """Bar parsial EA (shift=0) harus 'live', bukan 'ea' yang kebal rollup.

    Kalau bar parsial tersimpan sebagai 'ea', rollup menolak menimpanya dan
    candle berjalan membeku di harga pembukaan sepanjang bucket.
    """
    p = ingest.reset_pipeline(parquet_dir=tmp_path)
    clock = _Clock(datetime(2026, 11, 27, 1, 7, 30, tzinfo=timezone.utc))
    monkeypatch.setattr(ingest, "utcnow", clock)

    def _bar(ts: str) -> dict:
        return {"symbol": "XAUUSD", "timeframe": "M5", "ts": ts,
                "open": 3560.0, "high": 3560.5, "low": 3559.5,
                "close": 3560.2, "volume": 12}

    p.add_candles([_bar("2026-11-27T01:05:00Z"), _bar("2026-11-27T01:00:00Z")])
    running = p._candles[("XAUUSD", "M5", "2026-11-27T01:05:00Z")]
    closed = p._candles[("XAUUSD", "M5", "2026-11-27T01:00:00Z")]
    assert running["source"] == ingest.SOURCE_LIVE
    assert closed["source"] == ingest.SOURCE_EA


async def test_candle_bucket_berjalan_m15_ditandai_live(monkeypatch, tmp_path):
    p = ingest.reset_pipeline(parquet_dir=tmp_path)
    clock = _Clock(datetime(2026, 11, 27, 1, 20, 0, tzinfo=timezone.utc))
    monkeypatch.setattr(ingest, "utcnow", clock)
    p.add_candles([{"symbol": "BTCUSD", "timeframe": "M15",
                    "ts": "2026-11-27T01:15:00Z", "open": 90000.0,
                    "high": 90010.0, "low": 89990.0, "close": 90005.0,
                    "volume": 5}])
    row = p._candles[("BTCUSD", "M15", "2026-11-27T01:15:00Z")]
    assert row["source"] == ingest.SOURCE_LIVE


async def test_m1_candle_flushes_to_db(tmp_path):
    p = ingest.reset_pipeline(parquet_dir=tmp_path)
    _prime_quote(p)
    p.add_tick("XAUUSD", 2000.0, 2000.3)
    _force_close_windows(p)
    await p.flush_now()
    async with db.pool().connection() as conn:
        cur = await conn.execute(
            "SELECT * FROM candles WHERE symbol='XAUUSD' AND timeframe='M1'")
        row = await cur.fetchone()
    assert row is not None
    assert float(row["open"]) == 2000.0
    assert row["volume"] == 1


async def test_liquidity_window_flushes_to_db(tmp_path):
    p = ingest.reset_pipeline(parquet_dir=tmp_path)
    _prime_quote(p)
    p.add_tick("XAUUSD", 2000.0, 2000.3)
    p.add_tick("XAUUSD", 2000.1, 2000.4)
    _force_close_windows(p)
    await p.flush_now()
    async with db.pool().connection() as conn:
        cur = await conn.execute(
            "SELECT * FROM liquidity_samples WHERE symbol='XAUUSD'")
        rows = await cur.fetchall()
    assert len(rows) == 1
    assert rows[0]["tick_count"] == 2
    assert float(rows[0]["spread_avg"]) == 0.3
    assert float(rows[0]["spread_min"]) == 0.3
    assert float(rows[0]["spread_max"]) == 0.3
    assert rows[0]["session"] in ("asia", "london", "london_newyork", "newyork")


async def test_backpressure_drops_liquidity_not_candles(tmp_path):
    p = ingest.reset_pipeline(parquet_dir=tmp_path)
    _prime_quote(p)
    p.add_tick("XAUUSD", 2000.0, 2000.3)
    _force_close_windows(p)
    w = next(iter(p._liq_open.values()))
    p._close_window("XAUUSD", w)
    del p._liq_open["XAUUSD"]
    p.add_candles([{"symbol": "XAUUSD", "timeframe": "M1",
                    "ts": "2026.11.21 10:00", "open": 2000, "high": 2001,
                    "low": 1999, "close": 2000.5, "volume": 4}])
    # simulasi siklus tulis sebelumnya lambat (> 5 dtk)
    p._last_write_duration = 10.0
    await p.flush_now()
    assert p.dropped_samples == 1
    async with db.pool().connection() as conn:
        cur = await conn.execute("SELECT count(*) AS n FROM liquidity_samples")
        assert (await cur.fetchone())["n"] == 0
        cur = await conn.execute(
            "SELECT count(*) AS n FROM candles WHERE timeframe='M1'")
        # 2 bar: 1 dari agregasi tick (add_tick) + 1 dari add_candles —
        # keduanya tetap ditulis walau backpressure (yang dibuang hanya
        # sampel likuiditas, bukan candle/event order).
        assert (await cur.fetchone())["n"] == 2


async def test_add_candles_normalizes_timeframe(tmp_path):
    p = ingest.reset_pipeline(parquet_dir=tmp_path)
    p.add_candles([
        {"symbol": "XAUUSD", "timeframe": "1m", "ts": "2026.11.21 10:00",
         "open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 3},
        {"symbol": "XAUUSD", "timeframe": "1h", "ts": "2026.11.21 10:00",
         "open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 3},
    ])
    assert {k[1] for k in p._candles} == {"M1", "H1"}


async def test_parquet_flush_writes_ticks(tmp_path):
    p = ingest.reset_pipeline(parquet_dir=tmp_path)
    p.add_tick("XAUUSD", 2000.0, 2000.3)
    p.add_tick("XAUUSD", 2000.1, 2000.4)
    await p.flush_now()
    files = list(tmp_path.glob("ticks_*.parquet"))
    assert len(files) == 1
    df = pd.read_parquet(files[0])
    assert len(df) == 2
    assert set(df["symbol"]) == {"XAUUSD"}
    assert df.iloc[0]["spread"] == 0.3
    assert p.parquet_rows_written == 2


async def test_tick_endpoint_does_not_write_db(tmp_path, monkeypatch):
    """Order path tidak pernah menunggu tulis tick: /bridge/tick murni
    memori; flush DB hanya di task latar belakang (diuji terpisah)."""
    p = ingest.reset_pipeline(parquet_dir=tmp_path)
    before = p.samples_written + p.candles_written
    p.add_tick("XAUUSD", 2000.0, 2000.3)
    assert p.ticks_buffered == 1
    assert p.samples_written + p.candles_written == before
    assert not list(tmp_path.glob("*.parquet"))  # belum flush


# ---------------------------------------------------------------- rollup M1->M5 (t_86507d65)

async def _insert_m1(conn, symbol, ts, o, h, l, c, v):
    """Bar M1 dengan kunci ts eksplisit true UTC (sebagai pipeline tick)."""
    await conn.execute(
        "INSERT INTO candles (symbol, timeframe, ts, open, high, low, close, volume) "
        "VALUES (%s, 'M1', %s, %s, %s, %s, %s, %s) ON CONFLICT DO NOTHING",
        (symbol, ts, o, h, l, c, v),
    )


def _nov(d, h, m=0):
    return datetime(2026, 11, d, h, m, tzinfo=timezone.utc)


async def test_rollup_m1_to_m5_uses_broker_base_key(tmp_path):
    """Kunci ts M5 = bucket true UTC + (offset broker A1' - offset tz DB) —
    server A1 = UTC+7 (terukur) = tz sesi DB, sama dengan seed EA/crawler,
    supaya runner & backtest membacanya benar (stored_to_utc)."""
    ingest.reset_pipeline(parquet_dir=tmp_path)
    async with db.pool().connection() as conn:
        db_tz = await ingest._db_tz_offset_h(conn)
        shift = timedelta(hours=7 - db_tz)  # A1' (terukur): server UTC+7 tetap
        # Konvensi MT5: bar M5 berlabel 10:00 berisi M1 10:00..10:04.
        for i in range(6):  # M1 true 10:00..10:05 -> bucket 10:00 & 10:05
            await _insert_m1(conn, "XAUUSD", _nov(21, 10, i),
                             1 + i, 2 + i, 0.5 + i, 1.5 + i, 10)
        n = await ingest.rollup_m1_to_m5(conn, since=_nov(21, 10, 0),
                                         until=_nov(21, 10, 6))
        assert n == 2
        cur = await conn.execute(
            "SELECT * FROM candles WHERE symbol='XAUUSD' AND timeframe='M5' ORDER BY ts")
        rows = await cur.fetchall()
    assert len(rows) == 2
    # bucket 10:00 = M1 10:00..10:04
    r0 = rows[0]
    assert r0["ts"] == _nov(21, 10, 0) + shift
    assert float(r0["open"]) == 1.0
    assert float(r0["high"]) == 6.0
    assert float(r0["low"]) == 0.5
    assert float(r0["close"]) == 5.5
    assert float(r0["volume"]) == 50.0
    # bucket 10:05 = M1 10:05 saja
    r1 = rows[1]
    assert r1["ts"] == _nov(21, 10, 5) + shift
    assert float(r1["open"]) == 6.0
    assert float(r1["close"]) == 6.5
    assert float(r1["volume"]) == 10.0


async def test_rollup_m1_to_m5_idempotent(tmp_path):
    """Rollup berulang tidak menduplikasi bar; nilai konvergen."""
    ingest.reset_pipeline(parquet_dir=tmp_path)
    async with db.pool().connection() as conn:
        for i in range(5):  # 10:00..10:04 -> satu bucket M5 10:00
            await _insert_m1(conn, "XAUUSD", _nov(21, 10, i), 1, 2, 0.5, 1.5, 7)
        await ingest.rollup_m1_to_m5(conn, since=_nov(21, 10, 0), until=_nov(21, 10, 6))
        await ingest.rollup_m1_to_m5(conn, since=_nov(21, 10, 0), until=_nov(21, 10, 6))
        cur = await conn.execute(
            "SELECT count(*) AS n FROM candles WHERE symbol='XAUUSD' AND timeframe='M5'")
        assert (await cur.fetchone())["n"] == 1
        cur = await conn.execute(
            "SELECT volume FROM candles WHERE symbol='XAUUSD' AND timeframe='M5'")
        assert float((await cur.fetchone())["volume"]) == 35.0


async def test_rollup_cycle_fills_gap_and_current_bucket(monkeypatch, tmp_path):
    """Siklus menutup gap sejak bar M5 terakhir + 1 bucket, dan window
    minimal 15 menit menjaga bucket berjalan tetap konvergen."""
    ingest.reset_pipeline(parquet_dir=tmp_path)
    monkeypatch.setattr(ingest, "utcnow",
                        _Clock(datetime(2026, 11, 21, 12, 0, tzinfo=timezone.utc)))
    async with db.pool().connection() as conn:
        db_tz = await ingest._db_tz_offset_h(conn)
        shift = timedelta(hours=7 - db_tz)
        # bar M5 lama: bucket true 11:30 (feed "mati" sejak itu)
        await conn.execute(
            "INSERT INTO candles (symbol, timeframe, ts, open, high, low, close, volume) "
            "VALUES ('XAUUSD', 'M5', %s, 1, 1, 1, 1, 1)",
            (_nov(21, 11, 30) + shift,))
        # M1 true 11:35..11:59 → bucket 11:35..11:55 (gap terisi)
        for minute in range(35, 60):
            await _insert_m1(conn, "XAUUSD", _nov(21, 11, minute), 1, 1, 1, 1, 2)
        n = await ingest.rollup_cycle(conn)
        # 5 bar M5 (gap 11:35..11:55 + berjalan) + 2 M15 (11:30, 11:45) +
        # 1 H1 (11:00) + 1 H4 (08:00, dari H1) + 1 D1 (dari H4) = 10
        assert n == 10
        cur = await conn.execute(
            "SELECT ts FROM candles WHERE symbol='XAUUSD' AND timeframe='M5' ORDER BY ts")
        keys = [r["ts"] for r in await cur.fetchall()]
    assert keys == [_nov(21, 11, m) + shift for m in (30, 35, 40, 45, 50, 55)]


async def test_rollup_cycle_writes_m15_h1(monkeypatch, tmp_path):
    """Tingkat lanjut M5->M15/H1 (t_f2mp3): bucket kanonik, idempotent."""
    ingest.reset_pipeline(parquet_dir=tmp_path)
    monkeypatch.setattr(ingest, "utcnow",
                        _Clock(datetime(2026, 11, 21, 12, 0, tzinfo=timezone.utc)))
    async with db.pool().connection() as conn:
        db_tz = await ingest._db_tz_offset_h(conn)
        shift = timedelta(hours=7 - db_tz)
        for minute in range(0, 60):  # M1 11:00..11:59 penuh
            await _insert_m1(conn, "XAUUSD", _nov(21, 11, minute), 1, 1, 1, 1, 2)
        await ingest.rollup_cycle(conn)
        await ingest.rollup_cycle(conn)  # idempotent: tidak duplikat
        for tf, n in (("M15", 4), ("H1", 1)):
            cur = await conn.execute(
                "SELECT ts FROM candles WHERE symbol='XAUUSD' AND timeframe=%s ORDER BY ts",
                (tf,))
            keys = [r["ts"] for r in await cur.fetchall()]
            assert keys == [_nov(21, 11, m) + shift for m in (0, 15, 30, 45)][:n], tf


async def test_flush_writes_m5_rollup(tmp_path, monkeypatch):
    """Flush pipeline menulis M1 hasil agregasi tick SEKALIGUS rollup M5-nya
    (kunci M5 mengikuti konvensi jam broker)."""
    p = ingest.reset_pipeline(parquet_dir=tmp_path)
    monkeypatch.setattr(ingest, "utcnow",
                        _Clock(datetime(2026, 11, 21, 12, 0, 58, tzinfo=timezone.utc)))
    _prime_quote(p)
    p.add_tick("XAUUSD", 2000.0, 2000.3)
    p.add_tick("XAUUSD", 2000.1, 2000.4)
    _force_close_windows(p)
    await p.flush_now()
    async with db.pool().connection() as conn:
        db_tz = await ingest._db_tz_offset_h(conn)
        shift = timedelta(hours=7 - db_tz)
        cur = await conn.execute(
            "SELECT ts, volume FROM candles WHERE symbol='XAUUSD' AND timeframe='M5'")
        row = await cur.fetchone()
    assert row is not None
    assert row["ts"] == _nov(21, 12, 0) + shift
    assert float(row["volume"]) == 2.0
    assert p.rollup_rows_written == 5  # M5 + M15 + H1 + H4 + D1 (rollup bertingkat)


# ---------------------------------------------------------------- freeze guard tick beku

async def test_add_tick_skips_frozen_quote_after_timeout(tmp_path, monkeypatch):
    """Kutipan beku > 10 menit (pasar tutup, EA resend) tidak menghasilkan bar."""
    p = ingest.reset_pipeline(parquet_dir=tmp_path)
    clock = _Clock(datetime(2026, 11, 22, 10, 0, tzinfo=timezone.utc))
    monkeypatch.setattr(ingest, "utcnow", clock)
    p.add_tick("XAUUSD", 3537.47, 3537.90)  # kutipan pertama: belum terverifikasi bergerak
    assert p.ticks_frozen_skipped == 1
    clock.advance(5)
    p.add_tick("XAUUSD", 3537.47, 3537.90)  # masih sama -> tetap ditahan
    assert p.ticks_frozen_skipped == 2
    assert "XAUUSD" not in p._m1_current  # tidak ada bar dari kutipan beku
    p.add_tick("XAUUSD", 3538.00, 3538.40)  # harga bergerak: mulai diagregasi
    assert p.ticks_frozen_skipped == 2
    assert p._m1_current["XAUUSD"]["volume"] == 1
    clock.advance(700)  # beku > 10 menit sejak perubahan terakhir
    p.add_tick("XAUUSD", 3538.00, 3538.40)
    assert p.ticks_frozen_skipped == 3
    # tidak ada bar M1 baru: bar berjalan tetap di menit 10:00, volume tak bertambah
    assert p._m1_current["XAUUSD"]["ts"] == datetime(2026, 11, 22, 10, 0, tzinfo=timezone.utc)
    assert p._m1_current["XAUUSD"]["volume"] == 1
    assert [k for k in p._candles if k[0] == "XAUUSD" and k[1] == "M1"] == [
        ("XAUUSD", "M1", datetime(2026, 11, 22, 10, 0, tzinfo=timezone.utc))]


async def test_first_ticks_after_restart_do_not_make_flat_bars(tmp_path, monkeypatch):
    """Regresi insiden 22 Nov 18:05 UTC: setelah restart proses, kutipan
    beku pasar tutup tidak lagi menghasilkan bar flat — agregasi baru
    jalan setelah perubahan harga pertama teramati."""
    p = ingest.reset_pipeline(parquet_dir=tmp_path)
    clock = _Clock(datetime(2026, 11, 22, 18, 5, tzinfo=timezone.utc))
    monkeypatch.setattr(ingest, "utcnow", clock)
    for i in range(600):  # ~10 menit tick beku 1x/dtk pasca-restart
        p.add_tick("XAUUSD", 3537.47, 3537.90)
        clock.advance(1)
    assert p.ticks_frozen_skipped == 600
    assert not [k for k in p._candles if k[0] == "XAUUSD"]
    p.add_tick("XAUUSD", 3539.10, 3539.50)  # pasar buka: harga bergerak
    assert p._m1_current["XAUUSD"]["volume"] == 1
    assert p._m1_current["XAUUSD"]["open"] == 3539.10


async def test_frozen_quote_resumes_on_price_change(tmp_path, monkeypatch):
    p = ingest.reset_pipeline(parquet_dir=tmp_path)
    clock = _Clock(datetime(2026, 11, 22, 10, 0, tzinfo=timezone.utc))
    monkeypatch.setattr(ingest, "utcnow", clock)
    p.add_tick("XAUUSD", 100.0, 100.5)  # kutipan pertama ditahan
    assert p.ticks_frozen_skipped == 1
    p.add_tick("XAUUSD", 100.5, 101.0)  # berubah -> mulai diagregasi
    assert p.ticks_frozen_skipped == 1
    clock.advance(700)
    p.add_tick("XAUUSD", 100.5, 101.0)  # beku -> skip
    assert p.ticks_frozen_skipped == 2
    p.add_tick("XAUUSD", 101.0, 101.5)  # harga berubah -> reset timer, ditulis
    assert p.ticks_frozen_skipped == 2
    clock.advance(700)
    p.add_tick("XAUUSD", 101.0, 101.5)  # beku lagi (timer sudah di-reset saat perubahan)
    assert p.ticks_frozen_skipped == 3


async def test_frozen_quote_is_per_symbol(tmp_path, monkeypatch):
    p = ingest.reset_pipeline(parquet_dir=tmp_path)
    clock = _Clock(datetime(2026, 11, 22, 10, 0, tzinfo=timezone.utc))
    monkeypatch.setattr(ingest, "utcnow", clock)
    p.add_tick("XAUUSD", 3537.47, 3537.90)  # kutipan pertama XAUUSD ditahan
    p.add_tick("BTCUSD", 61314.35, 61353.35)  # kutipan pertama BTCUSD ditahan
    assert p.ticks_frozen_skipped == 2
    p.add_tick("XAUUSD", 3538.00, 3538.40)  # XAUUSD bergerak -> agregasi
    p.add_tick("BTCUSD", 61314.35, 61353.35)  # BTCUSD masih sama -> tetap ditahan
    assert p.ticks_frozen_skipped == 3
    assert p._m1_current["XAUUSD"]["volume"] == 1
    assert "BTCUSD" not in p._m1_current
