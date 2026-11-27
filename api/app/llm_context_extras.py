"""[FUND2-LLM-1 t_906c7755] Provider data makro untuk konteks LLM agent.

Tiga blok data eksternal untuk memperkaya prompt LLM agent (XAUUSD/BTCUSD):
- ``sentiment``   : Fear & Greed Index (alternative.me) sebagai proxy risk
                    sentiment (dipakai untuk BTCUSD primer; XAUUSD memakai
                    nilai yang sama dengan label ``basis: risk_sentiment_proxy``).
- ``fundamental`` : DXY + US10Y dari Yahoo chart; jika Yahoo gagal, US10Y
                    fallback ke yield harian resmi Treasury.gov (kolom "10 Yr").
- ``calendar``    : event ekonomi berdampak tinggi USD (ForexFactory this-week
                    JSON) dalam window now-2h .. now+72h.

Kontrak desain (keputusan CEO, kartu t_906c7755 - final):
- Modul BARU, read-only: tidak ada tabel baru, migrasi, atau write DB.
- API publik: :func:`collect_extras` -> ``{"sentiment": ..., "fundamental": ...,
  "calendar": ...}``; tiap blok punya ``status`` ("ok"|"stale"|"unavailable"),
  ``fetched_at``, ``source``, ``as_of``. Fetch gagal TIDAK pernah melempar
  exception ke caller.
- Cache in-process per blok (TTL: sentiment 3600s, fundamental 600s,
  calendar 3600s; bisa di-override via env). Stale-while-error: fetch gagal
  -> sajikan cache terakhir dengan status "stale" (maks umur 24 jam); lewat
  itu "unavailable" + alasan.
- Tiga fetch paralel (asyncio.gather); timeout per fetch total 10s / connect 5s.
  Blok fundamental boleh menjalankan fallback Treasury (+5s) sehingga
  worst-case ~15s jika kedua sumber menggantung; kegagalan umum (429/timeout
  cepat) jauh di bawah itu dan siklus 300s tetap sehat.
- Env (semua opsional, pola config.get; modul ini TIDAK mengedit config.py):
  FNG_URL, YAHOO_CHART_URL (template wajib mengandung "{symbol}"),
  CALENDAR_URL, EXTRAS_TIMEOUT_S, EXTRAS_TTL_SENTIMENT_S,
  EXTRAS_TTL_FUNDAMENTAL_S, EXTRAS_TTL_CALENDAR_S.

Anti-injection: semua string eksternal (judul event, klasifikasi, forecast)
disanitasi lewat :func:`_sanitize_text` (control/format/surrogate chars
dibuang, dipangkas sesuai batas). Data hanya boleh masuk prompt lewat
``<market_data>`` tags (lihat ``llm_agent_loop._build_user_prompt``); JANGAN
pernah menginterpolasi string eksternal ke SYSTEM_PROMPT.

Sumber data (diuji live dari host ini 24 Nov 2026; jangan diganti tanpa
konsultasi CEO):
- https://api.alternative.me/fng/?limit=1
- https://query2.finance.yahoo.com/v8/finance/chart/DX-Y.NYB?range=1d&interval=1d
- https://query2.finance.yahoo.com/v8/finance/chart/%5ETNX?range=1d&interval=1d
  (WAJIB header User-Agent browser; tanpa UA -> 429. Catatan: Yahoo juga
  memblok klien non-browser dari sebagian IP; kegagalan Yahoo ditangani
  stale/unavailable untuk DXY dan fallback Treasury untuk US10Y.)
- https://nfs.faireconomy.media/ff_calendar_thisweek.json
- Fallback US10Y: https://home.treasury.gov/resource-center/data-chart-center/
  interest-rates/daily-treasury-rates.csv/<tahun>/all?type=daily_treasury_yield
  _curve&field_tdr_date_value=<tahun>&page&_format=csv
"""
from __future__ import annotations

import asyncio
import copy
import csv
import io
import json
import math
import os
import time
import unicodedata
from datetime import datetime, timedelta, timezone

import httpx

from . import config

