"""Bridge endpoints: poll / result (idempotent) / tick / positions / reconciler."""
import json
import logging

import pytest

from app import config, db, ingest, kill_switch, market, telegram_bot
from app.db import DEFAULT_SETTINGS
from app.state_machine import fetchall, fetchone, transition


def _spec_sl_max(symbol: str) -> float:
    """sl_max_usd spec risk simbol dari default settings (sumber jarak SL
    darurat orphan per-simbol; QA_MP5 finding 1)."""
    return float(DEFAULT_SETTINGS["symbol_specs"][symbol]["sl_max_usd"])


def _auth(token):
    return {"Authorization": "Bearer " + token}


async def _make_order(status="SENT") -> dict:
    async with db.pool().connection() as conn:
        row = await fetchone(
            conn,
            """
            INSERT INTO orders (symbol, side, volume, sl, tp, status, sent_at)
            VALUES ('XAUUSD', 'BUY', 0.10, 1998, 2005, %s,
                    CASE WHEN %s = 'SENT' THEN now() ELSE NULL END)
            RETURNING *
            """,
            (status, status),
        )
        if status == "RECEIVED":
            await conn.execute(
                "INSERT INTO order_events (order_id, from_status, to_status) "
                "VALUES (%s, NULL, 'RECEIVED')", (row["id"],)
            )
        return row


async def test_poll_requires_token(client):
    resp = await client.get("/bridge/poll?timeout_s=0")
    assert resp.status_code == 401


async def test_poll_bad_token(client):
    resp = await client.get("/bridge/poll?timeout_s=0",
                            headers=_auth("wrong-token"))
    assert resp.status_code == 401


async def test_poll_returns_sent_command(client, bridge_token):
    order = await _make_order("SENT")
    headers = _auth(bridge_token)
    resp = await client.get("/bridge/poll?timeout_s=0", headers=headers)
    assert resp.status_code == 200
    cmd = resp.json()
    assert cmd["command_id"] == str(order["command_id"])
    assert cmd["side"] == "BUY"
    assert cmd["volume"] == 0.1

    # second poll: already delivered -> nothing
    resp2 = await client.get("/bridge/poll?timeout_s=0", headers=headers)
    assert resp2.status_code == 200
    assert resp2.json() is None


async def test_poll_longpoll_waits_then_returns(client, bridge_token):
    """Long-poll returns None when idle (timeout_s=1)."""
    headers = _auth(bridge_token)
    resp = await client.get("/bridge/poll?timeout_s=1", headers=headers)
    assert resp.status_code == 200
    assert resp.json() is None


async def test_poll_idle_tidak_menahan_lebih_dari_dua_detik(client, bridge_token):
    """Floor long-poll harus pendek: EA MQL5 memblokir OnTimer selama poll.

    Kalau floor >= 3 s, heartbeat 2 s dan flush tick 250 ms ikut tertahan dan
    tick terbaca basi oleh pre-flight (max_tick_age_s). timeout_s=0 di-clamp ke
    BRIDGE_POLL_MIN_S, jadi test ini mengunci batas atas floor tersebut.
    """
    import time as _t
    from app.bridge import BRIDGE_POLL_MIN_S
    assert BRIDGE_POLL_MIN_S <= 1.5
    headers = _auth(bridge_token)
    started = _t.monotonic()
    resp = await client.get("/bridge/poll?timeout_s=0", headers=headers)
    elapsed = _t.monotonic() - started
    assert resp.status_code == 200
    assert resp.json() is None
    assert elapsed < 2.0, f"poll idle menahan {elapsed:.2f}s"


