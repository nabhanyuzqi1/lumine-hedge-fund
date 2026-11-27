"""Loader candle read-only untuk backtest riset Hermes (sisi parent).

Parent-lah yang membaca DB (sandbox child tidak punya akses DB/jaringan):
ambil candle pada window, konversi ke UTC dengan konvensi yang SAMA dengan
paper.backtest (to_utc_candles), lalu kirim sebagai ISO string ke sandbox.
"""
from __future__ import annotations

from datetime import datetime

from . import db
from paper.backtest import canonical_tf, to_utc_candles
from paper.runner import db_timezone_offset_h


async def load_candles(symbol: str, timeframe: str, start: datetime,
                       end: datetime, limit: int) -> list[dict]:
    """Return candle UTC ISO oldest-first untuk window [start, end]."""
    async with db.pool().connection() as conn:
        offset_h = await db_timezone_offset_h(conn)
        rows = await conn.execute(
            """
            SELECT ts, open, high, low, close FROM candles
            WHERE symbol = %s AND timeframe = %s AND ts >= %s AND ts <= %s
            ORDER BY ts ASC LIMIT %s
            """,
            (symbol, canonical_tf(timeframe), start, end, limit),
        )
        data = await rows.fetchall()
    candles = to_utc_candles(data, offset_h)
    return [
        {"ts": c["ts"].isoformat(), "open": c["open"], "high": c["high"],
         "low": c["low"], "close": c["close"]}
        for c in candles
    ]