# ── Sumber data (default; bisa di-override via env) ─────────────────────────
FNG_URL = "https://api.alternative.me/fng/?limit=1"
YAHOO_CHART_URL = (
    "https://query2.finance.yahoo.com/v8/finance/chart/{symbol}?range=1d&interval=1d"
)
# Host alternatif: Yahoo memblokir per-host (query2 sempat 429 sementara
# query1 tetap 200 dari IP yang sama, diuji 27 Nov 2026). Urutan dicoba
# sampai satu menjawab; env YAHOO_CHART_URL tetap menang bila diisi.
YAHOO_CHART_URL_FALLBACKS = (
    "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range=1d&interval=1d",
    "https://query2.finance.yahoo.com/v8/finance/chart/{symbol}?range=5d&interval=1d",
)
CALENDAR_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
# Fallback: path XML sumber sama (JSON sering kena 429 saat XML tetap 200).
CALENDAR_XML_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.xml"
TREASURY_CSV_URL = (
    "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/"
    "daily-treasury-rates.csv/{year}/all?type=daily_treasury_yield_curve"
    "&field_tdr_date_value={year}&page&_format=csv"
)
# Dollar index cadangan saat Yahoo memblokir SEMUA host: FRED broad trade-weighted
# dollar (DTWEXBGS), harian, tanpa API key. Bukan DXY (keranjang lebih luas),
# jadi selalu diberi label proxy di payload supaya tidak salah skala.
FRED_DOLLAR_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DTWEXBGS"
YAHOO_COOLDOWN_S = 900.0

BROWSER_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

_CLIENT_HEADERS = {
    "User-Agent": BROWSER_UA,
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
}

# ── Batas operasional (keputusan CEO) ───────────────────────────────────────
DEFAULT_TIMEOUT_S = 10.0     # total per fetch
CONNECT_TIMEOUT_S = 5.0
FALLBACK_TIMEOUT_S = 5.0     # request fallback Treasury
STALE_MAX_AGE_S = 24 * 3600  # cache lebih tua dari ini -> unavailable
TTL_SENTIMENT_S = 3600
TTL_FUNDAMENTAL_S = 600
TTL_CALENDAR_S = 3600

# ── Kalender ────────────────────────────────────────────────────────────────
CALENDAR_LOOKBACK_H = 2      # window now-2h (event baru rilis tetap tampil)
CALENDAR_LOOKAHEAD_H = 72    # .. now+72h
CALENDAR_MAX_EVENTS = 12
EVENT_TITLE_MAX = 120        # batas judul event (anti-injection)
EVENT_FIELD_MAX = 40         # batas forecast/previous/impact

_SOURCE_NAMES = {
    "sentiment": "alternative.me",
    "fundamental": "yahoo_chart",
    "calendar": "faireconomy.media",
}

# Cache in-process: name -> {"block": envelope ok, "mono": monotonic, "wall": epoch}
_CACHE: dict[str, dict] = {}
_LOCKS: dict[str, asyncio.Lock] = {}


def _env(name: str, default: str = "") -> str:
    return config.get(name, default)


def _env_float(name: str, default: float) -> float:
    try:
        return float(_env(name, str(default)))
    except (TypeError, ValueError):
        return default


def _ttl(name: str, default: float) -> float:
    return _env_float(f"EXTRAS_TTL_{name}_S", default)


def _iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def _reset_cache() -> None:
    """Reset cache & lock (untuk test; dipanggil antar test agar bebas lintas-loop).

    Cooldown rate-limit dan cache disk juga direset/isolasi: tanpa itu test
    bisa membaca cache produksi di `.cache/extras` dan hasilnya bergantung
    pada state mesin.
    """
    _CACHE.clear()
    _LOCKS.clear()
    _COOLDOWN.clear()
    _YAHOO_COOLDOWN.clear()
    global _CACHE_DIR
    _CACHE_DIR = os.path.join(
        os.environ.get("PYTEST_TMPDIR") or os.environ.get("TMPDIR") or "/tmp",
        "extras-cache-test",
    )
    try:  # bersihkan cache disk isolasi supaya test tidak saling mewarisi state
        for fn in os.listdir(_CACHE_DIR):
            if fn.endswith(".json") or fn.endswith(".tmp"):
                os.unlink(os.path.join(_CACHE_DIR, fn))
    except OSError:
        pass


def _lock(name: str) -> asyncio.Lock:
    if name not in _LOCKS:
        _LOCKS[name] = asyncio.Lock()
    return _LOCKS[name]


def _new_client() -> httpx.AsyncClient:
    total = _env_float("EXTRAS_TIMEOUT_S", DEFAULT_TIMEOUT_S)
    return httpx.AsyncClient(
        timeout=httpx.Timeout(total, connect=min(CONNECT_TIMEOUT_S, total)),
        headers=_CLIENT_HEADERS,
        follow_redirects=True,
    )


