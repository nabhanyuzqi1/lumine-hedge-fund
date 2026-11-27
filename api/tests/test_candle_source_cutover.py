"""Tests: kolom ``candles.source`` + cutover GET /candles (kartu candle pipeline).

DoD:
- migrasi p016 additive: kolom source NOT NULL DEFAULT 'legacy' + index
  (symbol, timeframe, source, ts) ada di DB;
- GET /candles default hanya mengembalikan bar sumber baru dengan cutover per
  (symbol, timeframe): bar legacy yang ts-nya < bar baru pertama disembunyikan;
- seri yang belum punya bar sumber baru tetap menyajikan legacy (chart tidak
  kosong karena migrasi berjalan lebih dulu daripada penulis baru);
- include_legacy=1 = riset (semua sumber apa adanya), shape response sama;
- rollup menulis source='rollup', tidak menimpa source='ea', dan tidak
  membangun bar dari bar volume 0;
- rantai rollup kini mencapai H4 dan D1 (sebelumnya hanya M15/H1).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app import db, ingest

UTC = timezone.utc
T0 = datetime(2026, 11, 20, 10, 0, tzinfo=UTC)

SHAPE = {"symbol", "tf", "count", "candles"}
CANDLE_KEYS = {"ts", "open", "high", "low", "close", "volume"}


async def _insert(symbol, tf, ts, o, h, l, c, v, source=None):
    """Satu bar; source None = pakai DEFAULT kolom (jalur 'legacy')."""
    async with db.pool().connection() as conn:
        if source is None:
            await conn.execute(
                "INSERT INTO candles (symbol, timeframe, ts, open, high, low, close, volume) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                (symbol, tf, ts, o, h, l, c, v))
        else:
            await conn.execute(
                "INSERT INTO candles (symbol, timeframe, ts, open, high, low, close, "
                "volume, source) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (symbol, tf, ts, o, h, l, c, v, source))


async def _sources(symbol, tf):
    async with db.pool().connection() as conn:
        cur = await conn.execute(
            "SELECT ts FROM candles WHERE symbol=%s AND timeframe=%s ORDER BY ts",
            (symbol, tf))
        return [r["ts"] for r in await cur.fetchall()]


# ---------------------------------------------------------------- migrasi


async def test_source_column_and_index_exist():
    async with db.pool().connection() as conn:
        cur = await conn.execute(
            """
            SELECT column_default, is_nullable, data_type
            FROM information_schema.columns
            WHERE table_name = 'candles' AND column_name = 'source'
            """)
        col = await cur.fetchone()
        assert col is not None, "kolom candles.source tidak ada (migrasi p016 belum jalan)"
        assert col["is_nullable"] == "NO"
        assert "legacy" in str(col["column_default"])
        assert col["data_type"] == "text"
        cur = await conn.execute(
            "SELECT indexname FROM pg_indexes "
            "WHERE tablename = 'candles' AND indexname = 'idx_candles_source_ts'")
        assert await cur.fetchone() is not None, "index idx_candles_source_ts hilang"


async def test_existing_rows_default_to_legacy():
    await _insert("XAUUSD", "M5", T0, 2000, 2001, 1999, 2000.5, 3)
    async with db.pool().connection() as conn:
        cur = await conn.execute(
            "SELECT source FROM candles WHERE symbol='XAUUSD' AND timeframe='M5'")
        assert (await cur.fetchone())["source"] == "legacy"


# ---------------------------------------------------------------- cutover


async def test_cutover_hides_older_legacy_bars(client):
    """Legacy (volume 2-5) sebelum bar baru pertama tidak ikut chart default."""
    for i in range(5):  # legacy 10:00..10:20, volume kecil (kelas data lama)
        await _insert("XAUUSD", "M5", T0 + timedelta(minutes=5 * i),
                      2000, 2001, 1999, 2000.5, 3)
    for i in range(3):  # bar baru: native EA, volume besar
        await _insert("XAUUSD", "M5", T0 + timedelta(minutes=25 + 5 * i),
                      2100, 2102, 2099, 2101, 300 + i, source="ea")

    resp = await client.get("/candles", params={"symbol": "XAUUSD", "tf": "M5"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert set(body.keys()) == SHAPE
    assert body["count"] == 3, body
    assert all(set(c.keys()) == CANDLE_KEYS for c in body["candles"])
    assert [c["volume"] for c in body["candles"]] == [300.0, 301.0, 302.0]
    tss = [datetime.fromisoformat(c["ts"]) for c in body["candles"]]
    assert tss == sorted(tss) and len(set(tss)) == len(tss)


async def test_include_legacy_returns_every_source(client):
    for i in range(5):
        await _insert("XAUUSD", "M5", T0 + timedelta(minutes=5 * i),
                      2000, 2001, 1999, 2000.5, 3)
    await _insert("XAUUSD", "M5", T0 + timedelta(minutes=25),
                  2100, 2102, 2099, 2101, 300, source="ea")

    default = (await client.get(
        "/candles", params={"symbol": "XAUUSD", "tf": "M5"})).json()
    everything = (await client.get(
        "/candles", params={"symbol": "XAUUSD", "tf": "M5", "include_legacy": 1})).json()
    assert default["count"] == 1
    assert everything["count"] == 6
    assert set(everything.keys()) == SHAPE
    assert [c["volume"] for c in everything["candles"]] == [3.0] * 5 + [300.0]


async def test_legacy_only_series_still_served(client):
    """Belum ada bar sumber baru: cutover NULL -> legacy tetap tampil."""
    for i in range(4):
        await _insert("BTCUSD", "M15", T0 + timedelta(minutes=15 * i),
                      90000, 90010, 89990, 90005, 2)
    body = (await client.get("/candles", params={"symbol": "BTCUSD", "tf": "M15"})).json()
    assert body["count"] == 4


async def test_cutover_is_per_symbol_and_timeframe(client):
    """Cutover M5 XAUUSD tidak memotong seri BTCUSD maupun M15 XAUUSD."""
    await _insert("XAUUSD", "M5", T0, 2000, 2001, 1999, 2000.5, 3)
    await _insert("XAUUSD", "M5", T0 + timedelta(minutes=5), 2100, 2102, 2099, 2101, 300,
                  source="ea")
    await _insert("XAUUSD", "M15", T0, 2000, 2001, 1999, 2000.5, 2)
    await _insert("BTCUSD", "M5", T0, 90000, 90010, 89990, 90005, 2)

    xau_m5 = (await client.get("/candles", params={"symbol": "XAUUSD", "tf": "M5"})).json()
    xau_m15 = (await client.get("/candles", params={"symbol": "XAUUSD", "tf": "M15"})).json()
    btc_m5 = (await client.get("/candles", params={"symbol": "BTCUSD", "tf": "M5"})).json()
    assert xau_m5["count"] == 1
    assert xau_m15["count"] == 1
    assert btc_m5["count"] == 1


# ---------------------------------------------------------------- rollup


async def test_rollup_writes_source_and_respects_native_ea():
    """Rollup menulis 'rollup' dan TIDAK menimpa bar native EA di bucket sama."""
    bucket = T0  # 10:00 UTC (+shift 0 di env ini)
    for i in range(5):
        await _insert("XAUUSD", "M1", T0 + timedelta(minutes=i),
                      1 + i, 2 + i, 0.5 + i, 1.5 + i, 10, source="rollup")
    native_ts = bucket  # baris native EA di bucket M5 10:00
    await _insert("XAUUSD", "M5", native_ts, 555, 556, 554, 555.5, 999, source="ea")

    async with db.pool().connection() as conn:
        await ingest.rollup_m1_to_m5(conn, symbol="XAUUSD",
                                     since=T0, until=T0 + timedelta(minutes=5))
        cur = await conn.execute(
            "SELECT open, high, low, close, volume, source FROM candles "
            "WHERE symbol='XAUUSD' AND timeframe='M5' AND ts=%s", (native_ts,))
        row = await cur.fetchone()
    assert row is not None
    assert row["source"] == "ea", "bar native EA tertimpa rollup"
    assert float(row["volume"]) == 999.0


async def test_rollup_skips_zero_volume_source_bars():
    """Bar volume 0 (isi jendela tutup) tidak boleh naik ke M5."""
    for i in range(5):
        await _insert("XAUUSD", "M1", T0 + timedelta(minutes=i),
                      2000, 2000, 2000, 2000, 0)
    await _insert("XAUUSD", "M1", T0 + timedelta(minutes=6), 2001, 2003, 2000,
                  2002, 7)
    async with db.pool().connection() as conn:
        await ingest.rollup_m1_to_m5(conn, symbol="XAUUSD",
                                     since=T0, until=T0 + timedelta(minutes=7))
        cur = await conn.execute(
            "SELECT ts, volume, source FROM candles WHERE symbol='XAUUSD' "
            "AND timeframe='M5' ORDER BY ts")
        rows = await cur.fetchall()
    assert len(rows) == 1, [dict(r) for r in rows]  # bucket 10:00 seluruhnya volume 0
    assert float(rows[0]["volume"]) == 7.0
    assert rows[0]["source"] == "rollup"


async def test_rollup_chain_builds_h4_and_d1_from_h1():
    """H1 -> H4 dan H4 -> D1 (sebelumnya tidak pernah di-rollup)."""
    day = datetime(2026, 11, 20, 0, 0, tzinfo=UTC)
    async with db.pool().connection() as conn:
        for hour in range(24):
            await conn.execute(
                "INSERT INTO candles (symbol, timeframe, ts, open, high, low, close, "
                "volume, source) VALUES ('XAUUSD', 'H1', %s, %s, %s, %s, %s, %s, 'ea')",
                (day + timedelta(hours=hour), 100 + hour, 101 + hour, 99 + hour,
                 100.5 + hour, 50))
        h4 = await ingest._rollup_tf(conn, src_tf="H1", dst_tf="H4",
                                     seconds=ingest.H4_SECONDS,
                                     symbol="XAUUSD", since=day,
                                     until=day + timedelta(days=1))
        d1 = await ingest._rollup_tf(conn, src_tf="H4", dst_tf="D1",
                                     seconds=ingest.D1_SECONDS, symbol="XAUUSD",
                                     since=day, until=day + timedelta(days=1))
        cur = await conn.execute(
            "SELECT ts, open, high, low, close, volume, source FROM candles "
            "WHERE symbol='XAUUSD' AND timeframe='H4' ORDER BY ts")
        h4_rows = await cur.fetchall()
        cur = await conn.execute(
            "SELECT ts, volume, source FROM candles WHERE symbol='XAUUSD' "
            "AND timeframe='D1' ORDER BY ts")
        d1_rows = await cur.fetchall()
    assert h4 == 6 and len(h4_rows) == 6
    assert float(h4_rows[0]["open"]) == 100.0   # jam 00
    assert float(h4_rows[0]["close"]) == 103.5  # jam 03
    assert float(h4_rows[0]["volume"]) == 200.0
    assert {r["source"] for r in h4_rows} == {"rollup"}
    assert d1 == 1 and len(d1_rows) == 1
    assert float(d1_rows[0]["volume"]) == 1200.0
    assert d1_rows[0]["source"] == "rollup"


async def test_tick_bar_is_source_ea(tmp_path):
    p = ingest.reset_pipeline(parquet_dir=tmp_path)
    p.add_tick("XAUUSD", 1999.0, 1999.3)   # kutipan pertama: ditahan freeze guard
    p.add_tick("XAUUSD", 2000.0, 2000.3)   # harga bergerak: bar M1 lahir
    await p.flush_now()
    async with db.pool().connection() as conn:
        cur = await conn.execute(
            "SELECT source FROM candles WHERE symbol='XAUUSD' AND timeframe='M1'")
        row = await cur.fetchone()
    assert row is not None and row["source"] == "ea"
