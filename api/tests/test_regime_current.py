"""Tests GET /regime/current (PRD v2.2 §6/§21, task UI-D0).

Unit murni: build_regime_snapshot - label stabil dari fixture candle
(generator sama dengan test_regime.py), stale bila data tidak layak.
Integration: endpoint dengan DB test - candle kosong -> HTTP 200 stale,
fixture candle -> label + confidence + age, auth 401 tanpa login,
terdaftar di /openapi.json.
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

import pytest
from httpx import ASGITransport, AsyncClient

from app import db, market, regime
from app.main import app
from app.regime_current import build_regime_snapshot

UTC = timezone.utc
SYMBOL = "XAUUSD"
T0 = datetime(2026, 11, 16, 2, 0, tzinfo=UTC)  # Senin, sesi asia


def noise(i: float) -> float:
    """Pseudo-noise deterministik (tanpa RNG): sama dengan test_regime.py."""
    return 0.4 * math.sin(i * 1.7) + 0.2 * math.cos(i * 0.9)


def make_bars(n: int, gen, start: datetime = T0, tf_min: int = 5) -> list[dict]:
    out = []
    for i in range(n):
        o, h, l, c = gen(i)
        out.append({"ts": (start + timedelta(minutes=tf_min * i)).isoformat(),
                    "open": round(o, 4), "high": round(h, 4),
                    "low": round(l, 4), "close": round(c, 4), "volume": 0})
    return out


def gen_uptrend(i, base=2000.0, step=0.8):
    c = base + step * i + noise(i)
    return c - 0.2, c + 0.6, c - 0.5, c


def liq(now, spread=0.30, median15=0.25, fresh=True):
    return {"ts": now.isoformat(), "spread": spread,
            "spread_median_15m": median15, "fresh": fresh}


# ---------------------------------------------------------------- unit murni

def test_snapshot_happy_path_label_stabil():
    """Fixture candle uptrend -> label stabil + field response lengkap."""
    now = T0 + timedelta(minutes=5 * 300)
    candles = make_bars(300, gen_uptrend)
    snap = build_regime_snapshot(symbol=SYMBOL, now=now, candles=candles,
                                 liquidity=liq(now))
    # Determinisme: input sama -> label sama (classifier murni, PRD §6.5).
    again = build_regime_snapshot(symbol=SYMBOL, now=now, candles=candles,
                                  liquidity=liq(now))
    assert snap["label"] == again["label"] == "TREND_UP"
    assert snap["stale"] is False
    assert 0.0 <= snap["confidence"] <= 1.0
    assert snap["candle_ts"] == candles[-1]["ts"]
    assert snap["ts"]  # anchor close bar terakhir
    assert snap["age_s"] is not None and snap["age_s"] >= 0
    assert snap["degrade_reason"] is None
    assert snap["reason"]
    # Strategi XAUUSD yang lolos gerbang regime utk label ini.
    assert set(snap["allowed_strategies"]) <= {"london_breakout",
                                               "mean_reversion"}
    assert snap["allowed_count"] == len(snap["allowed_strategies"])


def test_snapshot_stale_without_candles():
    snap = build_regime_snapshot(symbol=SYMBOL, now=T0, candles=[],
                                 liquidity=None)
    assert snap["label"] is None
    assert snap["stale"] is True
    assert snap["reason"] and snap["degrade_reason"]
    assert snap["allowed_strategies"] == [] and snap["allowed_count"] == 0


def test_snapshot_stale_when_bars_insufficient():
    """Bar < min_bars -> UNKNOWN (kondisi aman) -> label null + stale."""
    now = T0 + timedelta(minutes=5 * 20)
    snap = build_regime_snapshot(symbol=SYMBOL, now=now,
                                 candles=make_bars(20, gen_uptrend),
                                 liquidity=liq(now))
    assert snap["label"] is None
    assert snap["stale"] is True
    assert "min_bars" in snap["reason"]


def test_snapshot_stale_when_liquidity_missing():
    """Spread tidak tersedia -> UNKNOWN (PRD §6.2), bukan crash."""
    now = T0 + timedelta(minutes=5 * 300)
    snap = build_regime_snapshot(symbol=SYMBOL, now=now,
                                 candles=make_bars(300, gen_uptrend),
                                 liquidity=None)
    assert snap["label"] is None
    assert snap["stale"] is True
    assert "spread" in snap["reason"].lower()


def test_snapshot_stale_when_classifier_raises():
    """Classifier raise -> label null + stale (endpoint tetap 200)."""
    bad = [{"ts": "bukan-tanggal", "open": 1, "high": 1, "low": 1,
            "close": 1}]
    snap = build_regime_snapshot(symbol=SYMBOL, now=T0, candles=bad,
                                 liquidity=liq(T0))
    assert snap["label"] is None
    assert snap["stale"] is True
    assert snap["reason"]


# ---------------------------------------------------------------- integration

async def _insert_candles(n=300, symbol=SYMBOL, end=None):
    """n bar M5 closed berurutan (uptrend) berakhir ~2 menit lalu.

    Bar disisipkan kontinu; gap break harian/akhir pekan BUKAN data buruk
    (dikecualikan classifier, PRD §6.2), jadi aman untuk jam test apa pun.
    """
    end = end or datetime.now(timezone.utc) - timedelta(minutes=7)
    start = end - timedelta(minutes=5 * (n - 1))
    rows = []
    price = 2000.0
    for i in range(n):
        price += 0.8 + noise(i)
        ts = start + timedelta(minutes=5 * i)
        rows.append((symbol, "M5", ts, round(price - 0.2, 4),
                     round(price + 0.6, 4), round(price - 0.5, 4),
                     round(price, 4)))
    async with db.pool().connection() as conn:
        placeholders = ", ".join(["(%s, %s, %s, %s, %s, %s, %s)"] * n)
        await conn.execute(
            "INSERT INTO candles (symbol, timeframe, ts, open, high, low, close) "
            f"VALUES {placeholders}",
            [v for row in rows for v in row])


async def test_regime_current_empty_db_stale(client):
    """Tabel candle kosong -> HTTP 200 + label null + stale (bukan error)."""
    resp = await client.get("/regime/current", params={"symbol": "XAUUSD"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["symbol"] == "XAUUSD"
    assert body["label"] is None
    assert body["stale"] is True
    assert body["reason"]
    for field in ("confidence", "ts", "candle_ts", "age_s"):
        assert body[field] is None


async def test_regime_current_happy_path(client):
    """Fixture candle + tick -> label + confidence + age + allowed strategies."""
    market.update_tick("XAUUSD", bid=1999.85, ask=2000.15)  # spread 0.30
    await _insert_candles()
    resp = await client.get("/regime/current", params={"symbol": "XAUUSD"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["label"] == "TREND_UP"
    assert body["stale"] is False
    assert isinstance(body["confidence"], float)
    assert body["age_s"] is not None and body["age_s"] < 600
    assert body["candle_ts"] and body["ts"]
    assert set(body["allowed_strategies"]) <= {"london_breakout",
                                               "mean_reversion"}
    assert body["allowed_count"] == len(body["allowed_strategies"])


async def test_regime_current_unknown_symbol_stale(client):
    """Simbol tanpa data -> stale HTTP 200 (bukan 404/500)."""
    resp = await client.get("/regime/current", params={"symbol": "NOPE"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["symbol"] == "NOPE"
    assert body["label"] is None and body["stale"] is True


async def test_regime_current_requires_auth(user):
    """Tanpa session cookie -> 401 (auth get_current_user)."""
    async with AsyncClient(transport=ASGITransport(app=app),
                           base_url="http://test") as anon:
        r = await anon.get("/regime/current", params={"symbol": "XAUUSD"})
        assert r.status_code == 401


async def test_regime_current_in_openapi(client):
    """DoD: endpoint terdaftar di /openapi.json."""
    resp = await client.get("/openapi.json")
    assert resp.status_code == 200
    assert "/regime/current" in resp.json()["paths"]