# ── Sanitasi string eksternal (anti-injection) ──────────────────────────────
def _sanitize_text(value, max_len: int) -> str | None:
    """Buang control/format/surrogate chars lalu pangkas ke max_len.

    Semua string dari sumber eksternal WAJIB lewat sini sebelum masuk payload
    yang kelak disisipkan ke prompt LLM (via <market_data> tags).
    """
    if value is None:
        return None
    s = unicodedata.normalize("NFKC", str(value))
    s = "".join(
        ch for ch in s if unicodedata.category(ch) not in ("Cc", "Cf", "Cs")
    )
    s = s.strip()
    if len(s) > max_len:
        s = s[:max_len].rstrip()
    return s


def _parse_iso(value) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


# ── HTTP helpers ────────────────────────────────────────────────────────────
# TradingView economic-calendar butuh Origin/Referer seperti browser.
_TV_HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/126.0 Safari/537.36",
    "Origin": "https://www.tradingview.com",
    "Referer": "https://www.tradingview.com/",
    "Accept": "application/json",
}


async def _get_json(http: httpx.AsyncClient, url: str, timeout=None,
                    headers: dict | None = None):
    resp = await http.get(url, timeout=timeout, headers=headers)
    resp.raise_for_status()
    return resp.json()


async def _get_text(http: httpx.AsyncClient, url: str, timeout=None,
                    headers: dict | None = None) -> str:
    resp = await http.get(url, timeout=timeout, headers=headers)
    resp.raise_for_status()
    return resp.text


# ── Parser: sentiment (Fear & Greed Index) ──────────────────────────────────
def _parse_fng(data, now_utc: datetime) -> dict:
    rows = (data or {}).get("data") or []
    if not rows:
        raise ValueError("FNG: array data kosong")
    row = rows[0]
    try:
        value = int(str(row.get("value", "")).strip())
    except ValueError:
        raise ValueError(f"FNG: value bukan integer: {row.get('value')!r}") from None
    if not 0 <= value <= 100:
        raise ValueError(f"FNG: value di luar 0-100: {value}")
    ts_raw = str(row.get("timestamp", "")).strip()
    if not ts_raw.isdigit():
        raise ValueError(f"FNG: timestamp tidak valid: {row.get('timestamp')!r}")
    as_of = datetime.fromtimestamp(int(ts_raw), tz=timezone.utc).isoformat()
    classification = _sanitize_text(row.get("value_classification"), 60) or ""
    return {
        "source": "alternative.me",
        "as_of": as_of,
        "fng": {
            "value": value,
            "classification": classification,
            "as_of": as_of,
            "source": "alternative.me",
            "basis": "risk_sentiment_proxy",
        },
        "symbol_note": "BTCUSD primer; XAUUSD proxy risk-sentiment",
    }


async def _fetch_sentiment(now_utc: datetime, http: httpx.AsyncClient) -> dict:
    data = await _get_json(http, _env("FNG_URL", FNG_URL))
    return _parse_fng(data, now_utc)


# ── Parser: fundamental (DXY + US10Y) ───────────────────────────────────────
def _parse_yahoo_chart(data) -> tuple[float, str | None]:
    """Return (price, as_of_iso) dari response Yahoo chart v8."""
    chart = (data or {}).get("chart") or {}
    if chart.get("error"):
        raise ValueError(f"Yahoo chart error: {str(chart['error'])[:120]}")
    results = chart.get("result") or []
    if not results:
        raise ValueError("Yahoo chart: result kosong")
    res = results[0]
    meta = res.get("meta") or {}
    price = meta.get("regularMarketPrice")
    if price is None:
        quote = (res.get("indicators") or {}).get("quote") or [{}]
        closes = [c for c in (quote[0].get("close") or []) if c is not None]
        price = closes[-1] if closes else None
    if price is None:
        raise ValueError("Yahoo chart: harga tidak tersedia")
    price = float(price)
    if not math.isfinite(price):
        raise ValueError("Yahoo chart: harga non-finite")
    ts = meta.get("regularMarketTime")
    as_of = None
    if ts:
        try:
            as_of = datetime.fromtimestamp(int(ts), tz=timezone.utc).isoformat()
        except (OverflowError, OSError, ValueError):
            as_of = None
    return round(price, 4), as_of


_YAHOO_COOLDOWN: dict[str, float] = {}


def _host_of(template: str) -> str:
    return template.split("/")[2] if "//" in template else template


def _yahoo_in_cooldown(template: str) -> bool:
    import time as _time
    until = _YAHOO_COOLDOWN.get(_host_of(template))
    return bool(until and until > _time.monotonic())


