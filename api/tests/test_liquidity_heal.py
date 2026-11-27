"""Self-heal celah `liquidity_samples` dari parquet tick (app/liquidity_heal.py)."""
from datetime import datetime, timedelta, timezone

import pandas as pd

from app.liquidity_heal import heal_liquidity_gaps


def _iso_z(dt):
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _write_parquet(path, rows):
    for r in rows:
        if isinstance(r["ts_utc"], datetime):
            r["ts_utc"] = _iso_z(r["ts_utc"])
    pd.DataFrame(rows).to_parquet(path, index=False)


async def _insert(conn, symbol, ws, avg, cnt=10):
    await conn.execute(
        "INSERT INTO liquidity_samples "
        "(symbol, window_start, session, spread_avg, spread_min, spread_max, tick_count) "
        "VALUES (%s, %s, 'asia', %s, %s, %s, %s)",
        (symbol, ws, avg, avg, avg, cnt),
    )


async def test_heal_mengisi_celah_dari_parquet(tmp_path):
    """Celah 65 dtk diisi persis dari tick parquet, bukan dikarang."""
    t0 = datetime(2025, 1, 2, 1, 0, 0, tzinfo=timezone.utc)
    # tick tiap 5 dtk; jendela 01:00:00 dan 01:02:10 sudah ada di DB, sisanya
    # hilang karena restart, jadi harus direkonstruksi dari parquet.
    ticks = [{"ts_utc": t0 + timedelta(seconds=sec), "symbol": "BTCUSD",
              "bid": 1.0, "ask": 1.1, "spread": 0.10}
             for sec in range(0, 131, 5)]
    for i, t in enumerate(ticks):     # pasar bergerak: bukti bukan kutipan beku
        t["bid"] = 100.0 + i * 0.5
        t["ask"] = t["bid"] + 0.10
    _write_parquet(tmp_path / "ticks_2025-01-02.parquet", ticks)

    async with __import__("app.db", fromlist=["pool"]).pool().connection() as conn:
        await conn.execute(
            "DELETE FROM liquidity_samples WHERE symbol='BTCUSD' AND window_start >= %s",
            (t0 - timedelta(hours=1),))
        await _insert(conn, "BTCUSD", t0, 0.10, 2)
        await _insert(conn, "BTCUSD", t0 + timedelta(seconds=130), 0.12, 3)

        filled = await heal_liquidity_gaps(
            conn, parquet_dir=tmp_path, now=t0 + timedelta(hours=1), hours=2)
        assert filled > 0

        cur = await conn.execute(
            "SELECT window_start, spread_avg, tick_count FROM liquidity_samples "
            "WHERE symbol='BTCUSD' AND window_start >= %s ORDER BY window_start",
            (t0 - timedelta(hours=1),))
        rows = await cur.fetchall()

    starts = [r["window_start"] for r in rows]
    # tidak ada lagi delta > 60 dtk
    gaps = [b - a for a, b in zip(starts, starts[1:]) if (b - a).total_seconds() > 60]
    assert gaps == []
    assert len(rows) == 27  # 0..130 dtk, satu jendela per 5 dtk
    by_ts = {r["window_start"]: r for r in rows}
    # jendela yang sudah ada tidak diubah (DO NOTHING), termasuk tick_count-nya
    assert float(by_ts[t0]["spread_avg"]) == 0.10
    assert by_ts[t0]["tick_count"] == 2
    assert float(by_ts[t0 + timedelta(seconds=130)]["spread_avg"]) == 0.12
    # jendela hasil rekonstruksi memakai aturan _close_window
    assert float(by_ts[t0 + timedelta(seconds=60)]["spread_avg"]) == 0.10
    assert by_ts[t0 + timedelta(seconds=60)]["tick_count"] == 1


async def test_heal_idempoten_dan_tidak_menimpa_data_live(tmp_path):
    t0 = datetime(2025, 1, 2, 2, 0, 0, tzinfo=timezone.utc)
    ticks = [{"ts_utc": t0 + timedelta(seconds=s), "symbol": "XAUUSD",
              "bid": 2000.0 + i, "ask": 2000.5 + i, "spread": 0.5}
             for i, s in enumerate((60, 62, 64, 70, 130, 131))]
    _write_parquet(tmp_path / "ticks_2025-01-02.parquet", ticks)

    async with __import__("app.db", fromlist=["pool"]).pool().connection() as conn:
        await conn.execute(
            "DELETE FROM liquidity_samples WHERE symbol='XAUUSD' AND window_start >= %s",
            (t0 - timedelta(hours=1),))
        await _insert(conn, "XAUUSD", t0, 0.99, 1)
        await _insert(conn, "XAUUSD", t0 + timedelta(seconds=130), 0.42, 7)
        first = await heal_liquidity_gaps(
            conn, parquet_dir=tmp_path, now=t0 + timedelta(hours=2), hours=3)
        second = await heal_liquidity_gaps(
            conn, parquet_dir=tmp_path, now=t0 + timedelta(hours=2), hours=3)
        cur = await conn.execute(
            "SELECT spread_avg, tick_count FROM liquidity_samples "
            "WHERE symbol='XAUUSD' AND window_start=%s", (t0 + timedelta(seconds=130),))
        row = await cur.fetchone()

    assert first > 0
    assert second == 0                     # idempoten
    assert float(row["spread_avg"]) == 0.42  # data live menang
    assert row["tick_count"] == 7
