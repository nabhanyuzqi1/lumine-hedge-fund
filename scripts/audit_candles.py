# pyright: reportMissingImports=false
"""Audit kualitas seri candle (dipakai setelah worker selesai).

Jalankan: cd /home/tekka/fund2/api && .venv/bin/python /home/tekka/fund2/scripts/audit_candles.py
"""
import asyncio
import os
import sys

sys.path.insert(0, "/home/tekka/fund2/api")
os.chdir("/home/tekka/fund2/api")
from app import db  # noqa: E402

TF_SEC = {"M1": 60, "M5": 300, "M15": 900, "H1": 3600, "H4": 14400, "D1": 86400}


async def main() -> None:
    await db.init_pool()
    async with db.pool().connection() as conn:
        cur = await conn.execute(
            "select column_name from information_schema.columns "
            "where table_name='candles' and column_name='source'"
        )
        has_src = bool(await cur.fetchall())
        for sym in ("XAUUSD", "BTCUSD"):
            for tf in TF_SEC:
                src_col = ", source" if has_src else ""
                cur = await conn.execute(
                    f"select ts, open, high, low, close, volume{src_col} from candles "
                    "where symbol=%s and timeframe=%s order by ts desc limit 400",
                    (sym, tf),
                )
                rows = list(reversed(await cur.fetchall()))
                if not rows:
                    print(f"{sym:7} {tf:4} KOSONG")
                    continue
                flat = sum(
                    1
                    for r in rows
                    if r["open"] == r["high"] == r["low"] == r["close"]
                )
                vols = sorted(float(r["volume"] or 0) for r in rows)
                dup = len(rows) - len({r["ts"] for r in rows})
                gaps = [
                    (rows[i]["ts"] - rows[i - 1]["ts"]).total_seconds()
                    for i in range(1, len(rows))
                ]
                over = sum(1 for g in gaps if g > TF_SEC[tf] * 1.5)
                med = vols[len(vols) // 2]
                ratio = (vols[-1] / med) if med else float("inf")
                src = sorted({str(r["source"]) for r in rows}) if has_src else []
                print(
                    f"{sym:7} {tf:4} n={len(rows):4} flat={flat:3} dup={dup} "
                    f"gap>{TF_SEC[tf]}s={over:3} vol_med={med:7.0f} "
                    f"vol_max={vols[-1]:7.0f} ratio={ratio:6.1f} src={src}"
                )
    await db.close_pool()


if __name__ == "__main__":
    asyncio.run(main())
