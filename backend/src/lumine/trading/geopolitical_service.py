"""Geopolitical feeds — 19 Aug 2026 A6.

Berita perang/konflik mempengaruhi safe-haven (emas naik) & minyak.
Feeds tambahan:
- BBC world (peristiwa global, termasuk geopolitik)
- Al Jazeera (levant coverage)
- Markets (konsolidasi — bukan placeholder)

Terpisah oleh KATEGORI: gold/dollar/macro/geopolitical.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request

import defusedxml.ElementTree as defused_et  # noqa: N813 — alias snake_case untuk clear lint

CACHE_KEY = "lumine:news:headlines:geopolitical"
CACHE_TTL = 1800  # 30 menit

GEO_FEEDS: list[str] = [
    "https://feeds.bbci.co.uk/news/world/rss.xml",  # BBC world (geopolitik)
    "https://www.aljazeera.com/xml/rss/all.xml",  # Al Jazeera (middle-east focus)
    "https://feeds.bbci.co.uk/news/uk/rss.xml",  # BBC UK tambahan
]

GEO_KW: list[str] = [
    "war", "conflict", "military", "missile", "attack", "invasion",
    "sanction", "strike", "border", "troops", "ceasefire", "tension",
    "crisis", "oil supply", "supply disruption", "geopolitical risk",
]


def _fetch_rss(url: str) -> list[dict[str, str]]:
    """Fetch + parse satu RSS feed (best-effort)."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Lumine/1.0"})  # noqa: S310  # nosec B310
        with urllib.request.urlopen(req, timeout=8) as resp:  # noqa: S310  # nosec B310
            raw = resp.read()
        # 19 Aug 2026: defusedxml.ElementTree protects against XXE/entity
        # blowup (stdlib ET vulnerable).
        root = defused_et.fromstring(raw)  # nosec B314 — defusedxml, aman dari XXE
        items: list[dict[str, str]] = []
        for it in root.iter("item"):
            title = (it.findtext("title") or "").strip()
            link = (it.findtext("link") or "").strip()
            desc = (it.findtext("description") or "").strip()
            if title:
                items.append({"title": title, "url": link, "description": desc})
        return items
    except (urllib.error.URLError, OSError, defused_et.ParseError, ValueError):
        return []


async def get_geopolitical_headlines(get_redis) -> list[dict[str, str]]:
    """Headline geopolitik (perang/konflik) — cache 30 menit, kategori geopolitik."""
    try:
        r = await get_redis()
        cached = await r.get(CACHE_KEY)
        if cached:
            return json.loads(cached)
    except Exception:  # nosec B110
        pass

    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for url in GEO_FEEDS:
        for it in _fetch_rss(url):
            text = (it["title"] + " " + it["description"]).lower()
            if any(kw in text for kw in GEO_KW):
                key = it["title"][:80]
                if key in seen:
                    continue
                seen.add(key)
                out.append(
                    {
                        "title": it["title"],
                        "url": it["url"],
                        "tag": "geopolitical",
                    }
                )
        if len(out) >= 6:
            break

    try:
        r = await get_redis()
        await r.set(CACHE_KEY, json.dumps(out, ensure_ascii=False), ex=CACHE_TTL)
    except Exception:  # nosec B110
        pass
    return out


def classify_geopolitical(title: str, description: str = "") -> bool:
    """Klasifikasi headline → kategori geopolitik (untuk tag di UI)."""
    text = (title + " " + description).lower()
    return any(kw in text for kw in GEO_KW)
