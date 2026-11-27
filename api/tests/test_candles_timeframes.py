"""Tests: GET /candles mendukung timeframe tinggi H1/H4/D1 (BACKEND-C1 lanjutan).

DoD: H1/H4/D1 diterima dan membaca baris tabel candles per timeframe, alias
'1h'/'4h'/'1d'/'60m' memetakan ke bentuk kanonik, tf ngawur tetap 400, dan
perilaku M1/M5/M15 (whitelist lama) tidak berubah. Bentuk response tetap:
{symbol, tf, count, candles: [{ts, open, high, low, close, volume}]}.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.main import app  # noqa: F401  (memastikan router sudah terpasang)
from app import db

UTC = timezone.utc
T0 = datetime(2026, 11, 20, 0, 0, tzinfo=UTC)

# menit per bar untuk seed data
STEP_MIN = {"M1": 1, "M5": 5, "M15": 15, "H1": 60, "H4": 240, "D1": 1440}


async def _insert_candles(symbol="XAUUSD", tf="H1", n=3, start=T0, base=2000.0):
    """n bar berurutan per timeframe dengan OHLCV deterministik."""
    step_min = STEP_MIN[tf]
    rows = []
    for i in range(n):
        o = base + i
        rows.append((symbol, tf, start + timedelta(minutes=step_min * i),
                     o, o + 1.0, o - 1.0, o + 0.5, 100.0 + i))
    async with db.pool().connection() as conn:
        placeholders = ", ".join(["( %s, %s, %s, %s, %s, %s, %s, %s )"] * n)
        await conn.execute(
            "INSERT INTO candles (symbol, timeframe, ts, open, high, low, close, "
            f"volume) VALUES {placeholders}",
            [v for r in rows for v in r])


# ---------------------------------------------------------------- H1/H4/D1


async def test_candles_accepts_h1_h4_d1(client):
    """H1/H4/D1 -> 200, tf kanonik di response, shape response tidak berubah."""
    for tf in ("H1", "H4", "D1"):
        await _insert_candles(tf=tf, n=3, base=2000.0)
        resp = await client.get("/candles", params={"symbol": "XAUUSD", "tf": tf})
        assert resp.status_code == 200, (tf, resp.text)
        body = resp.json()
        assert set(body.keys()) == {"symbol", "tf", "count", "candles"}, tf
        assert body["symbol"] == "XAUUSD"
        assert body["tf"] == tf
        assert body["count"] == 3
        for c in body["candles"]:
            assert set(c.keys()) == {"ts", "open", "high", "low", "close", "volume"}
            for field in ("open", "high", "low", "close", "volume"):
                assert isinstance(c[field], float), (tf, field)
            ts = datetime.fromisoformat(c["ts"])
            assert ts.tzinfo is not None and ts.utcoffset() == timedelta(0)
        # oldest-first, deterministik dari seed
        tss = [datetime.fromisoformat(c["ts"]) for c in body["candles"]]
        assert tss == sorted(tss), tf
        assert body["candles"][0]["open"] == 2000.0, tf


async def test_candles_h1_limit_300_reads_newest_from_table(client):
    """Kontrak tugas: ?symbol=XAUUSD&tf=H1&limit=300 -> 300 bar terbaru."""
    await _insert_candles(tf="H1", n=305)
    resp = await client.get(
        "/candles", params={"symbol": "XAUUSD", "tf": "H1", "limit": 300})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["tf"] == "H1"
    assert body["count"] == 300
    opens = [c["open"] for c in body["candles"]]
    # 300 dari 305 (i=5..304), disajikan oldest-first
    assert opens == [2000.0 + i for i in range(5, 305)]


async def test_candles_tf_alias_high_timeframes(client):
    """Alias '1h'/'4h'/'1d'/'60m' -> H1/H4/D1; huruf besar/kecil sama."""
    await _insert_candles(tf="H1", n=2)
    await _insert_candles(tf="H4", n=2)
    await _insert_candles(tf="D1", n=2)
    cases = {"1h": "H1", "H1": "H1", "60m": "H1", "60M": "H1",
             "4h": "H4", "H4": "H4", "240m": "H4",
             "1d": "D1", "D1": "D1", "1440m": "D1"}
    for alias, canonical in cases.items():
        resp = await client.get(
            "/candles", params={"symbol": "XAUUSD", "tf": alias})
        assert resp.status_code == 200, (alias, resp.text)
        body = resp.json()
        assert body["tf"] == canonical, alias
        assert body["count"] == 2, alias
    # Konvensi lama dipertahankan: bentuk kanonik huruf kecil ('m5', 'h1')
    # memang bukan alias yang didukung -> tetap 400 seperti sebelumnya.
    for tf in ("m5", "h1"):
        resp = await client.get("/candles", params={"symbol": "XAUUSD", "tf": tf})
        assert resp.status_code == 400, tf


async def test_candles_high_tf_filtered_per_symbol_and_timeframe(client):
    """H4 BTCUSD tidak bercampur dengan H4 XAUUSD maupun M5."""
    await _insert_candles(symbol="XAUUSD", tf="H4", n=2)
    await _insert_candles(symbol="BTCUSD", tf="H4", n=3, base=90000.0)
    await _insert_candles(symbol="BTCUSD", tf="M5", n=4)
    resp = await client.get("/candles", params={"symbol": "BTCUSD", "tf": "H4"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["symbol"] == "BTCUSD" and body["tf"] == "H4"
    assert body["count"] == 3
    assert all(c["open"] > 80000 for c in body["candles"])


async def test_candles_high_tf_empty_result_200(client):
    """Whitelisted tf tanpa baris -> 200 dengan candles: [] (bukan 400)."""
    resp = await client.get("/candles", params={"symbol": "BTCUSD", "tf": "D1"})
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"symbol": "BTCUSD", "tf": "D1", "count": 0,
                           "candles": []}


# ---------------------------------------------------------------- regresi & 400


async def test_candles_m1_m5_m15_unchanged(client):
    """Whitelist lama tetap identik: M1/M5/M15 200 dan count sesuai."""
    for tf in ("M1", "M5", "M15"):
        await _insert_candles(tf=tf, n=4, base=3000.0)
        resp = await client.get("/candles", params={"symbol": "XAUUSD", "tf": tf})
        assert resp.status_code == 200, (tf, resp.text)
        body = resp.json()
        assert body["tf"] == tf and body["count"] == 4, tf


async def test_candles_unknown_tf_still_400(client):
    """tf di luar whitelist/alias tetap 400 (kontrak validasi tidak longgar)."""
    for tf in ("M2", "abc", "H2", "H12", "1w", "D2", "", " "):
        resp = await client.get("/candles", params={"symbol": "XAUUSD", "tf": tf})
        assert resp.status_code == 400, (tf, resp.status_code)


async def test_candles_high_tf_bad_limit_and_symbol_still_400(client):
    """Validasi limit/symbol tidak berubah untuk tf baru."""
    for params in ({"symbol": "XAUUSD", "tf": "H1", "limit": 0},
                   {"symbol": "XAUUSD", "tf": "H4", "limit": 2001},
                   {"symbol": "EURUSD", "tf": "D1"}):
        resp = await client.get("/candles", params=params)
        assert resp.status_code == 400, (params, resp.status_code)