def _yahoo_mark_cooldown(template: str) -> None:
    import time as _time
    _YAHOO_COOLDOWN[_host_of(template)] = _time.monotonic() + YAHOO_COOLDOWN_S


async def _yahoo_price(http: httpx.AsyncClient, symbol: str) -> tuple[float, str | None]:
    """Harga Yahoo dengan fallback host + cooldown per host.

    query2 bisa 429 per-host sementara query1 tetap menjawab (dan sebaliknya).
    Host yang membalas 429 dilewati selama YAHOO_COOLDOWN_S supaya tidak
    menembak server yang sama berulang kali setiap proses baru; semua
    kegagalan digabung agar pesan error menyebut setiap host yang dicoba.
    """
    template = _env("YAHOO_CHART_URL", YAHOO_CHART_URL)
    if "{symbol}" not in template:
        raise ValueError("YAHOO_CHART_URL harus mengandung placeholder {symbol}")
    candidates = [template, *YAHOO_CHART_URL_FALLBACKS]
    errors: list[str] = []
    for tpl in dict.fromkeys(candidates):
        if _yahoo_in_cooldown(tpl):
            errors.append(f"{_host_of(tpl)}: dilewati (429 cooldown)")
            continue
        try:
            data = await _get_json(http, tpl.format(symbol=symbol))
            return _parse_yahoo_chart(data)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 429:
                _yahoo_mark_cooldown(tpl)
            errors.append(f"{_host_of(tpl)}: {type(exc).__name__}: {exc}"[:90])
        except Exception as exc:  # noqa: BLE001 - coba host berikutnya
            errors.append(f"{_host_of(tpl)}: {type(exc).__name__}: {exc}"[:90])
    raise RuntimeError("; ".join(errors)[:300])


def _parse_fred_csv(text: str, column: str) -> tuple[float, float | None, str]:
    """Return (value, prev_value, as_of_date) dari CSV FRED (tanggal, nilai)."""
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames or column not in reader.fieldnames:
        raise ValueError(f"FRED CSV: kolom '{column}' tidak ada")
    rows = [(r.get("observation_date") or "", r.get(column) or "") for r in reader]
    rows = [(d, v) for d, v in rows if v.strip() not in ("", ".")]
    if not rows:
        raise ValueError("FRED CSV: tidak ada baris berisi nilai")
    rows.sort(key=lambda r: r[0])
    as_of, raw = rows[-1]
    value = float(raw)
    if not math.isfinite(value):
        raise ValueError("FRED CSV: nilai non-finite")
    prev = float(rows[-2][1]) if len(rows) > 1 else None
    return round(value, 4), (round(prev, 4) if prev is not None else None), as_of


async def _fred_dollar(http: httpx.AsyncClient) -> tuple[float, float | None, str]:
    # FRED (CloudFront) menahan permintaan dengan UA browser: curl/8.5.0 lolos,
    # UA Chrome menggantung sampai timeout (diuji 27 Nov 2026). Pakai UA polos.
    text = await _get_text(http, FRED_DOLLAR_URL,
                           timeout=httpx.Timeout(FALLBACK_TIMEOUT_S),
                           headers={"User-Agent": "curl/8.5.0"})
    return _parse_fred_csv(text, "DTWEXBGS")


def _parse_treasury_csv(text: str) -> tuple[float, str]:
    """Return (us10y_pct, as_of_date_iso) dari CSV yield harian Treasury.gov."""
    reader = csv.DictReader(io.StringIO(text))
    if "10 Yr" not in (reader.fieldnames or []):
        raise ValueError("Treasury CSV: kolom '10 Yr' tidak ada")
    rows = [r for r in reader if (r.get("10 Yr") or "").strip()]
    if not rows:
        raise ValueError("Treasury CSV: tidak ada baris berisi '10 Yr'")

    def _date(row):
        return datetime.strptime((row.get("Date") or "").strip(), "%m/%d/%Y")

    latest = max(rows, key=_date)
    value = float(str(latest["10 Yr"]).strip())
    if not math.isfinite(value):
        raise ValueError("Treasury CSV: nilai non-finite")
    return round(value, 4), _date(latest).date().isoformat()


