"""Tests: gate order 409 saat pasar tutup (kartu candle pipeline).

DoD:
- POST /orders menolak order BARU dengan 409
  {detail: 'Market sedang tutup — order baru dinonaktifkan hingga sesi buka',
   code: 'market_closed'} ketika status simbol CLOSED, dan TIDAK membuat baris
  order (penolakan di depan, sebelum gate risk/LLM);
- berlaku juga untuk order agent/LLM (role agent / strategy 'llm');
- order tetap lolos (201) saat pasar OPEN;
- CLOSE/exit yang sudah ada tidak diblokir (flatten tetap membuat order CLOSE);
- gate hanya aktif bila ada jalur eksekusi (EA terhubung): tanpa EA tidak ada
  penolakan berbasis jam dinding (lihat app/market_status.enforceable).
"""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from app import db, ingest, kill_switch, market_status
from app.state_machine import fetchall

WIB = ZoneInfo("Asia/Jakarta")
HEADERS_KEY = "Authorization"


def _body(**overrides):
    body = {"symbol": "XAUUSD", "side": "BUY", "volume": 0.1,
            "sl": 1998.0, "tp": 2005.0}
    body.update(overrides)
    return body


def _wib(y, mo, d, h, mi=0) -> datetime:
    return datetime(y, mo, d, h, mi, tzinfo=WIB)


@pytest.fixture(autouse=True)
def _clean_registry():
    market_status.clear()
    yield
    market_status.clear()
    kill_switch._ea_seen_mono = None


async def _heartbeat(client, token, **fields):
    payload = {"symbol": "XAUUSD", **fields}
    resp = await client.post("/bridge/heartbeat", json=payload,
                             headers={HEADERS_KEY: f"Bearer {token}"})
    assert resp.status_code == 200, resp.text


async def _order_count() -> int:
    async with db.pool().connection() as conn:
        rows = await fetchall(conn, "SELECT count(*) AS n FROM orders")
    return int(rows[0]["n"])


async def test_order_rejected_409_when_market_closed(client, bridge_token, tick_2000):
    await _heartbeat(client, bridge_token, market_status="CLOSED",
                     market_close_reason="weekend", trade_mode="CLOSEONLY")
    resp = await client.post("/orders", json=_body())
    assert resp.status_code == 409, resp.text
    body = resp.json()
    assert body["code"] == "market_closed"
    assert body["detail"] == ("Market sedang tutup — order baru dinonaktifkan "
                             "hingga sesi buka")
    assert await _order_count() == 0, "order ditolak pasar tetap tercatat"


async def test_order_passes_when_market_open(client, bridge_token, tick_2000):
    await _heartbeat(client, bridge_token, market_status="OPEN", trade_mode="FULL")
    resp = await client.post("/orders", json=_body())
    assert resp.status_code == 201, resp.text
    assert resp.json()["status"] == "RISK_PASS"


async def test_agent_order_blocked_too(client, bridge_token, tick_2000):
    """Order LLM/agent melewati endpoint yang sama -> juga 409."""
    await _heartbeat(client, bridge_token, market_status="CLOSED",
                     market_close_reason="session")
    resp = await client.post("/orders", json=_body(strategy="llm"))
    assert resp.status_code == 409, resp.text
    assert resp.json()["code"] == "market_closed"
    assert await _order_count() == 0


async def test_closed_but_ea_absent_does_not_block(client, tick_2000, monkeypatch):
    """Tanpa jalur eksekusi (EA tidak terhubung) gate tidak menebak dari jam.

    Status pasar tetap CLOSED menurut jadwal (bisa dilihat di /market/status),
    tapi tanpa EA tidak ada yang bisa mengeksekusi order; penolakan berbasis
    jam dinding saja akan mengunci order sah (mis. suite test di jendela tutup).
    """
    monkeypatch.setattr(market_status, "now_utc", lambda: _wib(2026, 11, 28, 6, 30))
    resp = await client.post("/orders", json=_body())
    assert resp.status_code == 201, resp.text


async def test_close_orders_not_blocked(client, bridge_token, tick_2000):
    """Posisi yang sudah ada tetap bisa ditutup (flatten) saat pasar tutup."""
    async with db.pool().connection() as conn:
        await conn.execute(
            "INSERT INTO positions (ticket, symbol, side, volume, open_price, "
            "status, profit) VALUES (9001, 'XAUUSD', 'BUY', 0.1, 2000.0, 'OPEN', 0)"
        )
    await _heartbeat(client, bridge_token, market_status="CLOSED",
                     market_close_reason="weekend")
    created = await kill_switch.flatten_positions(actor="tester", source="test")
    assert len(created) == 1, created
    async with db.pool().connection() as conn:
        rows = await fetchall(
            conn, "SELECT action, status FROM orders WHERE action = 'CLOSE'")
    assert rows and rows[0]["action"] == "CLOSE"
    # order CLOSE tetap boleh dibuat (tidak lewat gate pasar)
    assert rows[0]["status"] in ("RISK_PASS", "RECEIVED")


async def test_ingest_pipeline_not_disturbed_by_gate(client, bridge_token, tick_2000):
    """Gate order tidak menyentuh pipeline candle (tick tetap masuk)."""
    p = ingest.get_pipeline()
    await _heartbeat(client, bridge_token, market_status="CLOSED")
    before = p.ticks_buffered
    resp = await client.post("/bridge/tick",
                             json={"symbol": "XAUUSD", "bid": 2000.1, "ask": 2000.4},
                             headers={HEADERS_KEY: f"Bearer {bridge_token}"})
    assert resp.status_code == 200
    assert p.ticks_buffered == before + 1
