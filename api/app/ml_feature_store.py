"""Feature store offline P3 (t_f2p3a1): candle + likuiditas -> parquet.

Isi per bar XAUUSD M5 (point-in-time, bar close):
  - 29 fitur ml_features.compute_features (candle + likuiditas OHLC/context)
  - spread_duka: median spread per menit Dukascopy (raw bi5 lokal) dalam bar
  - tick_volume: volume candle DB (referensi; TIDAK jadi fitur model karena
    runner live mengirim volume 0 — lihat ml_features)

Fitur model = ml_features.FEATURE_NAMES (tanpa tick_volume/spread_duka).
Output: data/features/<SYMBOL>_<TF>.parquet

Run: .venv/bin/python -m app.ml_feature_store --symbol XAUUSD --tf M5
"""
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import db
from .ml_features import FEATURE_NAMES, MIN_BARS, compute_features
from paper.backtest import canonical_tf
from paper.dukascopy import load_m1, spread_series


def duka_spread_by_bar(series: list[tuple], tf_seconds: int) -> dict:
    """Median spread per menit -> per bar TF (bucket epoch // tf)."""
    buckets: dict[int, list[float]] = {}
    for t, sp in series:
        epoch = int(t.timestamp())
        buckets.setdefault(epoch - (epoch % tf_seconds), []).append(sp)
    from datetime import datetime as _dt
    return {_dt.fromtimestamp(k, tz=timezone.utc):
            float(sorted(v)[len(v) // 2]) for k, v in buckets.items()}


async def build_feature_store(symbol: str, tf: str, out_path: Path,
                              conn) -> dict:
    import pandas as pd

    tf = canonical_tf(tf)
    tf_seconds = {"M1": 60, "M5": 300, "M15": 900, "H1": 3600}[tf]
    db_tz = (await (await conn.execute(
        "SELECT current_setting('TimeZone') AS tz")).fetchone())["tz"]
    from paper.runner import db_timezone_offset_h
    from strategies.broker_time import broker_utc_offset_hours, stored_to_utc
    db_tz_offset_h = await db_timezone_offset_h(conn)
    rows = await (await conn.execute(
        "SELECT ts, open, high, low, close, volume FROM candles "
        "WHERE symbol = %s AND timeframe = %s ORDER BY ts ASC",
        (symbol, tf))).fetchall()
    candles = []
    for row in rows:
        wall = row["ts"]
        offset_h = broker_utc_offset_hours(wall)
        ts_utc = stored_to_utc(wall, db_tz_offset_h, offset_h)
        candles.append({"ts": ts_utc, "open": float(row["open"]),
                        "high": float(row["high"]), "low": float(row["low"]),
                        "close": float(row["close"]),
                        "volume": float(row["volume"] or 0.0)})
    # fitur batch (paritas dengan jalur per-bar decide() teruji di test suite)
    from .ml_features import compute_features_batch
    raw_dir = (Path(__file__).resolve().parent.parent.parent
               / "data" / "dukascopy" / "m1" / "raw")
    spread_by_bar: dict = {}
    if raw_dir.exists() and any(raw_dir.glob("*.bi5")):
        bid, ask = load_m1(raw_dir)
        series = spread_series(bid, ask)
        spread_by_bar = duka_spread_by_bar(series, tf_seconds)
    all_feats = compute_features_batch(
        candles, spread_fn=(lambda t: spread_by_bar.get(t)) if spread_by_bar else None)
    records = []
    for bar, feats in zip(candles, all_feats):
        feats["spread_duka"] = spread_by_bar.get(bar["ts"])
        feats["tick_volume"] = bar["volume"]
        feats["close"] = bar["close"]
        records.append(feats)
    df = pd.DataFrame(records, columns=["ts", *FEATURE_NAMES,
                                        "spread_duka", "tick_volume", "close"])
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out_path, index=False)
    return {"bars": len(df), "path": str(out_path),
            "first": df["ts"].iloc[0].isoformat(), "last": df["ts"].iloc[-1].isoformat(),
            "features": list(FEATURE_NAMES),
            "spread_bars_with_duka": int(df["spread_duka"].notna().sum())}


async def main() -> None:
    parser = argparse.ArgumentParser(description="Build feature store parquet (P3)")
    parser.add_argument("--symbol", default="XAUUSD")
    parser.add_argument("--tf", default="M5")
    parser.add_argument("--out", default="")
    args = parser.parse_args()
    out = Path(args.out) if args.out else (
        Path(__file__).resolve().parent.parent.parent / "data" / "features"
        / f"{args.symbol}_{canonical_tf(args.tf)}.parquet")
    await db.init_pool()
    async with db.pool().connection() as conn:
        info = await build_feature_store(args.symbol, args.tf, out, conn)
    await db.close_pool()
    print(info)


if __name__ == "__main__":
    asyncio.run(main())
