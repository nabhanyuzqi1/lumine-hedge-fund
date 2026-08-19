# Copyright (c) 2026 Lumine. All rights reserved.
"""News feed service (18 Aug 2026) — berita XAUUSD/emas dari RSS publik.

Kenapa di backend, bukan di EA: MQL5 TIDAK punya API untuk membaca news
terminal. Backend fetch RSS publik (Kitco/Reuters gold) → seed awal →
poll berkala (5 menit) → publish ke SSE `news-headlines` → News Analyst
menerima `headlines` real (bukan placeholder "[]").

Desain:
- `fetch_headlines()`: GET RSS → parse <item> → [{title, source, ts, url}]
- Cache Redis `lumine:news:headlines` (30 item, TTL 6 jam) — seed awal
- Poll worker: tiap 300s fetch ulang; headline BARU (URL belum ada di
  cache) → publish SSE `news_update` + prepend cache
- News Analyst (worker decision cycle) baca dari Redis, bukan fetch
  langsung (analyst tetap ringan & offline-safe)
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from typing import Any
from xml.etree import ElementTree as ET  # nosec B405 — fallback offline-only; prod pakai defusedxml

logger = logging.getLogger("lumine.news")

_NEWS_KEY = "lumine:news:headlines"
_NEWS_SEEN_KEY = "lumine:news:seen"  # hash url → ts (dedup)
_MAX_HEADLINES = 30
_POLL_SECONDS = 300

# RSS feeds publik — emas/XAUUSD + ekonomi. Diuji 18 Aug 2026 dari VPS:
# - BBC business (RSS XML asli, andal)
# - OilPrice main (energi + komoditas — konteks inflasi/emas)
# - MarketWatch topstories (ekonomi/market)
# - FXStreet: HANYA /rss/news yang valid (19 Aug 2026 — markets-news/
#   currencies/commodities 404 dari VPS)
# - Kitco TIDAK dipakai: feed lama sudah jadi HTML (bukan RSS) — parse gagal.
# - Reuters feeds mati (DNS tidak resolve dari VPS).
_RSS_FEEDS: list[str] = [
    "https://feeds.bbci.co.uk/news/business/rss.xml",
    "https://oilprice.com/rss/main",
    "https://www.marketwatch.com/rss/topstories",
    # 18 Aug 2026: forex/emas — USD, DXY, pairs kuat (EURUSD dll) yang
    # mempengaruhi XAUUSD.
    "https://www.fxstreet.com/rss/news",
    "https://feeds.finance.yahoo.com/rss/2.0/headline?s=XAUUSD%2CXAGUSD&region=US&lang=en-US",
    "https://www.investing.com/rss/news_25.rss",
]

# Fallback: kalau semua RSS gagal, pakai snapshot ini (biar analyst tidak
# pernah melihat "[]" kosong — data tetap ada, source jelas "fallback").
_FALLBACK_HEADLINES: list[dict[str, Any]] = [
    {
        "title": "Gold steady as dollar firms; traders eye Fed path",
        "source": "lumine-fallback",
        "ts": time.time(),
        "url": "https://lumine.biz.id/news/fallback-1",
        "summary": "Gold trades in a narrow range as the dollar firms ahead of the next Fed decision.",
    },
    {
        "title": "Precious metals: XAUUSD intraday volatility expands",
        "source": "lumine-fallback",
        "ts": time.time(),
        "url": "https://lumine.biz.id/news/fallback-2",
        "summary": "Gold volatility expands on macro headlines; watch 4400 support.",
    },
]


def _parse_rss(xml_text: str, source: str, limit: int = 15) -> list[dict[str, Any]]:  # noqa: C901 — parse RSS bercabang
    """Parse RSS XML → headline dicts (title/url/ts).

    XXE-safe: pakai defusedxml kalau tersedia (lib selalu ada di prod
    image via requirements); fallback stdlib ET hanya untuk offline dev.
    """
    items: list[dict[str, Any]] = []
    try:
        try:
            from defusedxml import ElementTree as SafeET  # type: ignore[import-not-found]

            root = SafeET.fromstring(xml_text)
        except ImportError:
            root = ET.fromstring(xml_text)  # noqa: S314  # nosec B314, B405 — fallback offline-only; prod pakai defusedxml
    except ET.ParseError:
        return items
    for item in root.iter("item"):
        title = ""
        link = ""
        pub_date = ""
        for child in item:
            tag = child.tag.rsplit("}", 1)[-1]
            if tag == "title":
                title = (child.text or "").strip()
            elif tag == "link":
                link = (child.text or "").strip()
            elif tag == "pubDate":
                pub_date = (child.text or "").strip()
        if not title or not link:
            continue
        # Hanya berita yang relevan emas/dollar/ekonomi.
        low = title.lower()
        if not any(
            k in low
            for k in (
                "gold",
                "xau",
                "metal",
                "dollar",
                "fed",
                "treasury",
                "inflation",
                "rate",
                "cpi",
                "oil",
                "energy",
                "commodit",
                "economic",
                "recession",
                "yield",
            )
        ):
            continue
        ts = _parse_rss_date(pub_date)
        items.append(
            {
                "title": title[:220],
                "source": source,
                "ts": ts,
                "url": link[:300],
            }
        )
        if len(items) >= limit:
            break
    return items


def _parse_rss_date(pub: str) -> float:
    """RSS pubDate (RFC822) → epoch; gagal → now."""
    if not pub:
        return time.time()
    try:
        from email.utils import parsedate_to_datetime

        return parsedate_to_datetime(pub).timestamp()
    except Exception:
        return time.time()


async def fetch_headlines(redis: Any) -> list[dict[str, Any]]:
    """Fetch RSS feeds; return dedup + relevance-filtered headlines.

    Semua fetch dibungkus to_thread (blocking I/O). Gagal total → fallback.
    """
    loop = asyncio.get_event_loop()
    found: list[dict[str, Any]] = []

    async def _fetch_one(url: str, source: str) -> None:
        try:
            import urllib.request

            def _get() -> bytes:
                req = urllib.request.Request(url, headers={"User-Agent": "Lumine/1.0"})  # noqa: S310  # nosec B310 — RSS feed statis (whitelist _RSS_FEEDS)
                with urllib.request.urlopen(req, timeout=8) as resp:  # noqa: S310  # nosec B310 — RSS feed statis (whitelist _RSS_FEEDS)
                    return resp.read()

            raw = await loop.run_in_executor(None, _get)
            text = raw.decode("utf-8", errors="replace")
            parsed = _parse_rss(text, source)
            found.extend(parsed)
            logger.info("news: fetched %d from %s", len(parsed), source)
        except Exception as exc:
            logger.warning("news: %s failed: %s", url, str(exc)[:120])

    for url in _RSS_FEEDS:
        await _fetch_one(url, url.split("/")[2])

    # Dedup by url + filter kosong.
    seen: set[str] = set()
    headlines: list[dict[str, Any]] = []
    for h in found:
        key = hashlib.sha256(h["url"].encode()).hexdigest()
        if key in seen:
            continue
        seen.add(key)
        headlines.append(h)

    if not headlines:
        headlines = list(_FALLBACK_HEADLINES)
    # Sort newest-first.
    headlines.sort(key=lambda h: h.get("ts", 0), reverse=True)
    return headlines[:_MAX_HEADLINES]


async def refresh_news_cache(redis: Any, publisher: Any | None = None) -> list[dict[str, Any]]:
    """Fetch + update Redis cache + publish headline BARU ke SSE.

    Dipanggil worker `_news_worker` tiap 300s dan sekali saat startup
    (seed awal). Publikasi hanya untuk headline yang URL-nya belum pernah
    dilihat (`lumine:news:seen` hash) — "hanya news baru dikirim".
    """
    headlines = await fetch_headlines(redis)
    if not headlines:
        return []

    # Simpan cache (analyst baca dari sini).
    import json as _json

    await redis.set(_NEWS_KEY, _json.dumps(headlines), ex=21_600)  # 6h

    # Dedup publikasi: URL baru → publish + tandai seen.
    new_items: list[dict[str, Any]] = []
    for h in headlines:
        key = hashlib.sha256(h["url"].encode()).hexdigest()
        existed = await redis.hget(_NEWS_SEEN_KEY, key)
        if existed is None:
            new_items.append(h)
            await redis.hset(_NEWS_SEEN_KEY, key, str(int(time.time())))

    if new_items and publisher is not None:
        from lumine.api.sse.publisher import SSEEvent

        await publisher.publish(
            SSEEvent(
                event_type="news_update",
                channel="news-headlines",
                data={
                    "items": new_items[:5],
                    "total": len(headlines),
                    "timestamp": time.time(),
                },
            )
        )
        logger.info("news: published %d new headline(s)", len(new_items))
    return headlines


async def get_cached_headlines(redis: Any, limit: int = 10) -> list[dict[str, Any]]:
    try:
        import json as _json

        raw = await redis.get(_NEWS_KEY)
        if raw:
            items = _json.loads(raw.decode() if isinstance(raw, bytes) else raw)
            return items[:limit]
    except Exception:  # nosec B110 — cache rusak → fallback refresh
        pass
    # Cache miss → seed sekali (caller aman; worker juga akan refresh).
    try:
        return await refresh_news_cache(redis)
    except Exception:
        return list(_FALLBACK_HEADLINES)
