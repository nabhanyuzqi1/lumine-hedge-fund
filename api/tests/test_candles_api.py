"""Tests: GET /candles read-only untuk chart candlestick (BACKEND-C1, UI-D5).

DoD: auth 401, validasi param 400, shape response, konversi UTC benar
(dibandingkan dengan to_utc_candles), dan empty result -> candles: [].
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from httpx import ASGITransport, AsyncClient

from app import db
from app.main import app
from paper.backtest import to_utc_candles
from paper.runner import db_timezone_offset_h

UTC = timezone.utc
T0 = datetime(2026, 11, 20, 10, 0, tzinfo=UTC)


def _anon_client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def _insert_candles(symbol="XAUUSD", tf="M5", n=5, start=T0, step_min=5,
                          base=2000.0):
    """n bar berurutan dengan OHLCV deterministik (ts = instan UTC)."""
    rows = []
    for i in range(n):
        o = base + i
        rows.append((symbol, tf, start + timedelta(minutes=step_min * i),
                     o, o + 1.0, o - 1.0, o + 0.5, 100.0 + i))
    async with db.pool().connection() as conn:
        placeholders = ", ".join(["(%s, %s, %s, %s, %s, %s, %s, %s)"] * n)
        await conn.execute(
            "INSERT INTO candles (symbol, timeframe, ts, open, high, low, close, "
            f"volume) VALUES {placeholders}",
            [v for r in rows for v in r])


# ---------------------------------------------------------------- auth


async def test_candles_requires_auth():
    """Tanpa login -> 401 (pola GET read-only existing)."""
    async with _anon_client() as c:
        resp = await c.get("/candles", params={"symbol": "XAUUSD", "tf": "M5"})
    assert resp.status_code == 401


# ---------------------------------------------------------------- validasi param


async def test_candles_bad_symbol_rejected_400(client):
    for sym in ("EURUSD", "XAUXAU", "XAU"):
        resp = await client.get("/candles", params={"symbol": sym, "tf": "M5"})
        assert resp.status_code == 400, sym


async def test_candles_bad_tf_rejected_400(client):
    """M2/abc/H2 bukan TF kanonik maupun alias chart (H1/H4/D1 kini didukung)."""
    for tf in ("M2", "abc", "H2", "1w"):
        resp = await client.get("/candles", params={"symbol": "XAUUSD", "tf": tf})
        assert resp.status_code == 400, tf


async def test_candles_bad_limit_rejected_400(client):
    for limit in (0, -5, 2001):
        resp = await client.get(
            "/candles", params={"symbol": "XAUUSD", "tf": "M5", "limit": limit})
        assert resp.status_code == 400, limit


async def test_candles_symbol_case_and_tf_alias(client):
    """xauusd -> XAUUSD; tf alias '5m' -> M5 (canonical_tf)."""
    await _insert_candles(n=2)
    resp = await client.get("/candles", params={"symbol": "xauusd", "tf": "5m"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["symbol"] == "XAUUSD"
    assert body["tf"] == "M5"
    assert body["count"] == 2


# ---------------------------------------------------------------- shape & urutan


async def test_candles_shape_oldest_first_floats(client):
    await _insert_candles(n=5)
    resp = await client.get("/candles", params={"symbol": "XAUUSD", "tf": "M5"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert set(body.keys()) == {"symbol", "tf", "count", "candles"}
    assert body["symbol"] == "XAUUSD"
    assert body["tf"] == "M5"
    assert body["count"] == 5
    assert len(body["candles"]) == 5
    for c in body["candles"]:
        assert set(c.keys()) == {"ts", "open", "high", "low", "close", "volume"}
        for field in ("open", "high", "low", "close", "volume"):
            assert isinstance(c[field], float), field
        ts = datetime.fromisoformat(c["ts"])
        assert ts.tzinfo is not None
        assert ts.utcoffset() == timedelta(0)  # ISO UTC
    # oldest-first, ketat meningkat
    tss = [datetime.fromisoformat(c["ts"]) for c in body["candles"]]
    assert tss == sorted(tss)
    assert len(set(tss)) == len(tss)
    # nilai bar pertama sesuai seed (o=2000.0)
    first = body["candles"][0]
    assert (first["open"], first["high"], first["low"], first["close"],
            first["volume"]) == (2000.0, 2001.0, 1999.0, 2000.5, 100.0)


async def test_candles_limit_returns_newest_oldest_first(client):
    await _insert_candles(tf="M1", n=10, step_min=1)
    resp = await client.get(
        "/candles", params={"symbol": "XAUUSD", "tf": "M1", "limit": 3})
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 3
    # 3 bar TERBARU (i=7,8,9), disajikan oldest-first
    assert [c["open"] for c in body["candles"]] == [2007.0, 2008.0, 2009.0]
    # default limit 500 -> semua 10 bar
    resp = await client.get("/candles", params={"symbol": "XAUUSD", "tf": "M1"})
    assert resp.status_code == 200
    assert resp.json()["count"] == 10


async def test_candles_filter_symbol_and_tf(client):
    await _insert_candles(symbol="XAUUSD", tf="M5", n=2)
    await _insert_candles(symbol="BTCUSD", tf="M5", n=3, base=90000.0)
    await _insert_candles(symbol="XAUUSD", tf="M15", n=4, step_min=15)
    resp = await client.get("/candles", params={"symbol": "XAUUSD", "tf": "M5"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 2
    assert all(c["open"] < 3000 for c in body["candles"])


# ---------------------------------------------------------------- konversi UTC


async def test_candles_utc_conversion_matches_to_utc_candles(client):
    """DoD: ts response == hasil helper teruji to_utc_candles (baris sama)."""
    await _insert_candles(n=4)
    async with db.pool().connection() as conn:
        offset_h = await db_timezone_offset_h(conn)
        cur = await conn.execute(
            "SELECT ts, open, high, low, close, volume FROM candles "
            "WHERE symbol = 'XAUUSD' AND timeframe = 'M5' ORDER BY ts ASC")
        rows = await cur.fetchall()
    expected = to_utc_candles(rows, offset_h)
    resp = await client.get("/candles", params={"symbol": "XAUUSD", "tf": "M5"})
    assert resp.status_code == 200
    got = resp.json()["candles"]
    assert [c["ts"] for c in got] == [e["ts"].isoformat() for e in expected]
    for g, e in zip(got, expected):
        assert (g["open"], g["high"], g["low"], g["close"], g["volume"]) == (
            e["open"], e["high"], e["low"], e["close"], e["volume"])


# ---------------------------------------------------------------- empty result


async def test_candles_empty_result(client):
    """Symbol+tf whitelisted tanpa data -> 200, candles: [] (bukan error)."""
    resp = await client.get("/candles", params={"symbol": "BTCUSD", "tf": "M15"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body == {"symbol": "BTCUSD", "tf": "M15", "count": 0, "candles": []}
