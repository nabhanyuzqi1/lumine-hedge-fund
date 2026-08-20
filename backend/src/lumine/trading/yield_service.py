"""Treasury yield service (19 Aug 2026 — A1: data tidak boleh placeholder).

FRED public CSV (tanpa API key): DGS10 (10Y) + DGS2 (2Y). Cache Redis
`lumine:yields` tiap 6 jam (yield bergerak harian, bukan per-menit).

Sebelumnya analyst macro menerima `us_10y/us_2y = "unavailable (external
feed not wired)"` — placeholder string. Kini yield REAL di-inject.
"""

from __future__ import annotations

import csv
import io
import json

import httpx

from lumine.shared.config import Settings

_FRED_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={series}&cosd={start}"
_CACHE_KEY = "lumine:yields"
_CACHE_TTL = 6 * 3600  # 6 jam — yield harian

_SERIES = {"us_10y": "DGS10", "us_2y": "DGS2"}


async def _fetch_series(client: httpx.AsyncClient, series: str) -> float | None:
    """Ambil nilai yield terbaru (baris terakhir, kolom kedua)."""
    url = _FRED_URL.format(series=series, start="2026-06-01")
    try:
        resp = await client.get(url, timeout=20, follow_redirects=True)
        resp.raise_for_status()
        reader = csv.reader(io.StringIO(resp.text))
        rows = list(reader)
        if len(rows) < 2:
            return None
        # Cari baris terakhir dengan nilai bukan "." (missing)
        for row in reversed(rows[1:]):
            if len(row) >= 2 and row[1].strip() not in ("", "."):
                try:
                    return float(row[1])
                except ValueError:
                    continue
    except (httpx.HTTPError, ValueError, csv.Error):
        return None
    return None


async def get_yields(get_redis, settings: Settings) -> dict[str, float]:
    """Yield 10Y/2Y real (cache). Fallback: None → caller jujur-kan."""
    try:
        r = await get_redis()
        cached = await r.get(_CACHE_KEY)
        if cached:
            data = json.loads(cached)
            if data.get("us_10y") and data.get("us_2y"):
                return data
    except Exception:  # nosec B110 — cache optional
        pass

    result: dict[str, float] = {}
    async with httpx.AsyncClient() as client:
        for key, series in _SERIES.items():
            value = await _fetch_series(client, series)
            if value is not None:
                result[key] = value

    if result.get("us_10y") and result.get("us_2y"):
        try:
            await r.set(_CACHE_KEY, json.dumps(result), ex=_CACHE_TTL)
        except Exception:  # nosec B110
            pass
    return result


def fed_stance_from(us_10y: float | None, us_2y: float | None, dxy_trend: str | None) -> str:
    """Infer stance FED dari kurva yield + DXY (proxy jujur, bukan placeholder).

    - spread 10y-2y negatif & dalam → inverted → hawkish/restriktif (fed
      dalam mode menahan / potensi cut).
    - spread positif lebar → steepening → dovish easing cycle.
    - DXY naik + yield naik → hawkish.
    Default: neutral (data tidak cukup).
    """
    if us_10y is None or us_2y is None:
        return "neutral (yield feed unavailable)"
    spread = us_10y - us_2y
    if dxy_trend == "up" and spread > -0.2 and us_10y > 4.5:
        return "hawkish (yields high + DXY firm)"
    if spread < -0.3:
        return "restrictive (inverted curve)"
    if spread > 0.2:
        return "accommodative (steepening curve)"
    return "neutral (curve flat)"
