"""Dukascopy m1 (BID/ASK bi5) -> spread series, candle agregat, upsert DB.

Sumber mentah: data/dukascopy/m1/raw/{YYYY-MM-DD}_{bid|ask}.bi5 dari
scripts/fetch_dukascopy_m1.py (LZMA-alone, record 24 byte, harga 1/1000 USD).

Fungsi:
  - load_m1(raw_dir)          -> (bid_rows, ask_rows) per epoch UTC
  - spread_series(bid, ask)   -> [(datetime UTC, spread)] per menit
  - aggregate(rows, tf)       -> candle OHLCV (sisi BID) per timeframe
  - upsert_candles()          -> INSERT ... ON CONFLICT DO UPDATE ke candles
"""
from __future__ import annotations

import lzma
import struct
from datetime import datetime, timedelta, timezone
from pathlib import Path

import psycopg

RECORD = struct.Struct(">iiiiif")
_TF_SECONDS = {"M1": 60, "M5": 300, "M15": 900, "H1": 3600, "H4": 14400, "D1": 86400}


def _parse_file(path: Path, day: datetime) -> list[tuple]:
    out = lzma.LZMADecompressor(lzma.FORMAT_ALONE).decompress(path.read_bytes())
    day0 = day.timestamp()
    rows = []
    for i in range(0, len(out) - len(out) % RECORD.size, RECORD.size):
        off, o, c, l, h, v = RECORD.unpack(out[i:i + RECORD.size])
        rows.append((day0 + off, o / 1000.0, c / 1000.0, l / 1000.0, h / 1000.0, v))
    return rows