async def _fetch_fundamental(now_utc: datetime, http: httpx.AsyncClient) -> dict:
    """DXY + US10Y paralel dari Yahoo; US10Y fallback ke Treasury.gov."""
    dxy_res, yld_res = await asyncio.gather(
        _yahoo_price(http, "DX-Y.NYB"),
        _yahoo_price(http, "%5ETNX"),
        return_exceptions=True,
    )
    errors: list[str] = []
    dxy = dxy_as_of = None
    if isinstance(dxy_res, BaseException):
        errors.append(f"dxy: {type(dxy_res).__name__}: {dxy_res}"[:160])
    else:
        dxy, dxy_as_of = dxy_res

    us10y = yld_as_of = None
    yields_source = "yahoo_chart"
    if isinstance(yld_res, BaseException):
        errors.append(f"us10y yahoo: {type(yld_res).__name__}: {yld_res}"[:160])
        # Fallback resmi: Treasury daily yield curve (kolom "10 Yr").
        try:
            url = TREASURY_CSV_URL.format(year=now_utc.astimezone(timezone.utc).year)
            text = await _get_text(
                http, url, timeout=httpx.Timeout(FALLBACK_TIMEOUT_S)
            )
            us10y, yld_as_of = _parse_treasury_csv(text)
            yields_source = "treasury.gov"
        except Exception as exc:  # noqa: BLE001 - gagal fetch tidak boleh raise
            errors.append(f"us10y treasury: {type(exc).__name__}: {exc}"[:160])
    else:
        us10y, yld_res_as_of = yld_res
        yld_as_of = yld_res_as_of

    if dxy is None:
        # Yahoo bisa memblokir SEMUA host sekaligus (429 per-IP burst). Dollar
        # tidak boleh hilang hanya karena satu vendor: pakai FRED DTWEXBGS
        # sebagai proxy terlabel, bukan angka DXY palsu.
        try:
            fred_val, fred_prev, fred_as_of = await _fred_dollar(http)
            change = (round((fred_val / fred_prev - 1) * 100, 3)
                      if fred_prev else None)
            dxy = fred_val
            dxy_as_of = fred_as_of
            dxy_meta = {"index": "DTWEXBGS",
                        "proxy": "broad_trade_weighted_dollar",
                        "prev": fred_prev, "change_pct": change,
                        "source": "fred.stlouisfed.org"}
        except Exception as exc:  # noqa: BLE001 - gagal fetch tidak boleh raise
            dxy_meta = {}
            errors.append(f"dxy fred: {type(exc).__name__}: {exc}"[:160])
    else:
        dxy_meta = {"index": "DXY", "proxy": None, "source": "yahoo_chart"}

    if dxy is None and us10y is None:
        raise RuntimeError("; ".join(errors) or "fundamental: semua sumber gagal")

    source = "yahoo_chart" if yields_source == "yahoo_chart" else "yahoo_chart+treasury.gov"
    if dxy_meta.get("source") == "fred.stlouisfed.org":
        source = f"fred+{yields_source}" if yields_source != "yahoo_chart" else "fred+yahoo_chart"
    payload: dict = {
        "source": source,
        "as_of": dxy_as_of or yld_as_of,
        "dxy": ({"value": dxy, "as_of": dxy_as_of, **dxy_meta}
                if dxy is not None else None),
        "yields": (
            {"us10y_pct": us10y, "as_of": yld_as_of, "source": yields_source}
            if us10y is not None
            else None
        ),
    }
    if errors:
        # `errors` = data yang BENAR-BENAR hilang (dipakai gate & prompt sebagai
        # sinyal degradasi). Kegagalan vendor yang berhasil ditambal sumber lain
        # hanya `warnings`, supaya dxy yang sudah pulih tidak lagi dituduh null.
        critical = []
        if dxy is None:
            critical += [e for e in errors if e.startswith("dxy")]
        if us10y is None:
            critical += [e for e in errors if e.startswith("us10y")]
        recoverable = [e for e in errors if e not in critical]
        if critical:
            payload["errors"] = critical
        if recoverable:
            payload["warnings"] = recoverable
    return payload


# ── Parser: calendar (ForexFactory this week) ───────────────────────────────
_ET_ZONE = None


def _et_zone():
    """Zona America/New_York (ET, DST-aware). Cache agar tidak resolve terus."""
    global _ET_ZONE
    if _ET_ZONE is None:
        from zoneinfo import ZoneInfo

        _ET_ZONE = ZoneInfo("America/New_York")
    return _ET_ZONE


