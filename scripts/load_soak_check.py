"""Load/soak check level 8 (PRD 22.1.8) - ISOLATED, tidak menyentuh live.

Boots the fund2 FastAPI app in-process against its own throwaway Postgres DB
(fund2_load_<ts>), logs in an admin, then drives:
  Phase A (load)  : 2000 mixed requests, 20 concurrent workers.
  Phase B (soak)  : 30 s sustained tick writes + reads at ~50 req/s.
Reports p50/p95/p99 latency, error rate, and requests/s to stdout + JSON.

Run:
  cd ~/fund2/api && TELEGRAM_ALERTS_OFF=1 .venv/bin/python ../scripts/load_soak_check.py
"""
from __future__ import annotations

import asyncio
import json
import os
import pathlib
import random
import statistics
import sys
import time
import uuid

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "api"))

os.environ["TELEGRAM_ALERTS_OFF"] = "1"

import psycopg  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402

from app import config, db  # noqa: E402
from app.auth import hash_password  # noqa: E402
from app.main import app  # noqa: E402

DB_NAME = f"fund2_load_{uuid.uuid4().hex[:8]}"
N_REQUESTS = 2000
CONCURRENCY = 20
SOAK_SECONDS = 30.0


def _base_url(dbname: str) -> str:
    """Retarget DATABASE_URL dari api/.env ke <dbname> (pola conftest).

    URL (termasuk kredensial) dibaca dari .env di runtime, tidak di-hardcode:
    credential tidak boleh masuk repo/skrip.
    """
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
    from urllib.parse import urlsplit, urlunsplit
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


def _url() -> str:
    return _base_url(DB_NAME)


def percentile(xs: list[float], p: float) -> float:
    if not xs:
        return float("nan")
    xs = sorted(xs)
    k = max(0, min(len(xs) - 1, int(round(p / 100 * (len(xs) - 1)))))
    return xs[k]


async def _login() -> tuple[dict, str]:
    async with db.pool().connection() as conn:
        await conn.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (%s, %s, 'admin')",
            ("loadadmin", hash_password("loadpass")))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.post("/auth/login", json={"username": "loadadmin", "password": "loadpass"})
        assert r.status_code == 200, r.text
        return dict(c.cookies), r.json()["csrf_token"]


READ_PATHS = ["/positions", "/orders", "/kill-switch", "/strategies", "/auth/me"]


async def phase_load(cookies: dict, csrf: str) -> dict:
    lat: list[float] = []
    errors: list[str] = []
    statuses: dict[int, int] = {}
    sem = asyncio.Semaphore(CONCURRENCY)
    rng = random.Random(20261123)

    async def one(i: int) -> None:
        async with sem:
            pick = rng.random()
            async with AsyncClient(transport=ASGITransport(app=app),
                                   base_url="http://test", cookies=cookies) as c:
                t0 = time.perf_counter()
                try:
                    if pick < 0.70:
                        r = await c.get(rng.choice(READ_PATHS))
                    elif pick < 0.90:
                        r = await c.post("/bridge/tick", headers={"x-csrf-token": csrf},
                                         json={"symbol": "XAUUSD", "bid": 1999.85,
                                               "ask": 2000.15})
                    else:
                        r = await c.post("/orders", headers={"x-csrf-token": csrf},
                                         json={"symbol": "XAUUSD", "side": "BUY",
                                               "volume": 0.1, "sl": 1998.0, "tp": 2005.0})
                    statuses[r.status_code] = statuses.get(r.status_code, 0) + 1
                    if r.status_code >= 500:
                        errors.append(r.text[:120])
                except Exception as exc:  # noqa: BLE001
                    errors.append(repr(exc)[:120])
                    statuses[0] = statuses.get(0, 0) + 1
                lat.append((time.perf_counter() - t0) * 1000.0)

    t0 = time.perf_counter()
    await asyncio.gather(*(one(i) for i in range(N_REQUESTS)))
    wall = time.perf_counter() - t0
    return {
        "requests": N_REQUESTS,
        "concurrency": CONCURRENCY,
        "wall_s": round(wall, 2),
        "rps": round(N_REQUESTS / wall, 1),
        "p50_ms": round(percentile(lat, 50), 1),
        "p95_ms": round(percentile(lat, 95), 1),
        "p99_ms": round(percentile(lat, 99), 1),
        "max_ms": round(max(lat), 1),
        "status_counts": statuses,
        "errors_5xx_or_exc": len(errors),
        "error_samples": errors[:5],
    }


async def phase_soak(cookies: dict, csrf: str) -> dict:
    """Sustain tick writes + reads for SOAK_SECONDS; watch latency drift."""
    lat: list[float] = []
    errors = 0
    sent = 0
    stop = time.perf_counter() + SOAK_SECONDS

    async def worker(wid: int) -> None:
        nonlocal errors, sent
        async with AsyncClient(transport=ASGITransport(app=app),
                               base_url="http://test", cookies=cookies) as c:
            i = 0
            while time.perf_counter() < stop:
                t0 = time.perf_counter()
                try:
                    if i % 2 == 0:
                        r = await c.post("/bridge/tick", headers={"x-csrf-token": csrf},
                                         json={"symbol": "XAUUSD",
                                               "bid": 1999.85 + wid * 0.01,
                                               "ask": 2000.15 + wid * 0.01})
                    else:
                        r = await c.get("/positions")
                    if r.status_code >= 500:
                        errors += 1
                except Exception:  # noqa: BLE001
                    errors += 1
                sent += 1
                lat.append((time.perf_counter() - t0) * 1000.0)
                i += 1
                await asyncio.sleep(0.02)  # ~50 req/s per worker target

    await asyncio.gather(*(worker(w) for w in range(5)))
    half = len(lat) // 2
    first_half = statistics.mean(lat[:half]) if half else float("nan")
    second_half = statistics.mean(lat[half:]) if half else float("nan")
    return {
        "duration_s": SOAK_SECONDS,
        "requests": sent,
        "rps": round(sent / SOAK_SECONDS, 1),
        "p50_ms": round(percentile(lat, 50), 1),
        "p95_ms": round(percentile(lat, 95), 1),
        "p99_ms": round(percentile(lat, 99), 1),
        "errors_5xx_or_exc": errors,
        "latency_first_half_ms": round(first_half, 2),
        "latency_second_half_ms": round(second_half, 2),
        "latency_drift_ratio": round(second_half / first_half, 2) if first_half else None,
    }


async def main() -> None:
    await _make_db()
    url = _url()
    os.environ["DATABASE_URL"] = url
    config.DATABASE_URL = url
    try:
        await db.init_pool()
        await db.apply_schema()
        await db.seed_defaults()
        cookies, csrf = await _login()
        load = await phase_load(cookies, csrf)
        soak = await phase_soak(cookies, csrf)
        report = {"phase_load": load, "phase_soak": soak,
                  "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                  "note": "in-process ASGITransport, isolated DB, bukan angka produksi"}
        out = pathlib.Path.home() / "fund2/docs/QA_v22_load_soak.json"
        out.write_text(json.dumps(report, indent=2))
        print(json.dumps(report, indent=2))
        print(f"saved: {out}")
    finally:
        await db.close_pool()
        await _drop_db()


if __name__ == "__main__":
    asyncio.run(main())
