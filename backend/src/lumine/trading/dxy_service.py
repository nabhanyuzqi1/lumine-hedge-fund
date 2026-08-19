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
        # DXY dihitung dari komponen tetap IC futures contract menggunakan
        # FX rates (exchangerate-api, tanpa key, diuji dari VPS 19 Aug 2026):
        #   DXY = 50.14348112 x EURUSD^-0.576 x USDJPY^0.136 x GBPUSD^-0.119
                #         x USDCAD^0.091 x USDSEK^0.042 x USDCHF^0.036
        # exchangerate-api memberi 1 USD = X (EUR, JPY, GBP, CAD, SEK, CHF).
        url = "https://open.er-api.com/v6/latest/USD"
        req = urllib.request.Request(url, headers={"User-Agent": "Lumine/1.0"})  # nosec B310 — URL publik statis
        with urllib.request.urlopen(req, timeout=10) as resp:  # noqa: S310  # nosec B310
            raw = json.loads(resp.read().decode("utf-8", errors="replace"))
        rates = raw.get("rates") or {}
        eur = float(rates.get("EUR") or 0)
        jpy = float(rates.get("JPY") or 0)
        gbp = float(rates.get("GBP") or 0)
        cad = float(rates.get("CAD") or 0)
        sek = float(rates.get("SEK") or 0)
        chf = float(rates.get("CHF") or 0)
        if not (eur and jpy and gbp and cad and sek and chf):
            return None
        # USDJPY = 1/JPY (rate = 1 USD = X JPY → pasangan USDJPY = X)
        # EURUSD = 1/EUR; GBPUSD = 1/GBP; USDCAD = CAD; USDSEK = SEK; USDCHF = CHF
        eurusd = 1.0 / eur
        gbpusd = 1.0 / gbp
        dxy = (
            50.14348112
            * (eurusd**-0.576)
            * (jpy**0.136)
            * (gbpusd**-0.119)
            * (cad**0.091)
            * (sek**0.042)
            * (chf**0.036)
        )
        return {
            "price": round(dxy, 3),
            "high": round(dxy, 3),
            "low": round(dxy, 3),
            "source": "computed-ic-basket",
        }

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
