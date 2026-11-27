"""Penghitung request bridge EA (in-process, murah).

Dipakai untuk mengukur beban nyata EA ke API: berapa request/detik per
endpoint. Counter naik tanpa lock (GIL cukup untuk int += 1 di event loop
single-thread) dan dibaca lewat payload /admin metrics, jadi tidak perlu
menyalakan access log uvicorn yang mahal.
"""

from __future__ import annotations

import time

_START = time.time()

_COUNTERS: dict[str, int] = {
    "poll": 0,
    "tick": 0,
    "positions": 0,
    "result": 0,
    "heartbeat": 0,
}


def inc(name: str) -> None:
    _COUNTERS[name] = _COUNTERS.get(name, 0) + 1


def snapshot() -> dict:
    """Total per endpoint + rate rata-rata sejak proses hidup."""
    uptime = max(time.time() - _START, 1e-6)
    counts = dict(_COUNTERS)
    total = sum(counts.values())
    return {
        "counts": counts,
        "total": total,
        "uptime_s": round(uptime, 1),
        "avg_per_s": round(total / uptime, 3),
        "per_s": {k: round(v / uptime, 3) for k, v in counts.items()},
    }
