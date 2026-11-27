"""Tests: GET /market/status + POST /bridge/heartbeat (kartu candle pipeline).

DoD kontrak:
- shape response persis {symbol, market_status, market_close_reason, trade_mode,
  last_tick_ts, last_tick_age_s, next_open_ts, ea_seen_s, source};
- OPEN/CLOSED/UNKNOWN dari laporan EA -> jadwal market_sessions -> bukti feed;
- BTCUSD (sesi 24/7) tidak pernah CLOSED karena jadwal;
- fallback sesi: jendela harian & akhir pekan XAUUSD menghasilkan CLOSED dengan
  alasan 'session' / 'weekend' + next_open_ts terisi;
- heartbeat menerima field baru secara opsional (tanpa 422, legacy tetap sah),
  menyimpan status terakhir in-memory + persist throttled, dan mem-publish SSE
  type='market' hanya saat status berubah.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from app import db, kill_switch, market_status
from app.sse import broadcaster

WIB = ZoneInfo("Asia/Jakarta")
CONTRACT_KEYS = {
    "symbol", "market_status", "market_close_reason", "trade_mode",
    "last_tick_ts", "last_tick_age_s", "next_open_ts", "ea_seen_s", "source",
}


def _wib(y, mo, d, h, mi=0) -> datetime:
    return datetime(y, mo, d, h, mi, tzinfo=WIB)


def _xau_rows() -> list[dict]:
    """Salinan seed migrasi o015: XAUUSD Senin-Jumat 06:00 -> 04:59 WIB."""
    return [
        {"symbol": "XAUUSD", "weekday": wd, "open_minute": 360,
         "close_minute": 299, "timezone": "Asia/Jakarta", "enabled": True}
        for wd in range(5)
    ]


def _btc_rows() -> list[dict]:
    return [
        {"symbol": "BTCUSD", "weekday": wd, "open_minute": 0,
         "close_minute": 1440, "timezone": "Asia/Jakarta", "enabled": True}
        for wd in range(7)
    ]


@pytest.fixture(autouse=True)
def _clean_registry():
    """Registry status in-memory harus bersih per test (state lintas test = bug)."""
    market_status.clear()
    yield
    market_status.clear()
    kill_switch._ea_seen_mono = None


# ---------------------------------------------------------------- decide (murni)


def test_decide_open_from_session_window():
    now = _wib(2026, 11, 26, 7, 30)  # Kamis pagi
    status = market_status.decide("XAUUSD", rows=_xau_rows(), now=now)
    assert status["market_status"] == "OPEN"
    assert status["market_close_reason"] is None
    assert status["source"] == "session"
    assert status["trade_mode"] is None


def test_decide_closed_daily_break_reason_session():
    now = _wib(2026, 11, 26, 5, 30)  # jeda harian 04:59-06:00 WIB
    status = market_status.decide("XAUUSD", rows=_xau_rows(), now=now)
    assert status["market_status"] == "CLOSED"
    assert status["market_close_reason"] == "session"


def test_decide_closed_weekend_reason_weekend():
    now = _wib(2026, 11, 28, 6, 30)  # Sabtu
    status = market_status.decide("XAUUSD", rows=_xau_rows(), now=now)
    assert status["market_status"] == "CLOSED"
    assert status["market_close_reason"] == "weekend"


def test_decide_btc_never_closed_by_schedule():
    """BTCUSD 24/7: Sabtu dini hari tetap OPEN oleh jadwal."""
    for moment in (_wib(2026, 11, 28, 3, 0), _wib(2026, 11, 29, 23, 59),
                   _wib(2026, 11, 27, 5, 30)):
        status = market_status.decide("BTCUSD", rows=_btc_rows(), now=moment)
        assert status["market_status"] == "OPEN", moment
        assert status["source"] == "session"


def test_decide_ea_report_wins_over_schedule():
    """Laporan EA (mis. libur bursa/maintenance broker) menang atas jadwal."""
    now = _wib(2026, 11, 26, 7, 30)  # jadwal bilang buka
    rep = {"market_status": "CLOSED", "market_close_reason": "holiday",
           "trade_mode": "DISABLED", "age_s": 2.0}
    status = market_status.decide("XAUUSD", rows=_xau_rows(), now=now,
                                  report_entry=rep)
    assert status["market_status"] == "CLOSED"
    assert status["market_close_reason"] == "holiday"
    assert status["trade_mode"] == "DISABLED"
    assert status["source"] == "ea"


def test_decide_stale_ea_report_ignored():
    now = _wib(2026, 11, 28, 6, 30)  # Sabtu, jadwal tutup
    rep = {"market_status": "OPEN", "market_close_reason": None,
           "trade_mode": "FULL", "age_s": market_status.EA_STATUS_TTL_S + 30}
    status = market_status.decide("XAUUSD", rows=_xau_rows(), now=now,
                                  report_entry=rep)
    assert status["market_status"] == "CLOSED", "laporan EA basi tidak boleh dipercaya"
    assert status["source"] == "session"


def test_decide_unknown_without_schedule_and_feed():
    now = _wib(2026, 11, 26, 7, 30)
    status = market_status.decide("XAUUSD", rows=[], now=now, feed_age_s=None)
    assert status["market_status"] == "UNKNOWN"
    assert status["market_close_reason"] == "no_data"
    assert status["source"] == "derived"


def test_decide_feed_evidence_without_schedule_rows():
    now = _wib(2026, 11, 26, 7, 30)
    live = market_status.decide("XAUUSD", rows=[], now=now, feed_age_s=1.0)
    dead = market_status.decide("XAUUSD", rows=[], now=now,
                                feed_age_s=market_status.FEED_CLOSED_MIN_S + 60)
    assert (live["market_status"], live["source"]) == ("OPEN", "derived")
    assert (dead["market_status"], dead["market_close_reason"]) == ("CLOSED", "no_data")


def test_decide_tick_fields():
    now = _wib(2026, 11, 26, 7, 30)
    ts = now.timestamp() - 2.5
    status = market_status.decide("XAUUSD", rows=_xau_rows(), now=now,
                                  tick={"ts": ts}, ea_seen_s=1.4)
    assert status["last_tick_age_s"] == 2.5
    assert status["last_tick_ts"] is not None
    assert status["ea_seen_s"] == 1.4


# ---------------------------------------------------------------- endpoint


async def test_market_status_requires_auth():
    from httpx import ASGITransport, AsyncClient

    from app.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/market/status", params={"symbol": "XAUUSD"})
    assert resp.status_code == 401


async def test_market_status_open_with_contract_shape(client, tick_2000, monkeypatch):
    monkeypatch.setattr(market_status, "now_utc", lambda: _wib(2026, 11, 26, 7, 30))
    resp = await client.get("/market/status", params={"symbol": "xauusd"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert set(body.keys()) == CONTRACT_KEYS
    assert body["symbol"] == "XAUUSD"
    assert body["market_status"] == "OPEN"
    assert body["market_close_reason"] is None
    assert body["trade_mode"] is None
    assert body["source"] == "session"
    assert body["next_open_ts"] is None
    assert body["last_tick_age_s"] is not None and body["last_tick_age_s"] >= 0


async def test_market_status_closed_weekend_with_next_open(client, monkeypatch):
    monkeypatch.setattr(market_status, "now_utc", lambda: _wib(2026, 11, 28, 6, 30))
    body = (await client.get("/market/status", params={"symbol": "XAUUSD"})).json()
    assert body["market_status"] == "CLOSED"
    assert body["market_close_reason"] == "weekend"
    assert body["source"] == "session"
    assert body["next_open_ts"] is not None
    next_open = datetime.fromisoformat(body["next_open_ts"])
    assert next_open > _wib(2026, 11, 28, 6, 30)


async def test_market_status_btc_247_stays_open(client, monkeypatch):
    monkeypatch.setattr(market_status, "now_utc", lambda: _wib(2026, 11, 28, 6, 30))
    body = (await client.get("/market/status", params={"symbol": "BTCUSD"})).json()
    assert body["market_status"] == "OPEN"
    assert body["market_close_reason"] is None


async def test_market_status_unknown_without_session_rows(client, monkeypatch, tmp_path):
    from app import ingest

    ingest.reset_pipeline(parquet_dir=tmp_path)  # tanpa bukti feed sama sekali
    monkeypatch.setattr(market_status, "now_utc", lambda: _wib(2026, 11, 26, 7, 30))

    async def no_rows(conn, symbols):
        return {s: [] for s in symbols}

    monkeypatch.setattr(market_status.market_sessions, "load_rows", no_rows)
    body = (await client.get("/market/status", params={"symbol": "XAUUSD"})).json()
    assert body["market_status"] == "UNKNOWN"
    assert body["market_close_reason"] == "no_data"
    assert body["source"] == "derived"


# ---------------------------------------------------------------- heartbeat


async def test_heartbeat_legacy_payload_still_ok(client, bridge_token):
    resp = await client.post("/bridge/heartbeat", json={"ts": 1},
                             headers={"Authorization": f"Bearer {bridge_token}"})
    assert resp.status_code == 200
    assert resp.json()["ok"] is True


async def test_heartbeat_accepts_new_fields_without_422(client, bridge_token):
    resp = await client.post(
        "/bridge/heartbeat",
        json={"ts": 2, "symbol": "XAUUSD", "market_status": "closed",
              "market_close_reason": "HOLIDAY", "trade_mode": 2,
              "symbol_time": "2026.11.27 10:00", "tick_age_s": 1.5},
        headers={"Authorization": f"Bearer {bridge_token}"})
    assert resp.status_code == 200, resp.text
    rep = market_status.report("XAUUSD")
    assert rep is not None
    assert rep["market_status"] == "CLOSED"          # dinormalisasi
    assert rep["market_close_reason"] == "holiday"   # dinormalisasi
    assert rep["trade_mode"] == "DISABLED"           # int MT5 -> nama
    assert rep["symbol_time"] == "2026.11.27 10:00"
    assert rep["tick_age_s"] == 1.5


async def test_heartbeat_ignores_unknown_values(client, bridge_token):
    """Nilai asing diabaikan (bukan 422) dan tidak menimpa status yang sah."""
    headers = {"Authorization": f"Bearer {bridge_token}"}
    await client.post("/bridge/heartbeat",
                      json={"symbol": "XAUUSD", "market_status": "OPEN",
                            "trade_mode": "FULL"}, headers=headers)
    resp = await client.post(
        "/bridge/heartbeat",
        json={"symbol": "XAUUSD", "market_status": "MAYBE",
              "market_close_reason": "market_halted", "trade_mode": "WHATEVER"},
        headers=headers)
    assert resp.status_code == 200
    rep = market_status.report("XAUUSD")
    assert rep["market_status"] == "OPEN"
    assert rep["trade_mode"] == "FULL"
    assert rep["market_close_reason"] is None


async def test_heartbeat_status_drives_endpoint(client, bridge_token, monkeypatch):
    headers = {"Authorization": f"Bearer {bridge_token}"}
    monkeypatch.setattr(market_status, "now_utc", lambda: _wib(2026, 11, 26, 7, 30))
    await client.post("/bridge/heartbeat",
                      json={"symbol": "XAUUSD", "market_status": "CLOSED",
                            "market_close_reason": "broker", "trade_mode": "CLOSEONLY"},
                      headers=headers)
    body = (await client.get("/market/status", params={"symbol": "XAUUSD"})).json()
    assert body["market_status"] == "CLOSED"
    assert body["market_close_reason"] == "broker"
    assert body["trade_mode"] == "CLOSEONLY"
    assert body["source"] == "ea"


async def test_heartbeat_publishes_sse_only_on_change(client, bridge_token):
    headers = {"Authorization": f"Bearer {bridge_token}"}
    queue = broadcaster.subscribe()
    try:
        await client.post("/bridge/heartbeat",
                          json={"symbol": "XAUUSD", "market_status": "OPEN"},
                          headers=headers)
        await client.post("/bridge/heartbeat",
                          json={"symbol": "XAUUSD", "market_status": "OPEN"},
                          headers=headers)
        await client.post("/bridge/heartbeat",
                          json={"symbol": "XAUUSD", "market_status": "CLOSED",
                                "market_close_reason": "weekend"},
                          headers=headers)
        events = []
        while not queue.empty():
            events.append(queue.get_nowait())
    finally:
        broadcaster.unsubscribe(queue)
    market_events = [e for e in events if e.get("type") == "market"]
    assert [e["market_status"] for e in market_events] == ["OPEN", "CLOSED"]
    assert market_events[1]["market_close_reason"] == "weekend"


async def test_heartbeat_persists_status_throttled(client, bridge_token):
    headers = {"Authorization": f"Bearer {bridge_token}"}
    await client.post("/bridge/heartbeat",
                      json={"symbol": "XAUUSD", "market_status": "OPEN",
                            "trade_mode": "FULL"}, headers=headers)
    settings = await db.get_settings()
    stored = settings.get(market_status.SETTINGS_KEY)
    assert isinstance(stored, dict) and "by_symbol" in stored
    assert stored["by_symbol"]["XAUUSD"]["market_status"] == "OPEN"


async def test_enforceable_requires_ea_link_or_fresh_report(client, bridge_token):
    assert market_status.enforceable() is False
    kill_switch._ea_seen_mono = None
    await client.post("/bridge/heartbeat",
                      json={"symbol": "XAUUSD", "market_status": "CLOSED"},
                      headers={"Authorization": f"Bearer {bridge_token}"})
    assert market_status.enforceable() is True