def _parse_calendar_xml(raw: str) -> list[dict]:
    """XML ForexFactory -> baris bergaya JSON (dipakai _parse_calendar).

    Format XML: <date>11-22-2026</date> + <time>9:45pm</time> dalam waktu
    lokal ET tanpa offset. Konversi ke UTC WAJIB lewat zoneinfo: menganggap
    UTC akan menggeser blackout window 4-5 jam (pernah bikin gate salah).
    Baris tanpa jam (all-day) atau tanggal/jam rusak di-skip, bukan gagal total.
    """
    import xml.etree.ElementTree as ET

    root = ET.fromstring(raw)
    rows: list[dict] = []
    for ev in root.findall("event"):
        def _txt(tag: str) -> str:
            return (ev.findtext(tag) or "").strip()

        date_s, time_s = _txt("date"), _txt("time")
        if not date_s or not time_s:
            continue
        try:
            naive = datetime.strptime(f"{date_s} {time_s}", "%m-%d-%Y %I:%M%p")
        except ValueError:
            continue
        try:
            local = naive.replace(tzinfo=_et_zone())
        except Exception:  # noqa: BLE001 - tzdata absen: skip, jangan nebak
            continue
        rows.append({
            "country": _txt("country"),
            "impact": _txt("impact"),
            "title": _txt("title"),
            "date": local.astimezone(timezone.utc).isoformat(),
            "forecast": _txt("forecast"),
            "previous": _txt("previous"),
        })
    if not rows:
        raise ValueError("Calendar XML: tidak ada event valid")
    return rows


def _parse_calendar(data, now_utc: datetime) -> dict:
    if not isinstance(data, list):
        raise ValueError("Calendar: JSON bukan array")
    start = now_utc - timedelta(hours=CALENDAR_LOOKBACK_H)
    end = now_utc + timedelta(hours=CALENDAR_LOOKAHEAD_H)
    picked: list[tuple[datetime, dict]] = []
    for row in data:
        try:
            if not isinstance(row, dict):
                continue
            if str(row.get("country", "")).strip().upper() != "USD":
                continue
            if str(row.get("impact", "")).strip().lower() != "high":
                continue
            t = _parse_iso(row.get("date"))
            if t is None or not (start <= t <= end):
                continue
            title = _sanitize_text(row.get("title"), EVENT_TITLE_MAX)
            if not title:
                continue
            event = {
                "title": title,
                "time_utc": t.isoformat(),
                "impact": _sanitize_text(row.get("impact"), 20) or "High",
                "forecast": _sanitize_text(row.get("forecast"), EVENT_FIELD_MAX) or None,
                "previous": _sanitize_text(row.get("previous"), EVENT_FIELD_MAX) or None,
            }
            picked.append((t, event))
        except Exception:  # noqa: BLE001 - baris rusak di-skip, bukan gagal total
            continue
    picked.sort(key=lambda pair: pair[0])
    picked = picked[:CALENDAR_MAX_EVENTS]
    next_pair = next((p for p in picked if p[0] > now_utc), None)
    return {
        "source": "faireconomy.media",
        "as_of": _iso(now_utc),
        "events": [event for _, event in picked],
        "next_high_impact_utc": next_pair[1]["time_utc"] if next_pair else None,
        "minutes_to_next_high_impact": (
            round((next_pair[0] - now_utc).total_seconds() / 60, 1) if next_pair else None
        ),
    }


def _parse_calendar_tv(rows, now_utc: datetime) -> dict:
    """TradingView economic calendar -> envelope blok calendar.

    Sumber kedua (tanpa API key, tidak kena Cloudflare throttle faireconomy).
    `date` sudah ISO UTC ("...Z"). `country` berisi kode negara ("US"),
    `currency` berisi kode mata uang ("USD") — parser blackout memfilter USD,
    jadi country dipetakan ke currency. `importance`: 1 = High.
    """
    if not isinstance(rows, list) or not rows:
        raise ValueError("Calendar TV: result kosong/bukan array")
    mapped: list[dict] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        try:
            imp = int(row.get("importance"))
        except (TypeError, ValueError):
            continue
        if imp != 1:
            continue
        cur = str(row.get("currency") or "").strip().upper()
        if not cur:
            continue
        date_s = str(row.get("date") or "").strip()
        if not date_s:
            continue
        mapped.append({
            "country": cur,
            "impact": "High",
            "title": row.get("title") or row.get("indicator") or "",
            "date": date_s,
            "forecast": row.get("forecast"),
            "previous": row.get("previous"),
        })
    out = _parse_calendar(mapped, now_utc)
    out["source"] = "tradingview.economic-calendar"
    out["no_high_impact"] = not mapped
    return out


