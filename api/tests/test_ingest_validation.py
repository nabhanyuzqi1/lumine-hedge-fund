"""Endpoint /bridge/tick: validasi PRD 4.4 terintegrasi (schema_version
tidak didukung -> 422; tick rusak -> skipped + counter; candle rusak ->
tidak masuk antrean)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app import market, validate


def _auth(token):
    return {"Authorization": "Bearer " + token}


def _fresh_ms(offset_s: int = 0) -> int:
    return int((datetime.now(timezone.utc)
                + timedelta(seconds=offset_s)).timestamp() * 1000)


async def test_tick_schema_version_unsupported_rejected(client, bridge_token):
    resp = await client.post(
        "/bridge/tick",
        json={"symbol": "XAUUSD", "ticks": [{"ts": _fresh_ms(), "bid": 2000.0,
                                             "ask": 2000.3}],
              "schema_version": "v99"},
        headers=_auth(bridge_token),
    )
    assert resp.status_code == 422
    assert "schema_version" in resp.json()["detail"]


async def test_tick_schema_version_supported_accepted(client, bridge_token):
    validate.reset_validator()
    resp = await client.post(
        "/bridge/tick",
        json={"symbol": "XAUUSD", "ticks": [{"ts": _fresh_ms(), "bid": 2000.0,
                                             "ask": 2000.3}],
              "schema_version": "v5"},
        headers=_auth(bridge_token),
    )
    assert resp.status_code == 200
    assert resp.json()["ticks"] == 1


async def test_invalid_tick_skipped_with_counter(client, bridge_token):
    """ask < bid -> tick ditolak, tidak masuk market store; respons
    melaporkan rejected=1 (PRD 4.4)."""
    validate.reset_validator()
    resp = await client.post(
        "/bridge/tick",
        json={"symbol": "XAUUSD",
              "ticks": [{"ts": _fresh_ms(), "bid": 2000.5, "ask": 2000.2},
                        {"ts": _fresh_ms(), "bid": 2000.0, "ask": 2000.3}]},
        headers=_auth(bridge_token),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ticks"] == 1        # tick valid tetap masuk
    assert body["rejected"] == 1     # tick ask<bid ditolak
    t = market.latest("XAUUSD")
    assert t["bid"] == 2000.0        # yang tersimpan tick valid


async def test_invalid_candle_not_queued(client, bridge_token):
    """Candle OHLC pecah ditolak di pipeline, tidak di-flush ke DB."""
    validate.reset_validator()
    resp = await client.post(
        "/bridge/tick",
        json={"symbol": "XAUUSD", "ticks": [],
              "candles": [{"symbol": "XAUUSD", "timeframe": "M1",
                           "ts": "2026-11-21T10:00:00Z",
                           "open": 2000, "high": 1999.0, "low": 2001.0,
                           "close": 2000.2, "volume": 5}]},
        headers=_auth(bridge_token),
    )
    assert resp.status_code == 200
    assert resp.json()["rejected"] == 1  # candle ditolak dilaporkan
    from app import db
    from app.state_machine import fetchone
    async with db.pool().connection() as conn:
        row = await fetchone(
            conn, "SELECT * FROM candles WHERE symbol='XAUUSD' "
                  "AND timeframe='M1' AND ts='2026-11-21T10:00:00+00:00'")
    assert row is None


async def test_duplicate_candle_reseed_ok(client, bridge_token):
    """Seed ulang candle sama (idempotent upsert) tetap diterima."""
    validate.reset_validator()
    payload = {"symbol": "XAUUSD", "ticks": [],
               "candles": [{"symbol": "XAUUSD", "timeframe": "M1",
                            "ts": "2026-11-21T10:00:00Z",
                            "open": 2000, "high": 2001.5, "low": 1999.5,
                            "close": 2001.2, "volume": 123}]}
    for _ in range(2):
        resp = await client.post("/bridge/tick", json=payload,
                                 headers=_auth(bridge_token))
        assert resp.status_code == 200
        assert resp.json()["flagged"] == 0
