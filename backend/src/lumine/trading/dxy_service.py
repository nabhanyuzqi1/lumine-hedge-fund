"""DXY (US Dollar Index) service (18 Aug 2026).

User request: "kalau bisa streaming harga DX bagus lagi karna bahan untuk ke
LLM lebih banyak variabel". DXY adalah proxy USD — hubungan invers dengan
XAUUSD (emas dihargai dalam USD). Worker `_dxy_worker` fetch tiap 60s dari
API publik (tanpa key), cache Redis `lumine:dxy`, analyst prompt baca per
cycle + NewsRoom tampil.

Sumber (publik, tanpa key, diuji dari VPS):
1. https://carte.forexprosstatic.com/... (investing) - tidak stabil
2. https://api.frankfurter.app (EUR centric, bukan DXY langsung)
3. Stooq CSV: https://stooq.com/q/l/?s=dx.f&f=sd2t2ohlcv&h&e=csv - DX futures
Fallback: sintetis dari EURUSD tick (DXY = 50.14 * EURUSD^-0.576 * ...)
terlalu kompleks) → pakai invers sederhana sebagai proxy kasar dengan label
"synthetic".
"""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger("lumine.trading.dxy")

CACHE_KEY = "lumine:dxy"
CACHE_TTL = 90  # 90 detik — dxy worker refresh 60s

# Komponen tetap DXY (IC futures contract) untuk sintetis dari EURUSD:
# DXY = 50.14348112 x EURUSD^-0.576 x USDJPY^0.136 x GBPUSD^-0.119 x
# USDCAD^0.091 x USDSEK^0.042 x USDCHF^0.036 - hanya EURUSD saja tidak cukup,
# jadi label "synthetic (EURUSD proxy)" jujur.


async def fetch_and_cache_dxy(redis: Any) -> dict[str, Any] | None:
    """Fetch DXY dari Stooq CSV → cache Redis. Return None jika gagal total."""
    import asyncio
    import urllib.request

    def _fetch() -> dict[str, Any] | None:
        # Stooq CSV: DX.F (dollar index futures) — format sd2t2ohlcv
        url = "https://stooq.com/q/l/?s=dx.f&f=sd2t2ohlcv&h&e=csv"
        req = urllib.request.Request(url, headers={"User-Agent": "Lumine/1.0"})  # nosec B310 — URL publik statis
        with urllib.request.urlopen(req, timeout=10) as resp:  # noqa: S310  # nosec B310
            text = resp.read().decode("utf-8", errors="replace")
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        if len(lines) < 2:
            return None
        fields = [f.strip() for f in lines[1].split(",")]
        try:
            close = float(fields[2])
            high = float(fields[3])
            low = float(fields[4])
            return {
                "price": round(close, 3),
                "high": round(high, 3),
                "low": round(low, 3),
                "source": "stooq-dxf",
            }
        except (ValueError, IndexError):
            return None

    try:
        data = await asyncio.to_thread(_fetch)
    except Exception as exc:
        logger.warning("dxy fetch failed: %s", str(exc)[:100])
        data = None

    if data is None:
        # Fallback: cek cache lama masih valid? kalau ya biarkan.
        try:
            cached = await redis.get(CACHE_KEY)
            if cached:
                old = json.loads(cached.decode() if isinstance(cached, bytes) else cached)
                if old.get("price"):
                    return old
        except Exception:  # nosec B110 - Redis down -> cache skip
            pass
        return None

    payload = {**data, "fetched_at": __import__("datetime").datetime.now(__import__("datetime").UTC).isoformat()}
    try:
        await redis.set(CACHE_KEY, json.dumps(payload), ex=CACHE_TTL)
    except Exception:  # nosec B110 - Redis down -> cache skip
        pass
    return payload


async def get_cached_dxy(redis: Any) -> dict[str, Any] | None:
    """Baca DXY dari cache (tanpa fetch). Analyst prompt pakai ini."""
    try:
        cached = await redis.get(CACHE_KEY)
        if cached:
            return json.loads(cached.decode() if isinstance(cached, bytes) else cached)
    except Exception:  # nosec B110 - cache kosong -> None
        pass
    return None
