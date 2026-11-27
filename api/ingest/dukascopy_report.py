"""Laporan crawler: resume state + preflight data quality (t_3c65f152)."""
from __future__ import annotations

import json
from pathlib import Path


def read_state(state_path: Path) -> dict:
    """Ringkas state JSONL: hit per status + total bar."""
    counts = {"ok": 0, "empty": 0, "fail": 0}
    bars = 0
    n = 0
    if not Path(state_path).exists():
        return {"counts": counts, "bars": 0, "units": 0}
    for line in Path(state_path).read_text(encoding="utf-8").splitlines():
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        st = rec.get("st", "fail")
        counts[st] = counts.get(st, 0) + 1
        bars += int(rec.get("bars", 0))
        n += 1
    return {"counts": counts, "bars": bars, "units": n}


async def cmd_summary(symbols: list[str], state_dir: Path) -> None:
    from app import db

    for symbol in symbols:
        st = read_state(Path(state_dir) / f"state_{symbol}.jsonl")
        print(f"== {symbol} ==")
        print(f"  state: {st}")
        async with db.pool().connection() as conn:
            cur = await conn.execute(
                "SELECT count(*) AS n, min(ts) AS first, max(ts) AS last "
                "FROM candles WHERE symbol = %s AND timeframe = 'M1'",
                (symbol,))
            row = await cur.fetchone()
        print(f"  DB M1: {row['n']} bar, {row['first']} .. {row['last']}")


async def cmd_preflight(symbol: str, out_dir: Path) -> dict:
    """Jalankan paper.preflight.run_preflight untuk seluruh M1 simbol di DB."""
    from app import db
    from paper.preflight import run_preflight

    async with db.pool().connection() as conn:
        # pg16 lokal gagal load llvmjit.so (libLLVM-17 tidak ada) saat planner
        # memilih JIT untuk query 1M+ bar -> matikan JIT di session ini saja.
        await conn.execute("SET jit = off")
        cur = await conn.execute(
            "SELECT ts, open, high, low, close, volume FROM candles "
            "WHERE symbol = %s AND timeframe = 'M1' ORDER BY ts",
            (symbol,))
        rows = await cur.fetchall()
    candles = [{"ts": r["ts"], "open": float(r["open"]),
                "high": float(r["high"]), "low": float(r["low"]),
                "close": float(r["close"]), "volume": float(r["volume"])}
               for r in rows]
    print(f"[{symbol}] memuat {len(candles)} bar M1 dari DB, jalankan preflight...",
          flush=True)
    report = run_preflight(candles, symbol=symbol, tf="M1")
    out = Path(out_dir) / f"preflight_{symbol}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"[{symbol}] overall: {report['overall_status']} "
          f"({report['bars']} bar) -> {out}")
    for name, c in report["checks"].items():
        print(f"  {name:16s} {c.get('status'):10s} {str(c.get('detail', ''))[:150]}")
    return report