async def _fetch_calendar(now_utc: datetime, http: httpx.AsyncClient) -> dict:
    """Kalender ekonomi: TradingView -> ForexFactory JSON -> ForexFactory XML.

    Urutan ini dipilih dari hasil audit 26 Nov 2026: TradingView tanpa API key
    dan tanpa rate-limit agresif; ForexFactory JSON/XML sering 429 Cloudflare.
    Bila semua gagal, error digabung supaya cache bisa menyajikan data stale.
    """
    errors: list[str] = []
    # 1) TradingView (primary).
    try:
        start = (now_utc - timedelta(hours=CALENDAR_LOOKBACK_H + 6)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        end = (now_utc + timedelta(hours=CALENDAR_LOOKAHEAD_H)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        url_tv = (f"https://economic-calendar.tradingview.com/events"
                  f"?from={start}&to={end}&countries=US,EU,GB,JP,CN")
        data = await _get_json(http, url_tv, headers=_TV_HEADERS)
        return _parse_calendar_tv((data or {}).get("result"), now_utc)
    except Exception as exc:  # noqa: BLE001 - lanjut ke sumber berikutnya
        errors.append(f"tradingview: {type(exc).__name__}: {exc}"[:140])
        _note_retry_after("calendar", exc)
    # 2) ForexFactory JSON.
    try:
        data = await _get_json(http, _env("CALENDAR_URL", CALENDAR_URL))
        return _parse_calendar(data, now_utc)
    except Exception as exc:  # noqa: BLE001
        errors.append(f"ff-json: {type(exc).__name__}: {exc}"[:140])
        _note_retry_after("calendar", exc)
    # 3) ForexFactory XML (kuota terpisah dari JSON).
    try:
        raw = await _get_text(http, _env("CALENDAR_XML_URL", CALENDAR_XML_URL))
        rows = _parse_calendar_xml(raw)
    except Exception as exc:  # noqa: BLE001
        errors.append(f"ff-xml: {type(exc).__name__}: {exc}"[:140])
        _note_retry_after("calendar", exc)
        raise RuntimeError("; ".join(errors)[:400]) from exc
    out = _parse_calendar(rows, now_utc)
    out["source"] = "faireconomy.media(xml)"
    out["fallback_errors"] = errors
    return out


# ── Cache + envelope ────────────────────────────────────────────────────────
# Cooldown per blok saat sumber membalas 429 + `retry-after`: berhenti
# menembak sumber (Cloudflare memblokir per-IP) dan sajikan cache disk.
_COOLDOWN: dict[str, float] = {}
_CACHE_DIR = (
    os.environ.get("EXTRAS_CACHE_DIR")
    or os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".cache", "extras")
)


def _note_retry_after(name: str, exc: BaseException) -> None:
    """Set cooldown dari header `retry-after` (default 300s untuk 429/403)."""
    wait = 300.0
    resp = getattr(exc, "response", None)
    if resp is not None:
        raw = (resp.headers or {}).get("retry-after")
        if raw:
            try:
                wait = max(30.0, min(float(str(raw).strip()), 3600.0))
            except ValueError:
                pass
        elif resp.status_code == 403:
            wait = 900.0
        elif resp.status_code != 429:
            return
        else:
            wait = 300.0
    else:
        return
    _COOLDOWN[name] = time.time() + wait


def _cooldown_left(name: str) -> float:
    return max(0.0, _COOLDOWN.get(name, 0.0) - time.time())


def _disk_path(name: str) -> str:
    return os.path.join(_CACHE_DIR, f"{name}.json")


def _disk_write(name: str, block: dict) -> None:
    try:
        os.makedirs(_CACHE_DIR, exist_ok=True)
        tmp = _disk_path(name) + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump({"saved_at": time.time(), "block": block}, fh)
        os.replace(tmp, _disk_path(name))
    except Exception:  # noqa: BLE001 - cache disk tidak boleh menggagalkan fetch
        pass


def _disk_read(name: str, max_age_s: float) -> dict | None:
    try:
        with open(_disk_path(name), "r", encoding="utf-8") as fh:
            raw = json.load(fh)
        if (time.time() - float(raw.get("saved_at") or 0)) > max_age_s:
            return None
        block = raw.get("block")
        # Blok fundamental tidak punya `events`; syarat lama menolak cache
        # disk-nya sehingga proses baru selalu menembak Yahoo (dan kena 429).
        return block if isinstance(block, dict) and block.get("status") else None
    except Exception:  # noqa: BLE001
        return None


async def _get_block(name: str, ttl_s: float, fetch, now_utc: datetime) -> dict:
    """Ambil blok dengan cache memori+disk (stale-while-error); TIDAK pernah raise."""
    async with _lock(name):
        entry = _CACHE.get(name)
        mono_now = time.monotonic()
        if entry is not None and (mono_now - entry["mono"]) < ttl_s:
            return copy.deepcopy(entry["block"])
        if _cooldown_left(name) > 0:
            # Sumber sedang membatasi: jangan tembak lagi, pakai cache.
            if entry is not None:
                block = copy.deepcopy(entry["block"])
                block["status"] = "stale"
                block["stale_reason"] = (
                    f"rate_limited (cooldown {int(_cooldown_left(name))}s, cache memory)")
                return block
            disk_hit = _disk_read(name, STALE_MAX_AGE_S)
            if disk_hit:
                disk_hit["status"] = "stale"
                disk_hit["stale_reason"] = (
                    f"rate_limited (cooldown {int(_cooldown_left(name))}s, cache disk)")
                return disk_hit
            return {
                "status": "unavailable",
                "fetched_at": _iso(now_utc),
                "as_of": None,
                "source": _SOURCE_NAMES.get(name, name),
                "error": f"rate_limited (cooldown {int(_cooldown_left(name))}s, tanpa cache)",
            }
        try:
            async with _new_client() as http:
                payload = await fetch(now_utc, http)
            block = dict(payload)
            block["status"] = "ok"
            block["fetched_at"] = _iso(now_utc)
            _CACHE[name] = {"block": copy.deepcopy(block), "mono": mono_now, "wall": time.time()}
            _disk_write(name, block)
            return block
        except Exception as exc:  # noqa: BLE001 - kontrak: gagal fetch tidak raise
            reason = f"{type(exc).__name__}: {exc}"[:200]
            if entry is not None and (time.time() - entry["wall"]) <= STALE_MAX_AGE_S:
                block = copy.deepcopy(entry["block"])
                block["status"] = "stale"
                block["stale_reason"] = reason
                return block
            # Cache disk hanya untuk warm-start (proses baru / memory kosong):
            # entry memory yang sudah kedaluwarsa tidak boleh "dihidupkan" lagi
            # oleh snapshot disk yang lebih tua.
            if entry is None:
                disk = _disk_read(name, STALE_MAX_AGE_S)
                if disk:
                    disk["status"] = "stale"
                    disk["stale_reason"] = f"{reason} (cache disk)"
                    return disk
            return {
                "status": "unavailable",
                "fetched_at": _iso(now_utc),
                "as_of": None,
                "source": _SOURCE_NAMES.get(name, name),
                "error": reason,
            }


async def fetch_calendar(now_utc: datetime | None = None) -> dict:
    """Ambil blok calendar dengan cache (dipakai juga oleh risk gate LLM).

    Envelope status: "ok" | "stale" | "unavailable" (lihat modul docstring).
    Dipakai oleh llm_risk.calendar_blackout_reason (t_d9e6b2a3): API tidak
    percaya kalender yang dikirim agent; gate self-contained via fungsi ini.
    """
    if now_utc is None:
        now_utc = datetime.now(timezone.utc)
    return await _get_block(
        "calendar", _ttl("CALENDAR", TTL_CALENDAR_S), _fetch_calendar, now_utc,
    )


async def collect_extras(now_utc: datetime) -> dict:
    """Kumpulkan sentiment + fundamental + calendar untuk konteks LLM.

    Aman dipanggil dengan now_utc naive (dianggap UTC). Tidak pernah raise:
    blok yang gagal mendapat status "stale" (jika ada cache <= 24 jam) atau
    "unavailable" + alasan.
    """
    if now_utc.tzinfo is None:
        now_utc = now_utc.replace(tzinfo=timezone.utc)
    results = await asyncio.gather(
        _get_block("sentiment", _ttl("SENTIMENT", TTL_SENTIMENT_S), _fetch_sentiment, now_utc),
        _get_block("fundamental", _ttl("FUNDAMENTAL", TTL_FUNDAMENTAL_S), _fetch_fundamental, now_utc),
        _get_block("calendar", _ttl("CALENDAR", TTL_CALENDAR_S), _fetch_calendar, now_utc),
        return_exceptions=True,
    )
    out: dict = {}
    for name, res in zip(("sentiment", "fundamental", "calendar"), results):
        if isinstance(res, BaseException):  # pertahanan terakhir (harusnya tak terjadi)
            out[name] = {
                "status": "unavailable",
                "fetched_at": _iso(now_utc),
                "as_of": None,
                "source": _SOURCE_NAMES.get(name, name),
                "error": f"{type(res).__name__}: {res}"[:200],
            }
        else:
            out[name] = res
    return out
