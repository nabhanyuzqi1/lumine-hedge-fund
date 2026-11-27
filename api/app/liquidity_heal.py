"""Self-heal celah `liquidity_samples` dari parquet tick milik ingest.

Kenapa modul ini ada
--------------------
Sampel spread per 5 detik hanya hidup di memori sampai flush DB (5 detik).
Restart API, backpressure (`BACKPRESSURE_S`), atau event loop yang tersendat
membuat sebagian jendela hilang. Celah > 60 detik dihitung metrik `gaps_1h`
dan memicu WARN di dashboard padahal tidak ada yang rusak di feed.

Tick mentahnya tetap tersimpan: `IngestPipeline._write_parquet_sync` menulis
`ticks_<YYYY-MM-DD>.parquet` (kolom ts_utc, symbol, bid, ask, spread) tiap
60 detik. Jadi jendela yang hilang bisa direkonstruksi persis dengan aturan
agregasi yang sama seperti `_agg_liquidity`/`_close_window`:

    window_start = floor(epoch / 5) * 5
    session      = session_of(tick UTC pertama di jendela)
    spread_avg   = rata-rata spread, 5 desimal
    spread_min/max, tick_count

Prinsip
-------
- Hanya menulis jendela yang BELUM ada (`ON CONFLICT DO NOTHING`), sehingga
  data live selalu menang dan modul ini idempoten.
- Berjalan sendiri: sekali saat start, lalu tiap `HEAL_INTERVAL_S` di loop
  ingest. Tanpa intervensi owner.
- Kegagalan apa pun hanya dicatat sebagai warning; ingest tidak boleh mati
  karena pemeliharaan data.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .ingest import LIQUIDITY_WINDOW_S, session_of

log = logging.getLogger("fund2.liquidity_heal")

GAP_MIN_S = 10.0          # > 2 jendela hilang: coba isi (metrik WARN di 60 dtk)
HEAL_HOURS = 6            # jendela pemeliharaan: 6 jam terakhir
HEAL_INTERVAL_S = 300     # tiap 5 menit di loop ingest
MAX_ROWS_PER_RUN = 5000  # batas baris per siklus, celah terbaru dulu


def _bucket(dt: datetime) -> int:
    return int(dt.timestamp() // LIQUIDITY_WINDOW_S) * LIQUIDITY_WINDOW_S


async def _existing_windows(conn, since: datetime,
                            until: datetime | None = None) -> dict[str, list[datetime]]:
    cur = await conn.execute(
        "SELECT symbol, window_start FROM liquidity_samples "
        "WHERE window_start >= %s AND (%s::timestamptz IS NULL OR window_start <= %s) "
        "ORDER BY symbol, window_start",
        (since, until, until),
    )
    out: dict[str, list[datetime]] = {}
    for row in await cur.fetchall():
        out.setdefault(row["symbol"], []).append(row["window_start"])
    return out


def _holes(windows: list[datetime], gap_s: float = GAP_MIN_S) -> list[tuple]:
    """Rentang (sesudah, sebelum) yang bolong, tanpa menyentuh ujung data."""
    holes = []
    for prev, cur in zip(windows, windows[1:]):
        if (cur - prev).total_seconds() > gap_s:
            holes.append((prev, cur))
    return holes


def _read_ticks(parquet_dir: Path, start: datetime, end: datetime) -> list[dict]:
    """Tick dari parquet harian yang menutup [start, end] (dibaca di thread)."""
    import pandas as pd

    # Normalisasi ke timezone.utc + datetime biasa. Timestamp Postgres datang
    # sebagai ZoneInfo('Asia/Pontianak'); pandas salah membandingkannya dengan
    # kolom datetime64[ns, UTC] dan hasilnya selalu kosong.
    start = datetime.fromtimestamp(start.timestamp(), tz=timezone.utc)
    end = datetime.fromtimestamp(end.timestamp(), tz=timezone.utc)
    frames = []
    day = start.date()
    while day <= end.date():
        p = parquet_dir / f"ticks_{day.isoformat()}.parquet"
        if p.exists():
            try:
                df = pd.read_parquet(p, columns=["ts_utc", "symbol", "spread", "bid"])
                frames.append(df)
            except Exception as exc:  # noqa: BLE001 — file korup: lewati
                log.warning("[liq-heal] parquet %s tidak terbaca: %s", p.name, exc)
        day += timedelta(days=1)
    if not frames:
        return []
    df = pd.concat(frames, ignore_index=True)
    # Parse ke datetime UTC (bukan banding string): format ts_utc bercampur
    # antar versi EA ("...Z" vs "+00:00") dan perbandingan string salah urut.
    df["ts_dt"] = pd.to_datetime(df["ts_utc"], utc=True, format="mixed", errors="coerce")
    df = df[(df["ts_dt"] >= start) & (df["ts_dt"] <= end)]
    rows = []
    for ts_dt, symbol, spread, bid in zip(df["ts_dt"], df["symbol"], df["spread"], df["bid"]):
        if pd.isna(ts_dt) or spread is None:
            continue
        rows.append({"ts": ts_dt.to_pydatetime().astimezone(timezone.utc),
                     "symbol": str(symbol), "spread": float(spread),
                     "bid": float(bid) if bid is not None else None})
    return rows


def _aggregate(ticks: list[dict]) -> dict[tuple, dict]:
    """Tick -> jendela 5 detik, aturan identik dengan `_close_window`."""
    buckets: dict[tuple, dict] = {}
    for t in ticks:
        key = (t["symbol"], _bucket(t["ts"]))
        b = buckets.get(key)
        if b is None:
            b = {"session": session_of(t["ts"]), "spreads": []}
            buckets[key] = b
        b["spreads"].append(t["spread"])
    out = {}
    for (symbol, ws), b in buckets.items():
        spreads = b["spreads"]
        out[(symbol, ws)] = {
            "symbol": symbol,
            "window_start": datetime.fromtimestamp(ws, tz=timezone.utc),
            "session": b["session"],
            "spread_avg": round(sum(spreads) / len(spreads), 5),
            "spread_min": min(spreads),
            "spread_max": max(spreads),
            "tick_count": len(spreads),
        }
    return out


async def heal_liquidity_gaps(conn, *, parquet_dir: Path | str | None = None,
                              now: datetime | None = None,
                              hours: float = HEAL_HOURS) -> int:
    """Isi celah `liquidity_samples` dari parquet tick. Kembalikan baris diisi."""
    from . import config

    now = now or datetime.now(timezone.utc)
    since = now - timedelta(hours=hours)
    exists = await _existing_windows(conn, since, now)
    spans: list[tuple[datetime, datetime]] = []
    for windows in exists.values():
        for prev, cur in _holes(windows):
            spans.append((prev + timedelta(seconds=LIQUIDITY_WINDOW_S),
                          cur - timedelta(seconds=LIQUIDITY_WINDOW_S)))
    if not spans:
        return 0
    pdir = Path(parquet_dir) if parquet_dir else Path(config.TICKS_PARQUET_DIR)
    start = min(s for s, _ in spans)
    end = max(e for _, e in spans)
    ticks = await asyncio.to_thread(_read_ticks, pdir, start, end)
    if not ticks:
        log.info("[liq-heal] %d celah terdeteksi, tidak ada tick parquet untuk "
                 "%s..%s", len(spans), start.isoformat(), end.isoformat())
        return 0
    # Pasar beku (kutipan EA diulang tanpa perubahan) bukan likuiditas: kalau
    # bid sama sekali tidak bergerak selama rentang celah, jangan diisi.
    moving = set()
    for sym in {t["symbol"] for t in ticks}:
        bids = [t["bid"] for t in ticks if t["symbol"] == sym and t["bid"] is not None]
        if bids and max(bids) != min(bids):
            moving.add(sym)
    rows = [r for r in _aggregate(ticks).values()
            if r["symbol"] in moving
            and any(s <= r["window_start"] <= e for s, e in spans)]
    if len(rows) > MAX_ROWS_PER_RUN:      # celah terbaru dulu, sisanya siklus berikut
        rows.sort(key=lambda r: r["window_start"], reverse=True)
        rows = rows[:MAX_ROWS_PER_RUN]
    if not rows:
        return 0
    cur = await conn.execute(
        "INSERT INTO liquidity_samples "
        "(symbol, window_start, session, spread_avg, spread_min, spread_max, tick_count) "
        "VALUES (%(symbol)s, %(window_start)s, %(session)s, %(spread_avg)s, "
        "%(spread_min)s, %(spread_max)s, %(tick_count)s) "
        "ON CONFLICT (symbol, window_start) DO NOTHING RETURNING 1",
        rows[0],
    )
    filled = len(await cur.fetchall())
    for row in rows[1:]:
        cur = await conn.execute(
            "INSERT INTO liquidity_samples "
            "(symbol, window_start, session, spread_avg, spread_min, spread_max, tick_count) "
            "VALUES (%(symbol)s, %(window_start)s, %(session)s, %(spread_avg)s, "
            "%(spread_min)s, %(spread_max)s, %(tick_count)s) "
            "ON CONFLICT (symbol, window_start) DO NOTHING RETURNING 1",
            row,
        )
        filled += len(await cur.fetchall())
    log.info("[liq-heal] %d celah, %d jendela dipulihkan dari parquet",
             len(spans), filled)
    return filled
