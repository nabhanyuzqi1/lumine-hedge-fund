"""Economic calendar service (18 Aug 2026).

Fetch jadwal ekonomi (NFP, CPI, FOMC, dll) dari API publik → cache Redis
`lumine:eco_calendar` (TTL 6 jam). Worker `_eco_calendar_worker` refresh
tiap 30 menit. Data dipakai analyst prompt (news_analyst/macro_analyst)
supaya AI tahu event yang akan datang + dampaknya — jawaban user: "news
rss dan dampaknya, economic calendar juga, plan pra news, plan pasca news".
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

logger = logging.getLogger("lumine.trading.eco_calendar")

CACHE_KEY = "lumine:eco_calendar"
CACHE_TTL = 6 * 3600  # 6 jam

# Fallback event statis jika API tidak reachable (jangan kosong total —
# analyst butuh konteks). 2026-08-18 s/d +5 hari.
_FALLBACK_EVENTS: list[dict[str, Any]] = [
    {"date": "2026-08-20", "time": "18:00", "currency": "USD", "event": "FOMC Meeting Minutes", "impact": "high"},
    {"date": "2026-08-21", "time": "14:30", "currency": "USD", "event": "Initial Jobless Claims", "impact": "medium"},
    {"date": "2026-08-25", "time": "18:00", "currency": "USD", "event": "CB Consumer Confidence", "impact": "medium"},
    {"date": "2026-08-28", "time": "14:30", "currency": "USD", "event": "Core PCE Price Index (MoM)", "impact": "high"},
    {"date": "2026-09-01", "time": "14:00", "currency": "USD", "event": "ISM Manufacturing PMI", "impact": "high"},
    {"date": "2026-09-04", "time": "14:30", "currency": "USD", "event": "Nonfarm Payrolls (NFP)", "impact": "high"},
]


def _impact_level(event: dict[str, Any]) -> str:
    """Map impact ke high/medium/low (banyak API pakai 'red'/'orange')."""
    impact = str(event.get("impact", "") or "").lower()
    if impact in ("high", "red", "red2", "red3"):
        return "high"
    if impact in ("medium", "orange", "orange2"):
        return "medium"
    return "low"


def _filter_upcoming(events: list[dict[str, Any]], hours: int = 72) -> list[dict[str, Any]]:
    """Hanya event dalam N jam ke depan (relevan untuk decision cycle)."""
    now = datetime.now(UTC)
    cutoff = now + timedelta(hours=hours)
    out: list[dict[str, Any]] = []
    for e in events:
        try:
            dt = datetime.fromisoformat(str(e.get("date", "")))
        except Exception as _exc:  # event korup → skip
            logger.debug("calendar date parse skipped: %s", _exc)
            continue
        if now <= dt <= cutoff:
            out.append(e)
    return sorted(out, key=lambda x: x.get("date", ""))


async def fetch_economic_calendar(redis: Any) -> list[dict[str, Any]]:
    """Fetch calendar dari API publik (best-effort) → cache Redis.

    Sumber utama: https://nfs.faireconomy.media/ff_calendar_thisweek.json
    (tanpa API key, JSON sederhana). Fallback: event statis + Redis cache.
    """
    import asyncio
    import urllib.request

    events: list[dict[str, Any]] = []

    def _fetch() -> list[dict[str, Any]]:  # sync — dipanggil via asyncio.to_thread
        url = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
        req = urllib.request.Request(url, headers={"User-Agent": "LumineEA/4.12"})  # nosec B310 — URL publik tetap
        with urllib.request.urlopen(req, timeout=12) as resp:  # noqa: S310  # nosec B310
            raw = json.loads(resp.read())
        parsed: list[dict[str, Any]] = []
        for item in raw if isinstance(raw, list) else []:
            try:
                # API pakai field `date` (ISO string dgn offset), bukan
                # `timestamp` — ts=0 → semua jadi 1970 → filter 72h kosong.
                raw_date = str(item.get("date", "") or "").strip()
                if raw_date:
                    dt = datetime.fromisoformat(raw_date.replace("Z", "+00:00"))
                else:
                    ts = float(item.get("timestamp", 0))
                    dt = datetime.fromtimestamp(ts, tz=UTC)
                parsed.append(
                    {
                        "date": dt.astimezone(UTC).isoformat(),
                        "currency": str(item.get("country", "") or "USD").upper(),
                        "event": str(item.get("title", "") or "Economic Event"),
                        "impact": _impact_level(item),
                        "previous": item.get("previous"),
                        "forecast": item.get("forecast"),
                    }
                )
            except Exception as _exc:  # item korup → skip
                logger.debug("calendar item skipped: %s", _exc)
                continue
        return parsed

    try:
        events = await asyncio.to_thread(_fetch)
    except Exception as exc:
        logger.warning("eco calendar fetch failed (fallback): %s", str(exc)[:100])
        events = []

    if not events:
        # Fallback: cache lama masih valid? atau statis.
        try:
            cached = await redis.get(CACHE_KEY)
            if cached:
                old = json.loads(cached.decode() if isinstance(cached, bytes) else cached)
                if old:
                    return old
        except Exception:  # nosec B110 — cache korup → fallback statis
            pass
        events = _FALLBACK_EVENTS

    upcoming = _filter_upcoming(events, hours=72)
    payload = {"fetched_at": datetime.now(UTC).isoformat(), "events": upcoming}
    try:
        await redis.set(CACHE_KEY, json.dumps(payload), ex=CACHE_TTL)
    except Exception:  # nosec B110 — Redis down → cache skip
        pass
    return upcoming


async def get_cached_calendar(redis: Any) -> list[dict[str, Any]]:
    """Baca calendar dari cache (tanpa fetch). Analyst prompt pakai ini."""
    try:
        cached = await redis.get(CACHE_KEY)
        if cached:
            data = json.loads(cached.decode() if isinstance(cached, bytes) else cached)
            return data.get("events", []) if isinstance(data, dict) else []
    except Exception:  # nosec B110 — cache kosong → []
        pass
    return []
