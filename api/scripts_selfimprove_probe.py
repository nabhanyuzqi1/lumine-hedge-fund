#!/usr/bin/env python3
"""Probe R2: muat M5 dari parquet snapshot Dukascopy (data P2 penuh),
jalankan walk-forward baseline vs kandidat min_sl_distance_usd=5.0.

t_f2p4a1 — self-improvement loop, percobaan pertama yang terukur.
"""
from __future__ import annotations

import asyncio
import json
import sys

sys.path.insert(0, "/home/tekka/fund2/api")

import pandas as pd  # noqa: E402
import pyarrow.parquet as pq  # noqa: E402

from app import db  # noqa: E402
from paper.backtest import to_utc_candles  # noqa: E402
from paper.walkforward import (  # noqa: E402
    PARAM_GRIDS,
    plan_windows,
    run_walkforward,
    write_report_rows,
)
from paper.dukascopy import build_dukascopy_cost_model  # noqa: E402
from strategies import london_breakout  # noqa: E402

CANDIDATE_GRID = {
    "breakout_buffer_usd": [0.10, 0.30],
    "rr": [1.0, 1.5, 2.0],
    "min_range_usd": [0.50, 1.00],
    "min_sl_distance_usd": [5.00],
}

PARQUET = "/home/tekka/fund2/data/dukascopy/snapshot/xauusd_m1_bid.parquet"


def load_m5_from_parquet(path: str) -> list[dict]:
    tbl = pq.read_table(path)
    df = tbl.to_pandas()
    print("parquet cols:", list(df.columns)[:10], "rows:", len(df), file=sys.stderr)
    ts_col = "ts"
    df[ts_col] = df[ts_col].str.slice(0, 19)
    df[ts_col] = pd.to_datetime(df[ts_col], format="%Y-%m-%dT%H:%M:%S")
    df = df.set_index(ts_col)
    agg = df.resample("5min", label="right", closed="right").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last"}).dropna()
    agg = agg.reset_index().rename(columns={ts_col: "ts"})
    agg["ts"] = agg["ts"].dt.tz_localize("UTC")
    candles = to_utc_candles(
        [{"ts": r.ts, "open": r.open, "high": r.high, "low": r.low, "close": r.close}
         for r in agg.itertuples()], db_tz_offset_h=0)
    return candles


async def main() -> None:
    candles = load_m5_from_parquet(PARQUET)
    start, end = candles[0]["ts"], candles[-1]["ts"]
    print(f"data {start} .. {end} bars={len(candles)}", file=sys.stderr)
    windows = plan_windows(start, end, train_months=6, test_months=1, step_months=1)
    print(f"windows={len(windows)}", file=sys.stderr)

    await db.init_pool()
    async with db.pool().connection() as conn:
        cost_model = await build_dukascopy_cost_model(conn)
        results = {}
        for label, grid in (
            ("baseline", PARAM_GRIDS["london_breakout"]),
            ("candidate", CANDIDATE_GRID),
        ):
            report = run_walkforward(
                candles, tf="M5", symbol="XAUUSD", windows=windows,
                grid=grid, equity0=10000.0, cost_model=cost_model,
                strategy=london_breakout, data_end=end)
            report["config"]["train_months"] = 6
            report["config"]["test_months"] = 1
            report["data"] = {"start": start.isoformat(), "end": end.isoformat(),
                              "bars": len(candles)}
            results[label] = report
            agg = report["aggregate"]
            print(f"{label}: net={agg['stitched_net_profit_usd']} "
                  f"dd={agg['stitched_max_drawdown_pct']} "
                  f"attempts={agg['total_attempts']} "
                  f"windows_profit={agg['windows_profitable']}/{agg['n_windows']}",
                  file=sys.stderr)
            written = await write_report_rows(conn, report)
            print(f"{label}: backtest_runs +{written} (run_id {report['run_id']})",
                  file=sys.stderr)
        with open("/home/tekka/fund2/docs/wf_selfimprove_r1_probe.json", "w") as fh:
            json.dump(results, fh, indent=1, default=str)
    await db.close_pool()


asyncio.run(main())
