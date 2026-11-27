"""Extended soak test Fund2 v2.2 (kartu rilis t_128a9dee, DevOps).

ISOLATED: boot app FastAPI in-process terhadap DB sekali pakai
(fund2_soak_<uuid>), TELEGRAM_ALERTS_OFF=1, tidak menyentuh DB/layanan live.

Berbeda dari scripts/load_soak_check.py (soak 30 s):
  - warmup terpisah,
  - durasi terukur panjang (default 360 s),
  - sampel RSS proses tiap 5 s (deteksi kebocoran memori),
  - p95 per menit (deteksi drift latensi bertahap),
  - kriteria lulus eksplisit.

Jalankan:
  cd ~/fund2/api && .venv/bin/python ../scripts/soak_extended.py \
      --duration 360 --concurrency 20
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import pathlib
import random
import statistics
import sys
import time
import uuid
from urllib.parse import urlsplit, urlunsplit

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "api"))
os.environ["TELEGRAM_ALERTS_OFF"] = "1"

import psycopg  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402

from app import config, db  # noqa: E402
from app.auth import hash_password  # noqa: E402
from app.main import app  # noqa: E402

DB_NAME = f"fund2_soak_{uuid.uuid4().hex[:8]}"
READ_PATHS = ["/positions", "/orders", "/kill-switch", "/strategies", "/auth/me"]


def _base_url(dbname: str) -> str:
    env_url = (os.environ.get("DATABASE_URL") or "").strip()
    if not env_url:
        env_path = pathlib.Path(__file__).resolve().parent.parent / "api" / ".env"
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line.startswith("DATABASE_URL="):
                env_url = line.split("=", 1)[1].strip()
                break
    if not env_url:
        raise RuntimeError("DATABASE_URL tidak ditemukan (env / api/.env)")
    parts = urlsplit(env_url)
    return urlunsplit((parts.scheme, parts.netloc, f"/{dbname}", parts.query, parts.fragment))


async def _make_db() -> None:
    conn = await psycopg.AsyncConnection.connect(_base_url("postgres"), autocommit=True)
    await conn.execute(f'CREATE DATABASE "{DB_NAME}"')
    await conn.close()


async def _drop_db() -> None:
    conn = await psycopg.AsyncConnection.connect(_base_url("postgres"), autocommit=True)
    await conn.execute(f'DROP DATABASE IF EXISTS "{DB_NAME}" WITH (FORCE)')
    await conn.close()


def percentile(xs: list[float], p: float) -> float:
    if not xs:
        return float("nan")
    xs = sorted(xs)
    k = max(0, min(len(xs) - 1, int(round(p / 100 * (len(xs) - 1)))))
    return xs[k]


def _rss_kb() -> int:
    try:
        pages = int(pathlib.Path("/proc/self/statm").read_text().split()[1])
        return pages * (os.sysconf("SC_PAGE_SIZE") // 1024)
    except Exception:  # noqa: BLE001
        return 0


async def _login() -> tuple[dict, str]:
    async with db.pool().connection() as conn:
        await conn.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (%s, %s, 'admin')",
            ("soakadmin", hash_password("soakpass")))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.post("/auth/login", json={"username": "soakadmin", "password": "soakpass"})
        assert r.status_code == 200, r.text
        return dict(c.cookies), r.json()["csrf_token"]


async def _hammer(cookies: dict, csrf: str, duration: float, concurrency: int,
                  buckets: dict[int, list[float]], counters: dict) -> None:
    stop = time.perf_counter() + duration
    sem = asyncio.Semaphore(concurrency)
    rng_seed = 20261125

    async def worker(wid: int) -> None:
        rng = random.Random(rng_seed + wid)
        i = 0
        async with AsyncClient(transport=ASGITransport(app=app),
                              base_url="http://test", cookies=cookies) as c:
            while time.perf_counter() < stop:
                t0 = time.perf_counter()
                pick = rng.random()
                try:
                    if pick < 0.60:
                        r = await c.get(rng.choice(READ_PATHS))
                    elif pick < 0.85:
                        r = await c.post("/bridge/tick", headers={"x-csrf-token": csrf},
                                         json={"symbol": "XAUUSD",
                                               "bid": 1999.80 + (i % 20) * 0.01,
                                               "ask": 2000.10 + (i % 20) * 0.01})
                    else:
                        r = await c.post("/orders", headers={"x-csrf-token": csrf},
                                         json={"symbol": "XAUUSD", "side": "BUY",
                                               "volume": 0.01, "sl": 1990.0, "tp": 2010.0})
                    counters["status"][r.status_code] = counters["status"].get(r.status_code, 0) + 1
                    if r.status_code >= 500:
                        counters["errors"] += 1
                except Exception as exc:  # noqa: BLE001
                    counters["errors"] += 1
                    counters["error_samples"].append(repr(exc)[:120])
                dt = (time.perf_counter() - t0) * 1000.0
                counters["sent"] += 1
                elapsed = duration - (stop - time.perf_counter())
                buckets.setdefault(int(elapsed // 60), []).append(dt)
                i += 1
                await asyncio.sleep(0.15)

    await asyncio.gather(*(worker(w) for w in range(concurrency)))


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--duration", type=float, default=360.0)
    ap.add_argument("--warmup", type=float, default=30.0)
    ap.add_argument("--concurrency", type=int, default=20)
    args = ap.parse_args()

    await _make_db()
    url = _base_url(DB_NAME)
    os.environ["DATABASE_URL"] = url
    config.DATABASE_URL = url
    try:
        await db.init_pool()
        await db.apply_schema()
        await db.seed_defaults()
        cookies, csrf = await _login()

        await _hammer(cookies, csrf, args.warmup, max(4, args.concurrency // 2),
                      {}, {"status": {}, "errors": 0, "sent": 0, "error_samples": []})

        buckets: dict[int, list[float]] = {}
        counters = {"status": {}, "errors": 0, "sent": 0, "error_samples": []}
        rss_samples: list[tuple[float, int]] = []
        t_start = time.perf_counter()
        rss0 = _rss_kb()
        sampler_stop = False

        async def sampler() -> None:
            while not sampler_stop:
                rss_samples.append((round(time.perf_counter() - t_start, 1), _rss_kb()))
                await asyncio.sleep(5)

        sampler_task = asyncio.create_task(sampler())
        await _hammer(cookies, csrf, args.duration, args.concurrency, buckets, counters)
        sampler_stop = True
        await sampler_task
        rss_end = _rss_kb()

        all_lat = [x for v in buckets.values() for x in v]
        per_min = []
        for minute in sorted(buckets):
            v = buckets[minute]
            per_min.append({"minute": minute + 1, "n": len(v),
                            "p50_ms": round(percentile(v, 50), 1),
                            "p95_ms": round(percentile(v, 95), 1),
                            "p99_ms": round(percentile(v, 99), 1)})
        first_p95 = per_min[0]["p95_ms"] if per_min else None
        last_p95 = per_min[-1]["p95_ms"] if per_min else None
        growth_pct = round((rss_end - rss0) / rss0 * 100, 1) if rss0 else None
        peak = max((r for _, r in rss_samples), default=rss_end)
        criteria = {
            "zero_5xx": counters["errors"] == 0,
            "rss_growth_le_20pct": growth_pct is not None and growth_pct <= 20.0,
            "p95_drift_le_1_5x": (first_p95 is not None and last_p95 is not None
                                  and last_p95 <= first_p95 * 1.5),
            "no_error_burst": counters["errors"] <= max(1, counters["sent"] // 10000),
        }
        report = {
            "phase": "extended_soak",
            "duration_s": args.duration,
            "warmup_s": args.warmup,
            "concurrency": args.concurrency,
            "requests": counters["sent"],
            "rps": round(counters["sent"] / args.duration, 1),
            "p50_ms": round(percentile(all_lat, 50), 1),
            "p95_ms": round(percentile(all_lat, 95), 1),
            "p99_ms": round(percentile(all_lat, 99), 1),
            "max_ms": round(max(all_lat), 1),
            "status_counts": counters["status"],
            "errors_5xx_or_exc": counters["errors"],
            "error_samples": counters["error_samples"][:5],
            "per_minute": per_min,
            "rss_kb_start": rss0,
            "rss_kb_end": rss_end,
            "rss_kb_peak": peak,
            "rss_growth_pct": growth_pct,
            "criteria": criteria,
            "passed": all(criteria.values()),
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "note": "in-process ASGITransport, isolated DB; bukan angka produksi",
        }
        out = pathlib.Path.home() / f"fund2/docs/QA_v22_soak_extended_{time.strftime('%Y%m%dT%H%M%SZ')}.json"
        out.write_text(json.dumps(report, indent=2))
        print(json.dumps(report, indent=2))
        print(f"saved: {out}")
    finally:
        await db.close_pool()
        await _drop_db()


if __name__ == "__main__":
    asyncio.run(main())