def load_m1(raw_dir: Path) -> tuple[list[tuple], list[tuple]]:
    """Baca semua file raw; return (bid_rows, ask_rows) urut epoch."""
    raw_dir = Path(raw_dir)
    bid: list[tuple] = []
    ask: list[tuple] = []
    for path in sorted(raw_dir.glob("*.bi5")):
        stem = path.stem  # YYYY-MM-DD_bid
        date_part, _, side = stem.rpartition("_")
        if side not in ("bid", "ask"):
            continue
        day = datetime.strptime(date_part, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        rows = _parse_file(path, day)
        (bid if side == "bid" else ask).extend(rows)
    bid.sort(key=lambda r: r[0])
    ask.sort(key=lambda r: r[0])
    return bid, ask


def spread_series(bid: list[tuple], ask: list[tuple]) -> list[tuple[datetime, float]]:
    """Spread per menit = ask.close - bid.close (hanya menit dengan kedua sisi)."""
    ask_by_ts = {r[0]: r for r in ask}
    out = []
    for row in bid:
        other = ask_by_ts.get(row[0])
        if other is None:
            continue
        out.append((datetime.fromtimestamp(row[0], tz=timezone.utc),
                    round(other[2] - row[2], 4)))
    return out


def aggregate(rows: list[tuple], tf: str) -> list[dict]:
    """Agregasi baris m1 (epoch, o, c, l, h, v) sisi BID jadi candle TF."""
    sec = _TF_SECONDS[tf]
    buckets: dict[int, dict] = {}
    for epoch, o, c, l, h, v in rows:
        key = epoch - (epoch % sec)
        b = buckets.get(key)
        if b is None:
            buckets[key] = {"ts": datetime.fromtimestamp(key, tz=timezone.utc),
                            "open": o, "high": h, "low": l, "close": c, "volume": v}
        else:
            b["high"] = max(b["high"], h)
            b["low"] = min(b["low"], l)
            b["close"] = c
            b["volume"] = round(b["volume"] + v, 6)
    return [buckets[k] for k in sorted(buckets)]


async def ensure_partitions(conn, start: datetime, end: datetime) -> list[str]:
    """Pastikan partisi bulanan candles_YYYY_MM ada untuk rentang tertentu.

    Batas bulan mengikuti konvensi partisi yang sudah ada di DB: awal bulan
    zona +07 (Asia/Pontianak), bukan UTC.
    """
    made: list[str] = []
    wib = timezone(timedelta(hours=7))
    # candles bisa tabel biasa (deploy DB tertentu) -> tanpa partisi, upsert
    # langsung tetap sah. Jangan gagalkan ingest hanya karena parent bukan
    # partitioned (temuan t_f2p4a1: pg.errors.InvalidObjectDefinition).
    parent = await conn.execute(
        "SELECT relkind FROM pg_class WHERE relname = 'candles'")
    prow = await parent.fetchone()
    if prow is None or prow["relkind"] != "p":
        return made
    cur = start.astimezone(wib).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    end_wib = end.astimezone(wib)
    while cur <= end_wib:
        nxt = (cur.replace(month=cur.month % 12 + 1, year=cur.year + (cur.month == 12)))
        name = f"candles_{cur.year}_{cur.month:02d}"
        exists = await conn.execute(
            "SELECT 1 FROM pg_class WHERE relname = %s AND relkind = 'p'", (name,))
        if (await exists.fetchone()) is None:
            await conn.execute(
                f"CREATE TABLE IF NOT EXISTS {name} PARTITION OF candles "
                f"FOR VALUES FROM ('{cur.isoformat()}') TO ('{nxt.isoformat()}')")
            made.append(name)
        cur = nxt
    return made


async def upsert_candles(conn, symbol: str, tf: str, candles: list[dict]) -> int:
    """Tulis candle Dukascopy ke tabel candles (upsert per (symbol, tf, ts))."""
    if not candles:
        return 0
    await ensure_partitions(conn, candles[0]["ts"], candles[-1]["ts"])
    rows = [(symbol, tf, c["ts"], c["open"], c["high"], c["low"], c["close"], c["volume"])
            for c in candles]
    async with conn.cursor() as cur:
        await cur.executemany(
            """
            INSERT INTO candles (symbol, timeframe, ts, open, high, low, close, volume)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (symbol, timeframe, ts) DO UPDATE SET
                open = EXCLUDED.open, high = EXCLUDED.high, low = EXCLUDED.low,
                close = EXCLUDED.close, volume = EXCLUDED.volume
            """,
            rows)
    return len(rows)


def validate_candles(candles: list[dict], *, max_gap: timedelta | None = None) -> dict:
    """Sanity check: urut, tanpa duplikat, OHLC konsisten, rentang harga wajar."""
    problems: list[str] = []
    ts_list = [c["ts"] for c in candles]
    if ts_list != sorted(ts_list):
        problems.append("ts tidak urut")
    if len(set(ts_list)) != len(ts_list):
        problems.append("ts duplikat")
    bad_ohlc = sum(1 for c in candles
                   if not (c["low"] <= min(c["open"], c["close"])
                           and max(c["open"], c["close"]) <= c["high"]))
    if bad_ohlc:
        problems.append(f"{bad_ohlc} bar OHLC tidak konsisten")
    prices = [c["close"] for c in candles]
    if prices and (min(prices) < 100 or max(prices) > 10000):
        problems.append(f"harga di luar rentang wajar XAUUSD: {min(prices)}..{max(prices)}")
    if max_gap is not None:
        gaps = [(b["ts"] - a["ts"]).total_seconds()
                for a, b in zip(candles, candles[1:]) if (b["ts"] - a["ts"]) > max_gap]
        if gaps:
            problems.append(f"{len(gaps)} gap > {max_gap} (max {max(gaps) / 3600:.1f} jam)")
    return {"bars": len(candles), "problems": problems,
            "first": candles[0]["ts"].isoformat() if candles else None,
            "last": candles[-1]["ts"].isoformat() if candles else None}


# ---------------------------------------------------------------- cost model


async def build_dukascopy_cost_model(conn, *, raw_dir: Path | None = None,
                                     haircut: float | None = None,
                                     commission_per_lot: float | None = None,
                                     slippage_per_fill: float | None = None):
    """CostModel PRD 5.2 dari data lokal.

    - Median spread Dukascopy per sesi dari raw bi5 (data/dukascopy/m1/raw).
    - Median spread HFM per sesi dari liquidity_samples (DB).
    """
    from paper.costs import (  # lokal: hindari import melingkar saat test
        build_cost_model, duka_session_medians, hfm_session_medians,
    )
    raw_dir = raw_dir or (Path(__file__).resolve().parent.parent.parent
                          / "data" / "dukascopy" / "m1" / "raw")
    bid, ask = load_m1(raw_dir)
    series = spread_series(bid, ask)
    if not series:
        raise RuntimeError(f"tidak ada data m1 Dukascopy di {raw_dir}")
    duka_medians = duka_session_medians(series)
    rows = await conn.execute(
        "SELECT session, spread_avg FROM liquidity_samples WHERE symbol = %s",
        ("XAUUSD",))
    hfm_rows = await rows.fetchall()
    hfm_medians = hfm_session_medians([dict(r) for r in hfm_rows])
    kwargs = {}
    if haircut is not None:
        kwargs["haircut"] = haircut
    if commission_per_lot is not None:
        kwargs["commission_per_lot"] = commission_per_lot
    if slippage_per_fill is not None:
        kwargs["slippage_per_fill"] = slippage_per_fill
    model = build_cost_model(duka_medians, hfm_medians, **kwargs)
    model.notes.append(f"basis Dukascopy: {len(series)} menit spread "
                       f"({series[0][0]:%Y-%m-%d} .. {series[-1][0]:%Y-%m-%d})")
    return model