async def test_result_fills_order(client, bridge_token):
    order = await _make_order("SENT")
    headers = _auth(bridge_token)
    resp = await client.post(
        "/bridge/result",
        json={"command_id": str(order["command_id"]), "status": "FILLED",
              "ticket": 123456, "price": 2000.15},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["duplicate"] is False

    async with db.pool().connection() as conn:
        row = await fetchone(conn, "SELECT * FROM orders WHERE id = %s", (order["id"],))
    assert row["status"] == "FILLED"
    assert row["ticket"] == 123456
    assert float(row["price_filled"]) == 2000.15


async def test_result_idempotent_by_command_id(client, bridge_token):
    order = await _make_order("SENT")
    headers = _auth(bridge_token)
    payload = {"command_id": str(order["command_id"]), "status": "FILLED",
               "ticket": 123456, "price": 2000.15}
    r1 = await client.post("/bridge/result", json=payload, headers=headers)
    r2 = await client.post("/bridge/result", json=payload, headers=headers)
    assert r1.status_code == 200 and r1.json()["duplicate"] is False
    assert r2.status_code == 200 and r2.json()["duplicate"] is True

    async with db.pool().connection() as conn:
        events = await conn.execute(
            "SELECT to_status FROM order_events WHERE order_id = %s ORDER BY id", (order["id"],)
        )
        rows = await events.fetchall()
    # exactly one FILLED event despite two identical posts
    assert [r["to_status"] for r in rows].count("FILLED") == 1


async def test_result_on_stuck_resolves(client, bridge_token):
    order = await _make_order("STUCK")
    headers = _auth(bridge_token)
    resp = await client.post(
        "/bridge/result",
        json={"command_id": str(order["command_id"]), "status": "FAILED", "reason": "late reject"},
        headers=headers,
    )
    assert resp.status_code == 200
    async with db.pool().connection() as conn:
        row = await fetchone(conn, "SELECT status FROM orders WHERE id = %s", (order["id"],))
    assert row["status"] == "FAILED"


async def test_result_unknown_command(client, bridge_token):
    resp = await client.post(
        "/bridge/result",
        json={"command_id": "00000000-0000-0000-0000-000000000000", "status": "FILLED"},
        headers=_auth(bridge_token),
    )
    assert resp.status_code == 404


async def test_result_bad_status(client, bridge_token):
    order = await _make_order("SENT")
    resp = await client.post(
        "/bridge/result",
        json={"command_id": str(order["command_id"]), "status": "MAYBE"},
        headers=_auth(bridge_token),
    )
    assert resp.status_code == 422


async def test_tick_updates_market_and_candles(client, bridge_token):
    headers = _auth(bridge_token)
    resp = await client.post(
        "/bridge/tick",
        json={"symbol": "XAUUSD", "bid": 2001.10, "ask": 2001.40,
              "candles": [{"symbol": "XAUUSD", "timeframe": "M1", "ts": "2026-11-21T10:00:00Z",
                           "open": 2000, "high": 2001.5, "low": 1999.5, "close": 2001.2,
                           "volume": 123}]},
        headers=headers,
    )
    assert resp.status_code == 200
    t = market.latest("XAUUSD")
    assert t["bid"] == 2001.10 and t["ask"] == 2001.40

    # candle ditulis background (order path tidak menunggu tulis tick):
    # flush pipeline ingest lalu cek DB.
    await ingest.get_pipeline().flush_now()
    async with db.pool().connection() as conn:
        row = await fetchone(conn, "SELECT * FROM candles WHERE symbol='XAUUSD' AND timeframe='M1'")
    assert row is not None and float(row["close"]) == 2001.2


async def test_tick_candle_only_accepted(client, bridge_token):
    """Seed history / refresh M1 kirim {symbol, ticks:[], candles:[...]} tanpa
    bid/ask — kontrak EA v5 SeedNextChunk. Harus 200 dan candle ter-upsert."""
    headers = _auth(bridge_token)
    resp = await client.post(
        "/bridge/tick",
        json={"symbol": "XAUUSD", "ticks": [],
              "candles": [{"symbol": "XAUUSD", "timeframe": "M1", "ts": "2026-11-21T10:00:00Z",
                           "open": 2000, "high": 2001.5, "low": 1999.5, "close": 2001.2,
                           "volume": 123}]},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["ticks"] == 0

    await ingest.get_pipeline().flush_now()
    async with db.pool().connection() as conn:
        row = await fetchone(conn, "SELECT * FROM candles WHERE symbol='XAUUSD' AND timeframe='M1'")
    assert row is not None and float(row["close"]) == 2001.2


async def test_tick_empty_payload_rejected(client, bridge_token):
    """Tanpa ticks, tanpa bid/ask, tanpa candles -> tetap 422."""
    resp = await client.post(
        "/bridge/tick",
        json={"symbol": "XAUUSD"},
        headers=_auth(bridge_token),
    )
    assert resp.status_code == 422


async def test_positions_sync_closes_missing(client, bridge_token):
    headers = _auth(bridge_token)
    # two open positions
    r1 = await client.post("/bridge/positions", json={"positions": [
        {"ticket": 1, "symbol": "XAUUSD", "side": "BUY", "volume": 0.1,
         "open_price": 2000.0, "profit": 5.0},
        {"ticket": 2, "symbol": "XAUUSD", "side": "SELL", "volume": 0.2,
         "open_price": 2001.0, "profit": -2.0},
    ]}, headers=headers)
    assert r1.status_code == 200
    assert r1.json()["open"] == 2

    # snapshot now only has ticket 1 -> ticket 2 must be CLOSED
    r2 = await client.post("/bridge/positions", json={"positions": [
        {"ticket": 1, "symbol": "XAUUSD", "side": "BUY", "volume": 0.1,
         "open_price": 2000.0, "profit": 7.5},
    ]}, headers=headers)
    assert r2.json()["closed"] == [2]

    pos = (await client.get("/positions")).json()
    by_ticket = {p["ticket"]: p for p in pos}
    assert by_ticket[1]["status"] == "OPEN"
    assert by_ticket[1]["profit"] == 7.5
    assert by_ticket[2]["status"] == "CLOSED"


# ── Reconciler (PRD 5.8): snapshot + orphan + FILLED_THEN_CLOSED/FAILED ──


async def _seed_open_position(ticket: int, order_status: str = "FILLED") -> dict:
    """Order (default FILLED) + posisi OPEN terhubung, seperti hasil fill normal."""
    async with db.pool().connection() as conn:
        row = await fetchone(
            conn,
            """
            INSERT INTO orders (symbol, side, volume, sl, tp, status, ticket, price_filled,
                                action, sent_at)
            VALUES ('XAUUSD', 'BUY', 0.10, 1998, 2005, %s, %s, 2000.0, 'OPEN', now())
            RETURNING *
            """,
            (order_status, ticket),
        )
        await conn.execute(
            """
            INSERT INTO positions (ticket, order_id, symbol, side, volume, open_price,
                                   sl, tp, profit, status)
            VALUES (%s, %s, 'XAUUSD', 'BUY', 0.10, 2000.0, 1998, 2005, 0, 'OPEN')
            """,
            (ticket, row["id"]),
        )
        await conn.execute(
            "INSERT INTO order_events (order_id, from_status, to_status) "
            "VALUES (%s, 'RECEIVED', %s)", (row["id"], order_status),
        )
        return row


async def _get_order(order_id) -> dict:
    async with db.pool().connection() as conn:
        return await fetchone(conn, "SELECT * FROM orders WHERE id = %s", (order_id,))


async def _get_position(ticket: int) -> dict:
    async with db.pool().connection() as conn:
        return await fetchone(conn, "SELECT * FROM positions WHERE ticket = %s", (ticket,))


async def _last_event(order_id) -> dict:
    async with db.pool().connection() as conn:
        return await fetchone(
            conn, "SELECT * FROM order_events WHERE order_id = %s ORDER BY id DESC LIMIT 1",
            (order_id,),
        )


def _out_deal(ticket: int, price: float = 2005.0, profit: float = 12.5) -> dict:
    return {"ticket": 9000 + ticket, "position_id": ticket, "symbol": "XAUUSD",
            "side": "SELL", "volume": 0.10, "price": price, "profit": profit,
            "entry": "OUT"}


async def test_reconciler_filled_then_closed_with_deal(client, bridge_token):
    """Posisi DB hilang dari broker + deal OUT di snapshot 24 jam -> FILLED_THEN_CLOSED."""
    order = await _seed_open_position(1001)
    resp = await client.post("/bridge/positions", headers=_auth(bridge_token), json={
        "positions": [],
        "deals": [_out_deal(1001)],
    })
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["closed"] == [1001]
    assert data["unexplained"] == []

    o = await _get_order(order["id"])
    assert o["status"] == "FILLED_THEN_CLOSED"
    p = await _get_position(1001)
    assert p["status"] == "CLOSED"
    assert float(p["close_price"]) == 2005.0
    ev = await _last_event(order["id"])
    assert ev["to_status"] == "FILLED_THEN_CLOSED"
    assert ev["payload"]["deal_ticket"] == 9000 + 1001
    # penutupan terjelaskan: kill-switch tidak boleh menyala
    state = await kill_switch.get_state()
    assert state["active"] is False


async def test_reconciler_unexplained_fails_order_and_halts(client, bridge_token, monkeypatch):
    """Posisi DB hilang tanpa deal penutup -> order FAILED + kill-switch + alert."""
    sent: list[str] = []

    async def fake_notify(text):
        sent.append(text)
        return True

    monkeypatch.setattr("app.bridge.notify_owner", fake_notify)
    order = await _seed_open_position(1002)
    resp = await client.post("/bridge/positions", headers=_auth(bridge_token),
                             json={"positions": [], "deals": []})
    assert resp.status_code == 200
    data = resp.json()
    assert data["unexplained"] == [1002]

    o = await _get_order(order["id"])
    assert o["status"] == "FAILED"
    ev = await _last_event(order["id"])
    assert ev["to_status"] == "FAILED"
    assert "tanpa deal penutup" in ev["payload"]["reason"]
    state = await kill_switch.get_state()
    assert state["active"] is True
    assert state["source"] == "auto:position_mismatch"
    assert sent and "REKONSILIASI" in sent[0]
    # bersihkan kill-switch untuk test berikutnya
    await kill_switch.release(checklist_ack=True, source="test")


async def test_reconciler_orphan_adopted_with_emergency_sl(client, bridge_token, monkeypatch):
    """Posisi broker tanpa order DB -> ORPHAN_ADOPTED + SL darurat + notifikasi."""
    sent: list[str] = []

    async def fake_notify(text):
        sent.append(text)
        return True

    monkeypatch.setattr("app.bridge.notify_owner", fake_notify)
    resp = await client.post("/bridge/positions", headers=_auth(bridge_token), json={
        "positions": [{"ticket": 2001, "symbol": "XAUUSD", "side": "BUY", "volume": 0.5,
                       "open_price": 2000.0, "profit": 1.0}],
        "deals": [],
    })
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert len(data["orphans"]) == 1
    oid = data["orphans"][0]

    o = await _get_order(oid)
    assert o["status"] == "ORPHAN_ADOPTED"
    assert o["strategy"] == "reconciler" and o["action"] == "OPEN"
    assert o["ticket"] == 2001 and o["side"] == "BUY" and float(o["volume"]) == 0.5
    p = await _get_position(2001)
    assert str(p["order_id"]) == oid
    # SL darurat: BUY -> open - sl_max spec XAUUSD (per-simbol, QA_MP5 #1)
    assert float(p["sl"]) == 2000.0 - _spec_sl_max("XAUUSD")
    async with db.pool().connection() as conn:
        cmd = await fetchone(
            conn, "SELECT * FROM bridge_commands WHERE order_id = %s", (oid,)
        )
    assert cmd is not None and cmd["action"] == "MODIFY_SL"
    assert cmd["status"] == "QUEUED"
    assert float(cmd["payload"]["sl"]) == 2000.0 - _spec_sl_max("XAUUSD")
    ev = await _last_event(oid)
    assert ev["to_status"] == "ORPHAN_ADOPTED"
    assert sent and "ORPHAN ADOPTED" in sent[0]


async def test_reconciler_orphan_btcusd_emergency_sl_per_symbol(
        client, bridge_token):
    """QA_MP5 finding 1: SL darurat orphan BTCUSD dihitung dari spec BTCUSD,
    bukan konstanta global XAUUSD (15.0 @ 61269 = 0.025% harga)."""
    resp = await client.post("/bridge/positions", headers=_auth(bridge_token), json={
        "positions": [
            {"ticket": 2011, "symbol": "BTCUSD", "side": "BUY", "volume": 0.01,
             "open_price": 61269.0, "profit": 1.0},
            {"ticket": 2012, "symbol": "BTCUSD", "side": "SELL", "volume": 0.01,
             "open_price": 61269.0, "profit": -1.0},
        ],
        "deals": [],
    })
    assert resp.status_code, resp.text
    orphans = resp.json()["orphans"]
    assert len(orphans) == 2
    spec = DEFAULT_SETTINGS["symbol_specs"]["BTCUSD"]
    sl_min = float(spec["sl_min_usd"])
    sl_max = float(spec["sl_max_usd"])
    # BUY: SL di bawah harga; SELL: SL di atas harga
    p_buy = await _get_position(2011)
    p_sell = await _get_position(2012)
    assert float(p_buy["sl"]) < 61269.0 < float(p_sell["sl"])
    for p in (p_buy, p_sell):
        dist = abs(61269.0 - float(p["sl"]))
        # dalam rentang spec BTCUSD, dan bukan lagi jarak global 15.0
        assert sl_min <= dist <= sl_max
        assert dist == sl_max
        assert dist > config.EMERGENCY_SL_DISTANCE
    # MODIFY_SL terqueue dengan SL per-simbol + event mencatat sumber jarak
    async with db.pool().connection() as conn:
        for oid in orphans:
            cmd = await fetchone(
                conn, "SELECT * FROM bridge_commands WHERE order_id = %s", (oid,))
            assert cmd is not None and cmd["action"] == "MODIFY_SL"
    ev = await _last_event(orphans[0])
    assert ev["payload"]["event"] == "emergency_sl_queued"
    assert ev["payload"]["distance_source"] == "spec_sl_max"
    assert float(ev["payload"]["distance"]) == sl_max


async def test_reconciler_orphan_emergency_sl_fallback_price_pct(
        client, bridge_token):
    """Simbol tanpa spec risk: SL darurat price-relative (persen harga open),
    bukan jarak absolut global yang satuan harganya beda per simbol."""
    resp = await client.post("/bridge/positions", headers=_auth(bridge_token), json={
        "positions": [{"ticket": 2013, "symbol": "EURUSD", "side": "SELL",
                       "volume": 0.10, "open_price": 1.0850, "profit": 0}],
        "deals": [],
    })
    assert resp.status_code, resp.text
    oid = resp.json()["orphans"][0]
    p = await _get_position(2013)
    dist = float(p["sl"]) - 1.0850  # SELL -> SL di atas harga
    assert dist == pytest.approx(1.0850 * config.EMERGENCY_SL_FALLBACK_PCT)
    ev = await _last_event(oid)
    assert ev["payload"]["distance_source"] == "fallback_price_pct"


def test_emergency_sl_distance_branches():
    """Helper jarak SL darurat: spec -> fallback persen -> legacy absolut."""
    from app.bridge import _emergency_sl_distance

    settings = dict(DEFAULT_SETTINGS)
    # spec BTCUSD: sl_max 1000.0 (bukan 15.0 global)
    assert _emergency_sl_distance("BTCUSD", 61269.0, settings) == (
        1000.0, "spec_sl_max")
    # simbol tanpa spec: persen harga
    dist, src = _emergency_sl_distance("EURUSD", 1.0850, settings)
    assert (dist, src) == (
        pytest.approx(1.0850 * config.EMERGENCY_SL_FALLBACK_PCT),
        "fallback_price_pct")
    # tanpa spec + tanpa harga: legacy absolut satu-satunya pilihan
    assert _emergency_sl_distance("EURUSD", None, settings) == (
        config.EMERGENCY_SL_DISTANCE, "legacy_abs")


async def test_reconciler_orphan_with_sl_gets_no_command(client, bridge_token):
    """Orphan yang sudah punya SL: tanpa MODIFY_SL, SL snapshot dipertahankan."""
    resp = await client.post("/bridge/positions", headers=_auth(bridge_token), json={
        "positions": [{"ticket": 2002, "symbol": "XAUUSD", "side": "SELL", "volume": 0.2,
                       "open_price": 2000.0, "sl": 1990.0, "profit": 0}],
        "deals": [],
    })
    assert resp.status_code == 200
    oid = resp.json()["orphans"][0]
    async with db.pool().connection() as conn:
        cmd = await fetchone(
            conn, "SELECT * FROM bridge_commands WHERE order_id = %s", (oid,)
        )
    assert cmd is None
    p = await _get_position(2002)
    assert float(p["sl"]) == 1990.0


async def test_reconciler_orphan_closed_with_deal(client, bridge_token):
    """Posisi orphan (ORPHAN_ADOPTED) lalu hilang + deal OUT -> ORPHAN_CLOSED."""
    resp = await client.post("/bridge/positions", headers=_auth(bridge_token), json={
        "positions": [{"ticket": 2003, "symbol": "XAUUSD", "side": "BUY", "volume": 0.1,
                       "open_price": 2000.0, "sl": 1985.0, "profit": 0}],
        "deals": [],
    })
    oid = resp.json()["orphans"][0]
    resp2 = await client.post("/bridge/positions", headers=_auth(bridge_token), json={
        "positions": [],
        "deals": [_out_deal(2003, price=2008.0, profit=8.0)],
    })
    assert resp2.status_code == 200
    o = await _get_order(oid)
    assert o["status"] == "ORPHAN_CLOSED"
    p = await _get_position(2003)
    assert p["status"] == "CLOSED"
    ev = await _last_event(oid)
    assert ev["to_status"] == "ORPHAN_CLOSED"


async def test_reconciler_cycle_with_alerts_guard_sends_no_telegram(
        client, bridge_token, monkeypatch, caplog):
    """DoD insiden 22 Nov 2026: 1 siklus reconciler dengan TELEGRAM_ALERTS_OFF=1.

    Reconciler tetap jalan normal (orphan diadopsi, SL darurat dibuat), tapi
    notify_owner asli TIDAK mengirim apa pun: 0 request ke api.telegram.org.
    """
    calls: list[dict] = []

    async def record_tg(token, method, **params):
        calls.append({"method": method, "params": params})
        return {"ok": True, "result": []}

    monkeypatch.setattr(telegram_bot, "tg_api", record_tg)
    # guard sudah diset conftest untuk seluruh session; di-set eksplisit agar
    # test ini tetap sah kalau dijalankan sendiri
    monkeypatch.setenv("TELEGRAM_ALERTS_OFF", "1")

    with caplog.at_level(logging.INFO, logger="fund2.telegram"):
        resp = await client.post("/bridge/positions", headers=_auth(bridge_token), json={
            "positions": [{"ticket": 2004, "symbol": "XAUUSD", "side": "BUY",
                           "volume": 0.1, "open_price": 2000.0, "profit": 0}],
            "deals": [],
        })
    assert resp.status_code == 200, resp.text

    # reconciler tetap bekerja normal
    data = resp.json()
    assert len(data["orphans"]) == 1
    oid = data["orphans"][0]
    o = await _get_order(oid)
    assert o["status"] == "ORPHAN_ADOPTED"
    p = await _get_position(2004)
    assert float(p["sl"]) == 2000.0 - _spec_sl_max("XAUUSD")

    # 0 pesan Telegram keluar + supresi tercatat di log
    assert calls == []
    assert any("TELEGRAM_ALERTS_OFF" in r.getMessage() for r in caplog.records)


async def test_modify_sl_command_lifecycle(client, bridge_token):
    """bridge_commands MODIFY_SL dilayani poll dan diselesaikan /result (idempotent)."""
    async with db.pool().connection() as conn:
        cmd = await fetchone(
            conn,
            "INSERT INTO bridge_commands (action, payload) VALUES ('MODIFY_SL', %s) "
            "RETURNING id",
            (json.dumps({"ticket": 2001, "sl": 1985.0}),),
        )
    cmd_id = str(cmd["id"])
    resp = await client.get("/bridge/poll?timeout_s=0", headers=_auth(bridge_token))
    body = resp.json()
    assert body["action"] == "MODIFY_SL"
    assert body["command_id"] == cmd_id
    assert body["ticket"] == "2001" and float(body["sl"]) == 1985.0
    # poll lagi: sudah delivered
    resp2 = await client.get("/bridge/poll?timeout_s=0", headers=_auth(bridge_token))
    assert resp2.json() is None
    # EA lapor sukses
    resp3 = await client.post("/bridge/result", headers=_auth(bridge_token),
                              json={"command_id": cmd_id, "status": "FILLED"})
    assert resp3.status_code == 200
    assert resp3.json()["status"] == "DONE"
    # replay idempotent
    resp4 = await client.post("/bridge/result", headers=_auth(bridge_token),
                              json={"command_id": cmd_id, "status": "FILLED"})
    assert resp4.json()["duplicate"] is True
    async with db.pool().connection() as conn:
        row = await fetchone(
            conn, "SELECT * FROM bridge_commands WHERE id = %s", (cmd_id,)
        )
    assert row["status"] == "DONE"


async def test_dod_disconnect_10x_reconciliation(client, bridge_token, monkeypatch):
    """DoD P1b: uji disconnect 10x -> rekonsiliasi benar 10/10, semua di order_events.

    Tiap siklus: posisi terbuka + snapshot reconnect. Skenario berputar:
    masih terbuka / tertutup dengan deal / hilang tanpa deal / orphan baru.
    """
    monkeypatch.setattr("app.bridge.notify_owner", _noop_notify)
    correct = 0
    for cycle in range(1, 11):
        ticket = 3000 + cycle
        scenario = cycle % 4
        # slate bersih antar siklus: posisi siklus sebelumnya dianggap sudah
        # selesai direkonsiliasi (history order_events tetap utuh).
        async with db.pool().connection() as conn:
            await conn.execute("UPDATE positions SET status = 'CLOSED' WHERE status = 'OPEN'")
        if scenario == 1:
            # disconnect: tidak ada snapshot. reconnect: posisi masih ada.
            order = await _seed_open_position(ticket)
            resp = await client.post("/bridge/positions", headers=_auth(bridge_token), json={
                "positions": [{"ticket": ticket, "symbol": "XAUUSD", "side": "BUY",
                               "volume": 0.10, "open_price": 2000.0, "sl": 1998.0,
                               "profit": 0}],
                "deals": [],
            })
            data = resp.json()
            ok = (data["closed"] == [] and data["orphans"] == []
                  and data["unexplained"] == [])
            o = await _get_order(order["id"])
            ok = ok and o["status"] == "FILLED"
            p = await _get_position(ticket)
            ok = ok and p["status"] == "OPEN"
            ev = await _last_event(order["id"])
            ok = ok and ev is not None
        elif scenario == 2:
            # disconnect: SL tersentuh di broker -> deal OUT muncul di snapshot.
            order = await _seed_open_position(ticket)
            resp = await client.post("/bridge/positions", headers=_auth(bridge_token), json={
                "positions": [],
                "deals": [_out_deal(ticket, price=1998.0, profit=-2.0)],
            })
            data = resp.json()
            ok = data["closed"] == [ticket] and data["unexplained"] == []
            o = await _get_order(order["id"])
            ok = ok and o["status"] == "FILLED_THEN_CLOSED"
            ev = await _last_event(order["id"])
            ok = ok and ev["to_status"] == "FILLED_THEN_CLOSED"
        elif scenario == 3:
            # disconnect: posisi hilang tanpa jejak -> FAILED + kill-switch.
            order = await _seed_open_position(ticket)
            resp = await client.post("/bridge/positions", headers=_auth(bridge_token),
                                     json={"positions": [], "deals": []})
            data = resp.json()
            ok = data["unexplained"] == [ticket]
            o = await _get_order(order["id"])
            ok = ok and o["status"] == "FAILED"
            state = await kill_switch.get_state()
            ok = ok and state["active"] is True
            ev = await _last_event(order["id"])
            ok = ok and ev["to_status"] == "FAILED"
            await kill_switch.release(checklist_ack=True, source="test")
        else:
            # reconnect: posisi di broker tidak dikenal DB -> ORPHAN_ADOPTED + SL.
            resp = await client.post("/bridge/positions", headers=_auth(bridge_token), json={
                "positions": [{"ticket": ticket, "symbol": "XAUUSD", "side": "BUY",
                               "volume": 0.10, "open_price": 2000.0, "profit": 0}],
                "deals": [],
            })
            data = resp.json()
            ok = len(data["orphans"]) == 1
            oid = data["orphans"][0] if ok else None
            o = await _get_order(oid) if ok else None
            ok = ok and o["status"] == "ORPHAN_ADOPTED"
            p = await _get_position(ticket)
            ok = ok and str(p["order_id"]) == oid and float(p["sl"]) == 1985.0
            ev = await _last_event(oid) if ok else None
            ok = ok and ev is not None and ev["to_status"] == "ORPHAN_ADOPTED"
        assert ok, f"siklus {cycle} (scenario {scenario}): rekonsiliasi salah"
        correct += 1
    assert correct == 10, f"DoD: rekonsiliasi benar {correct}/10"


async def _noop_notify(text: str) -> bool:
    return True


# ── Race T4: result CLOSE langsung mentransisikan order OPEN induk ──


async def _insert_action_order(ticket: int, action: str, status: str = "SENT") -> dict:
    """Order dengan action & ticket (CLOSE buatan flatten, atau OPEN hasil fill)."""
    async with db.pool().connection() as conn:
        row = await fetchone(
            conn,
            """
            INSERT INTO orders (symbol, side, volume, status, ticket, price_filled,
                                action, sent_at)
            VALUES ('XAUUSD',
                    CASE WHEN %s = 'CLOSE' THEN 'SELL' ELSE 'BUY' END,
                    0.10, %s, %s, 2000.0, %s,
                    CASE WHEN %s = 'SENT' THEN now() ELSE NULL END)
            RETURNING *
            """,
            (action, status, ticket, action, status),
        )
        await conn.execute(
            "INSERT INTO order_events (order_id, from_status, to_status) "
            "VALUES (%s, 'RECEIVED', %s)",
            (row["id"], status),
        )
        return row


async def _count_events(order_id, to_status: str) -> int:
    async with db.pool().connection() as conn:
        row = await fetchone(
            conn,
            "SELECT COUNT(*) AS n FROM order_events WHERE order_id = %s AND to_status = %s",
            (order_id, to_status),
        )
    return row["n"]


async def test_result_close_transitions_owner_to_filled_then_closed(client, bridge_token):
    """Race T4: CLOSE FILLED via /result langsung menutup order OPEN induk
    (FILLED -> FILLED_THEN_CLOSED) tanpa menunggu snapshot reconciler."""
    owner = await _seed_open_position(4001)
    close = await _insert_action_order(4001, "CLOSE")
    resp = await client.post(
        "/bridge/result",
        json={"command_id": str(close["command_id"]), "status": "FILLED",
              "ticket": 4001, "price": 2005.5, "profit": 12.5},
        headers=_auth(bridge_token),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["duplicate"] is False

    assert (await _get_order(close["id"]))["status"] == "FILLED"
    o = await _get_order(owner["id"])
    assert o["status"] == "FILLED_THEN_CLOSED"
    p = await _get_position(4001)
    assert p["status"] == "CLOSED"
    assert float(p["close_price"]) == 2005.5
    ev = await _last_event(owner["id"])
    assert ev["from_status"] == "FILLED"
    assert ev["to_status"] == "FILLED_THEN_CLOSED"
    assert ev["payload"]["source"] == "bridge_result"
    assert ev["payload"]["close_order_id"] == str(close["id"])
    assert float(ev["payload"]["close_price"]) == 2005.5
    assert float(ev["payload"]["profit"]) == 12.5
    # penutupan terjelaskan: kill-switch tetap mati
    state = await kill_switch.get_state()
    assert state["active"] is False


async def test_result_close_owner_stuck_goes_filled_then_closed(client, bridge_token):
    """Order induk STUCK (result fill hilang) ikut ditutup saat CLOSE FILLED."""
    owner = await _seed_open_position(4002, order_status="STUCK")
    close = await _insert_action_order(4002, "CLOSE")
    resp = await client.post(
        "/bridge/result",
        json={"command_id": str(close["command_id"]), "status": "FILLED",
              "ticket": 4002, "price": 2004.0, "profit": 4.0},
        headers=_auth(bridge_token),
    )
    assert resp.status_code == 200, resp.text
    assert (await _get_order(owner["id"]))["status"] == "FILLED_THEN_CLOSED"
    assert (await _get_position(4002))["status"] == "CLOSED"


async def test_result_close_orphan_owner_goes_orphan_closed(client, bridge_token):
    """Posisi ORPHAN_ADOPTED ditutup CLOSE FILLED -> ORPHAN_CLOSED."""
    r = await client.post("/bridge/positions", headers=_auth(bridge_token), json={
        "positions": [{"ticket": 4003, "symbol": "XAUUSD", "side": "BUY",
                       "volume": 0.1, "open_price": 2000.0, "sl": 1985.0, "profit": 0}],
        "deals": [],
    })
    orphan_id = r.json()["orphans"][0]
    close = await _insert_action_order(4003, "CLOSE")
    resp = await client.post(
        "/bridge/result",
        json={"command_id": str(close["command_id"]), "status": "FILLED",
              "ticket": 4003, "price": 2004.0, "profit": 4.0},
        headers=_auth(bridge_token),
    )
    assert resp.status_code == 200, resp.text
    o = await _get_order(orphan_id)
    assert o["status"] == "ORPHAN_CLOSED"
    assert (await _get_position(4003))["status"] == "CLOSED"
    ev = await _last_event(orphan_id)
    assert ev["to_status"] == "ORPHAN_CLOSED"
    assert ev["payload"]["source"] == "bridge_result"


async def test_result_close_transitions_all_linked_owners(client, bridge_token):
    """Kasus live 22 Nov (ticket 503129381): posisi ter-link ke order orphan
    (diadopsi sebelum order manual fill), sementara order manual FILLED
    memakai ticket yang sama. Keduanya harus ditutup."""
    # 1. posisi muncul di snapshot tanpa owner -> ORPHAN_ADOPTED
    r = await client.post("/bridge/positions", headers=_auth(bridge_token), json={
        "positions": [{"ticket": 4008, "symbol": "XAUUSD", "side": "BUY",
                       "volume": 0.1, "open_price": 2000.0, "sl": 1985.0, "profit": 0}],
        "deals": [],
    })
    orphan_id = r.json()["orphans"][0]
    # 2. order manual terisi belakangan dengan ticket yang sama
    manual = await _insert_action_order(4008, "OPEN", "FILLED")
    # 3. CLOSE untuk posisi itu FILLED
    close = await _insert_action_order(4008, "CLOSE")
    resp = await client.post(
        "/bridge/result",
        json={"command_id": str(close["command_id"]), "status": "FILLED",
              "ticket": 4008, "price": 2004.0, "profit": 4.0},
        headers=_auth(bridge_token),
    )
    assert resp.status_code == 200, resp.text
    assert (await _get_order(manual["id"]))["status"] == "FILLED_THEN_CLOSED"
    assert (await _get_order(orphan_id))["status"] == "ORPHAN_CLOSED"
    assert (await _get_position(4008))["status"] == "CLOSED"


async def test_result_close_after_reconciler_is_noop(client, bridge_token):
    """Reconciler menang race: result CLOSE telat tidak crash dan tidak
    menduplikasi transisi."""
    owner = await _seed_open_position(4004)
    r = await client.post("/bridge/positions", headers=_auth(bridge_token),
                          json={"positions": [], "deals": [_out_deal(4004)]})
    assert r.status_code == 200
    assert (await _get_order(owner["id"]))["status"] == "FILLED_THEN_CLOSED"

    close = await _insert_action_order(4004, "CLOSE")
    resp = await client.post(
        "/bridge/result",
        json={"command_id": str(close["command_id"]), "status": "FILLED",
              "ticket": 4004, "price": 2005.0, "profit": 5.0},
        headers=_auth(bridge_token),
    )
    assert resp.status_code == 200, resp.text
    assert (await _get_order(owner["id"]))["status"] == "FILLED_THEN_CLOSED"
    assert await _count_events(owner["id"], "FILLED_THEN_CLOSED") == 1


async def test_result_close_without_owner_still_closes_position(client, bridge_token):
    """CLOSE FILLED tanpa order induk: posisi tetap ditutup, tidak 500."""
    async with db.pool().connection() as conn:
        await conn.execute(
            """
            INSERT INTO positions (ticket, symbol, side, volume, open_price, status)
            VALUES (4005, 'XAUUSD', 'BUY', 0.10, 2000.0, 'OPEN')
            """
        )
    close = await _insert_action_order(4005, "CLOSE")
    resp = await client.post(
        "/bridge/result",
        json={"command_id": str(close["command_id"]), "status": "FILLED",
              "ticket": 4005, "price": 2003.0},
        headers=_auth(bridge_token),
    )
    assert resp.status_code == 200, resp.text
    assert (await _get_position(4005))["status"] == "CLOSED"


async def test_result_close_idempotent_no_double_transition(client, bridge_token):
    """Replay result CLOSE yang sama tidak menduplikasi transisi induk."""
    owner = await _seed_open_position(4006)
    close = await _insert_action_order(4006, "CLOSE")
    payload = {"command_id": str(close["command_id"]), "status": "FILLED",
               "ticket": 4006, "price": 2004.0, "profit": 4.0}
    r1 = await client.post("/bridge/result", json=payload, headers=_auth(bridge_token))
    r2 = await client.post("/bridge/result", json=payload, headers=_auth(bridge_token))
    assert r1.status_code == 200 and r1.json()["duplicate"] is False
    assert r2.status_code == 200 and r2.json()["duplicate"] is True
    assert (await _get_order(owner["id"]))["status"] == "FILLED_THEN_CLOSED"
    assert await _count_events(owner["id"], "FILLED_THEN_CLOSED") == 1


async def test_result_close_failed_leaves_owner_and_position(client, bridge_token):
    """CLOSE FAILED: order induk dan posisi tidak disentuh."""
    owner = await _seed_open_position(4007)
    close = await _insert_action_order(4007, "CLOSE")
    resp = await client.post(
        "/bridge/result",
        json={"command_id": str(close["command_id"]), "status": "FAILED",
              "reason": "requote"},
        headers=_auth(bridge_token),
    )
    assert resp.status_code == 200, resp.text
    assert (await _get_order(close["id"]))["status"] == "FAILED"
    assert (await _get_order(owner["id"]))["status"] == "FILLED"
    assert (await _get_position(4007))["status"] == "OPEN"


# ── Regresi profit close 0.0 (t_6c30e62b): EA BuildResultJson hardcode 0 ──


async def _seed_open_position_custom(ticket: int, side: str, volume: float,
                                     entry_price: float | None,
                                     symbol: str = "XAUUSD") -> dict:
    """Order OPEN FILLED + posisi terhubung dgn side/volume/entry custom."""
    async with db.pool().connection() as conn:
        row = await fetchone(
            conn,
            """
            INSERT INTO orders (symbol, side, volume, status, ticket, price_filled,
                                action, sent_at)
            VALUES (%s, %s, %s, 'FILLED', %s, %s, 'OPEN', now())
            RETURNING *
            """,
            (symbol, side, volume, ticket, entry_price),
        )
        await conn.execute(
            """
            INSERT INTO positions (ticket, order_id, symbol, side, volume, open_price,
                                   status)
            VALUES (%s, %s, %s, %s, %s, %s, 'OPEN')
            """,
            (ticket, row["id"], symbol, side, volume, entry_price),
        )
        await conn.execute(
            "INSERT INTO order_events (order_id, from_status, to_status) "
            "VALUES (%s, 'RECEIVED', 'FILLED')", (row["id"],)
        )
        return row


async def test_result_close_profit_zero_computed_sell(client, bridge_token):
    """CLOSE SELL dgn profit 0.0 (hardcode EA) dihitung ulang dari harga.

    Kasus live 25 Nov: SELL 0.05 @3630.09 -> close 3633.20 harus tercatat
    -15.55, bukan 0.0 (rumus = DEAL_PROFIT broker, terverifikasi).
    """
    owner = await _seed_open_position_custom(4101, "SELL", 0.05, 3630.09)
    close = await _insert_action_order(4101, "CLOSE")
    resp = await client.post(
        "/bridge/result",
        json={"command_id": str(close["command_id"]), "status": "FILLED",
              "ticket": 4101, "price": 3633.20, "profit": 0.0},
        headers=_auth(bridge_token),
    )
    assert resp.status_code == 200, resp.text
    ev = await _last_event(owner["id"])
    assert ev["to_status"] == "FILLED_THEN_CLOSED"
    assert ev["payload"]["source"] == "bridge_result"
    assert float(ev["payload"]["profit"]) == -15.55
    assert ev["payload"]["profit_estimated"] is True
    # payload order CLOSE juga tidak mencatat 0.0 hardcode EA
    ev_close = await _last_event(close["id"])
    assert ev_close["to_status"] == "FILLED"
    assert float(ev_close["payload"]["profit"]) == -15.55
    assert ev_close["payload"]["profit_estimated"] is True


async def test_result_close_profit_zero_computed_buy(client, bridge_token):
    """CLOSE BUY dgn profit 0.0 dihitung ulang: BUY 0.10 @2000.0 -> close
    2003.0 = +30.00 (rumus = DEAL_PROFIT broker, terverifikasi)."""
    owner = await _seed_open_position_custom(4102, "BUY", 0.10, 2000.0)
    close = await _insert_action_order(4102, "CLOSE")
    resp = await client.post(
        "/bridge/result",
        json={"command_id": str(close["command_id"]), "status": "FILLED",
              "ticket": 4102, "price": 2003.0, "profit": 0.0},
        headers=_auth(bridge_token),
    )
    assert resp.status_code == 200, resp.text
    ev = await _last_event(owner["id"])
    assert ev["to_status"] == "FILLED_THEN_CLOSED"
    assert float(ev["payload"]["profit"]) == 30.0
    assert ev["payload"]["profit_estimated"] is True


async def test_result_close_profit_zero_computed_btcusd(client, bridge_token):
    """contract_size per simbol dari settings.symbol_specs (BTCUSD=1)."""
    owner = await _seed_open_position_custom(4103, "SELL", 0.20, 61269.0,
                                             symbol="BTCUSD")
    close = await _insert_action_order(4103, "CLOSE")
    resp = await client.post(
        "/bridge/result",
        json={"command_id": str(close["command_id"]), "status": "FILLED",
              "ticket": 4103, "price": 61069.0, "profit": 0.0},
        headers=_auth(bridge_token),
    )
    assert resp.status_code == 200, resp.text
    ev = await _last_event(owner["id"])
    assert float(ev["payload"]["profit"]) == 40.0  # (-200) * 1.0 * 0.20 * -1
    assert ev["payload"]["profit_estimated"] is True


async def test_result_close_profit_nonzero_passthrough(client, bridge_token):
    """profit non-nol dari EA diteruskan apa adanya, tanpa marker."""
    owner = await _seed_open_position_custom(4104, "BUY", 0.10, 2000.0)
    close = await _insert_action_order(4104, "CLOSE")
    resp = await client.post(
        "/bridge/result",
        json={"command_id": str(close["command_id"]), "status": "FILLED",
              "ticket": 4104, "price": 2005.0, "profit": 12.5},
        headers=_auth(bridge_token),
    )
    assert resp.status_code == 200, resp.text
    ev = await _last_event(owner["id"])
    assert float(ev["payload"]["profit"]) == 12.5
    assert "profit_estimated" not in ev["payload"]
    ev_close = await _last_event(close["id"])
    assert float(ev_close["payload"]["profit"]) == 12.5
    assert "profit_estimated" not in ev_close["payload"]


async def test_result_close_profit_zero_entry_missing_marks_estimated(
        client, bridge_token):
    """Entry (price_filled induk) atau close price hilang -> profit 0 +
    marker profit_estimated, bukan angka karangan."""
    # entry hilang
    owner = await _seed_open_position_custom(4105, "BUY", 0.10, None)
    close = await _insert_action_order(4105, "CLOSE")
    resp = await client.post(
        "/bridge/result",
        json={"command_id": str(close["command_id"]), "status": "FILLED",
              "ticket": 4105, "price": 2003.0, "profit": 0.0},
        headers=_auth(bridge_token),
    )
    assert resp.status_code == 200, resp.text
    ev = await _last_event(owner["id"])
    assert ev["to_status"] == "FILLED_THEN_CLOSED"
    assert float(ev["payload"]["profit"]) == 0.0
    assert ev["payload"]["profit_estimated"] is True
    # close price hilang
    owner2 = await _seed_open_position_custom(4106, "BUY", 0.10, 2000.0)
    close2 = await _insert_action_order(4106, "CLOSE")
    resp2 = await client.post(
        "/bridge/result",
        json={"command_id": str(close2["command_id"]), "status": "FILLED",
              "ticket": 4106, "profit": 0.0},
        headers=_auth(bridge_token),
    )
    assert resp2.status_code == 200, resp2.text
    ev2 = await _last_event(owner2["id"])
    assert float(ev2["payload"]["profit"]) == 0.0
    assert ev2["payload"]["profit_estimated"] is True


# ── Regresi: order_id terpotong dari comment broker (45858f6, t_110597bb) ──


async def test_positions_truncated_order_id_28char_relinks_via_ticket(
        client, bridge_token):
    """order_id 28 char (UUID terpotong comment MT5) tidak boleh 500.

    Nilai dibuang validator, link posisi dipulihkan via fallback ticket,
    dan nilai mentah disimpan di raw untuk recon.
    """
    order = await _seed_open_position(3001)
    truncated = str(order["id"])[:28]
    assert len(truncated) == 28
    resp = await client.post("/bridge/positions", headers=_auth(bridge_token), json={
        "positions": [{"ticket": 3001, "order_id": truncated, "symbol": "XAUUSD",
                       "side": "BUY", "volume": 0.10, "open_price": 2000.0,
                       "profit": 1.0}],
        "deals": [],
    })
    assert resp.status_code == 200, resp.text
    assert resp.json()["orphans"] == []
    p = await _get_position(3001)
    assert str(p["order_id"]) == str(order["id"])  # link dipulihkan via ticket
    assert p["raw"]["order_id_raw_dropped"] == truncated  # tersimpan untuk recon


async def test_positions_truncated_order_id_31char_boundary_orphan(
        client, bridge_token, monkeypatch):
    """Boundary 31 char (batas comment MT5) + ticket tak dikenal -> ORPHAN_ADOPTED, bukan 500."""
    sent: list[str] = []

    async def fake_notify(text):
        sent.append(text)
        return True

    monkeypatch.setattr("app.bridge.notify_owner", fake_notify)
    full_uuid = "9be9bea7-f735-485d-81c8-abcdefabcdef"
    truncated = full_uuid[:31]
    assert len(truncated) == 31
    resp = await client.post("/bridge/positions", headers=_auth(bridge_token), json={
        "positions": [{"ticket": 3002, "order_id": truncated, "symbol": "XAUUSD",
                       "side": "SELL", "volume": 0.20, "open_price": 2001.0,
                       "profit": -2.0}],
        "deals": [],
    })
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert len(data["orphans"]) == 1
    o = await _get_order(data["orphans"][0])
    assert o["status"] == "ORPHAN_ADOPTED"
    p = await _get_position(3002)
    assert p["raw"]["order_id_raw_dropped"] == truncated


async def test_positions_valid_order_id_still_links(client, bridge_token):
    """Regresi 45858f6: order_id UUID valid tetap ter-link seperti biasa."""
    order = await _seed_open_position(3003)
    resp = await client.post("/bridge/positions", headers=_auth(bridge_token), json={
        "positions": [{"ticket": 3003, "order_id": str(order["id"]), "symbol": "XAUUSD",
                       "side": "BUY", "volume": 0.10, "open_price": 2000.0,
                       "profit": 1.0}],
        "deals": [],
    })
    assert resp.status_code == 200, resp.text
    assert resp.json()["orphans"] == []
    p = await _get_position(3003)
    assert str(p["order_id"]) == str(order["id"])
    assert p["raw"].get("order_id_raw_dropped") is None
