"""Kill-switch: mode, persistensi, auto-trigger, flatten, mismatch (PRD v2.1 §5.7, v2.2 §16)."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from app import db, kill_switch, market
from app.kill_switch import RECOVERY_CHECKLIST, SLIPPAGE_WARNING


async def _insert_position(ticket, *, side="BUY", volume=0.10, profit=0.0, status="OPEN"):
    async with db.pool().connection() as conn:
        await conn.execute(
            """
            INSERT INTO positions (ticket, symbol, side, volume, open_price, profit, status)
            VALUES (%s, 'XAUUSD', %s, %s, 2000.0, %s, %s)
            """,
            (ticket, side, volume, profit, status),
        )


async def _insert_closed_position(ticket, profit, *, days_ago=0):
    async with db.pool().connection() as conn:
        await conn.execute(
            """
            INSERT INTO positions (ticket, symbol, side, volume, open_price, profit, status,
                                   close_time)
            VALUES (%s, 'XAUUSD', 'BUY', 0.10, 2000.0, %s, 'CLOSED',
                    now() - (%s * interval '1 day'))
            """,
            (ticket, profit, days_ago),
        )


async def _insert_order(status="FAILED", *, strategy="manual", created_seconds_ago=0,
                        fail_risk_rejected=False):
    async with db.pool().connection() as conn:
        row = await conn.execute(
            """
            INSERT INTO orders (symbol, side, volume, sl, tp, strategy, status,
                                created_at, fail_reason)
            VALUES ('XAUUSD', 'BUY', 0.10, 1998, 2005, %s, %s,
                    now() - (%s * interval '1 second'), 'test')
            RETURNING id
            """,
            (strategy, status, created_seconds_ago),
        )
        created = await row.fetchone()
        payload = {"risk": "rejected", "reasons": ["x"]} if fail_risk_rejected else \
            {"source": "bridge", "reason": "retcode"}
        await conn.execute(
            "INSERT INTO order_events (order_id, from_status, to_status, payload) "
            "VALUES (%s, 'SENT', 'FAILED', %s)",
            (created["id"], json.dumps(payload)),
        )
        return created["id"]


async def _events(action=None):
    async with db.pool().connection() as conn:
        if action:
            rows = await conn.execute(
                "SELECT * FROM kill_switch_events WHERE action = %s ORDER BY id", (action,))
        else:
            rows = await conn.execute("SELECT * FROM kill_switch_events ORDER BY id")
        return await rows.fetchall()


# ---------------------------------------------------------------- state & mode API

@pytest.mark.asyncio
async def test_activate_stop_new_orders_and_release(client_2fa):
    r = await client_2fa.post("/kill-switch", json={"mode": "STOP_NEW_ORDERS",
                                                "reason": "test manual"})
    assert r.status_code == 200, r.text
    state = r.json()["state"]
    assert state["active"] is True
    assert state["mode"] == "STOP_NEW_ORDERS"
    assert state["actor"] == "tester"

    # order baru ditolak risk gate
    tick = market.update_tick("XAUUSD", bid=1999.85, ask=2000.15)
    r = await client_2fa.post("/orders", json={
        "symbol": "XAUUSD", "side": "BUY", "volume": 0.1, "sl": 1998.0, "tp": 2005.0})
    assert r.status_code == 422
    assert any("kill-switch" in reason for reason in r.json()["rejected_reasons"])

    # release
    r = await client_2fa.post("/kill-switch/release", json={})
    assert r.status_code == 200
    assert r.json()["state"]["active"] is False

    # order diterima kembali
    r = await client_2fa.post("/orders", json={
        "symbol": "XAUUSD", "side": "BUY", "volume": 0.1, "sl": 1998.0, "tp": 2005.0})
    assert r.status_code == 201


@pytest.mark.asyncio
async def test_events_recorded_activate_release(client_2fa):
    await client_2fa.post("/kill-switch", json={"mode": "STOP_NEW_ORDERS"})
    await client_2fa.post("/kill-switch/release", json={})
    events = await _events()
    actions = [e["action"] for e in events]
    assert "ACTIVATE" in actions
    assert "RELEASE" in actions
    activate = next(e for e in events if e["action"] == "ACTIVATE")
    assert activate["mode"] == "STOP_NEW_ORDERS"
    assert activate["source"] == "dashboard"
    assert activate["actor"] == "tester"


@pytest.mark.asyncio
async def test_stop_and_flatten_requires_confirm(client):
    await _insert_position(501, profit=1.0)
    r = await client.post("/kill-switch", json={"mode": "STOP_AND_FLATTEN"})
    assert r.status_code == 400
    assert "slippage" in r.json()["detail"].lower()
    # belum aktif
    assert (await kill_switch.get_state())["active"] is False

    r = await client.post("/kill-switch", json={"mode": "STOP_AND_FLATTEN", "confirm": True})
    assert r.status_code, r.text
    body = r.json()
    assert body["state"]["mode"] == "STOP_AND_FLATTEN"
    assert body["flatten"]["requested"] == 1
    order = body["flatten"]["orders"][0]
    assert order["position_ticket"] == 501
    assert order["side"] == "SELL"  # inverse dari posisi BUY


@pytest.mark.asyncio
async def test_flatten_endpoint_requires_confirm(client_2fa):
    r = await client_2fa.post("/kill-switch/flatten", json={})
    assert r.status_code == 400
    r = await client_2fa.post("/kill-switch/flatten", json={"confirm": True})
    assert r.status_code == 200
    assert r.json()["flatten"]["requested"] == 0  # tidak ada posisi terbuka


@pytest.mark.asyncio
async def test_flatten_wrong_totp_code_rejected(client_2fa):
    """QA UI-D6 [7_flatten_wrong_2FA]: code TOTP salah di body tidak boleh
    diabaikan; flatten tidak boleh dieksekusi (regresi GAP-4)."""
    from app import totp

    import time

    # enrol secret baru supaya test tahu secret yang sedang aktif
    secret = (await client_2fa.post("/auth/2fa/setup")).json()["secret"]
    r = await client_2fa.post("/auth/2fa/enable",
                              json={"code": totp.totp_at(secret)})
    assert r.status_code == 200, r.text

    await _insert_position(601, profit=1.0)

    # code salah (secret lain) -> 403, TIDAK ada flatten
    wrong = totp.totp_at("JBSWY3DPEHPK3PXP")
    r = await client_2fa.post("/kill-switch/flatten",
                              json={"confirm": True, "code": wrong})
    assert r.status_code == 403, r.text
    assert not await _events("FLATTEN_REQUEST")
    # posisi masih terbuka
    async with db.pool().connection() as conn:
        rows = await conn.execute("SELECT status FROM positions WHERE ticket = 601")
        assert (await rows.fetchone())["status"] == "OPEN"

    # code valid -> flatten dieksekusi
    r = await client_2fa.post("/kill-switch/flatten",
                              json={"confirm": True,
                                    "code": totp.totp_at(secret, time.time() + 30)})
    assert r.status_code == 200, r.text
    assert r.json()["flatten"]["requested"] == 1


@pytest.mark.asyncio
async def test_pause_strategy_mode(client_2fa):
    r = await client_2fa.post("/kill-switch", json={"mode": "PAUSE_STRATEGY", "strategy": "london_breakout"})
    assert r.status_code, r.text
    assert r.json()["paused_strategies"] == ["london_breakout"]

    tick = market.update_tick("XAUUSD", bid=1999.85, ask=2000.15)
    # order strategi lain tetap lolos
    r = await client_2fa.post("/orders", json={
        "symbol": "XAUUSD", "side": "BUY", "volume": 0.1, "sl": 1998.0, "tp": 2005.0,
        "strategy": "manual"})
    assert r.status_code == 201, r.text
    # order strategi yang di-pause ditolak
    r = await client_2fa.post("/orders", json={
        "symbol": "XAUUSD", "side": "BUY", "volume": 0.1, "sl": 1998.0, "tp": 2005.0,
        "strategy": "london_breakout"})
    assert r.status_code == 422
    assert any("PAUSE_STRATEGY" in x for x in r.json()["rejected_reasons"])

    # resume satu strategi -> kill-switch mati (daftar kosong)
    r = await client_2fa.post("/kill-switch/release", json={"strategy": "london_breakout"})
    assert r.status_code
    assert r.json()["state"]["active"] is False
    assert r.json()["paused_strategies"] == []


@pytest.mark.asyncio
async def test_global_halt_release_requires_checklist(client_2fa):
    await client_2fa.post("/kill-switch", json={"mode": "GLOBAL_HALT", "reason": "darurat"})
    r = await client_2fa.post("/kill-switch/release", json={})
    assert r.status_code == 400
    detail = r.json()["detail"]
    assert "checklist" in detail["message"].lower()
    assert len(detail["recovery_checklist"]) == len(RECOVERY_CHECKLIST)
    # masih aktif
    assert (await kill_switch.get_state())["active"] is True

    r = await client_2fa.post("/kill-switch/release", json={"checklist_ack": True})
    assert r.status_code
    assert r.json()["state"]["active"] is False


@pytest.mark.asyncio
async def test_escalation_to_higher_severity(client):
    await client.post("/kill-switch", json={"mode": "STOP_NEW_ORDERS"})
    state = await kill_switch.activate("GLOBAL_HALT", reason="escalate",
                                       source="auto:test", actor="auto")
    assert state["mode"] == "GLOBAL_HALT"
    actions = [e["action"] for e in await _events()]
    assert "ESCALATE" in actions
    # downgrade manual saat aktif: no-op (tetap GLOBAL_HALT)
    state = await kill_switch.activate("STOP_NEW_ORDERS", source="dashboard", actor="t")
    assert state["mode"] == "GLOBAL_HALT"


@pytest.mark.asyncio
async def test_release_event_records_transition_reason(client_2fa):
    """RELEASE mencatat alasan PELEPASAN, bukan salinan alasan aktivasi.

    Kasus historis: event RELEASE membawa reason aktivasi (mis. drawdown),
    sehingga History menampilkan alasan yang salah untuk transisi itu.
    """
    activate_reason = "drawdown harian 1.88% > 1.5%"
    r = await client_2fa.post("/kill-switch", json={
        "mode": "GLOBAL_HALT", "reason": activate_reason})
    assert r.status_code == 200, r.text
    r = await client_2fa.post("/kill-switch/release", json={"checklist_ack": True})
    assert r.status_code == 200, r.text

    events = await _events()
    act = next(e for e in events if e["action"] == "ACTIVATE")
    rel = next(e for e in events if e["action"] == "RELEASE")

    assert act["reason"] == activate_reason
    assert rel["reason"] != activate_reason
    assert "release manual oleh owner" in rel["reason"]
    assert "(tester)" in rel["reason"]
    assert "checklist recovery diakui" in rel["reason"]
    assert rel["actor"] == "tester"
    assert rel["mode"] == "GLOBAL_HALT"
    # alasan aktivasi lama tetap utuh di details
    assert rel["details"]["previous"]["reason"] == activate_reason
    assert rel["details"]["previous_reason"] == activate_reason
    assert rel["details"]["release_reason"] == rel["reason"]
    assert rel["details"]["checklist_ack"] is True
    # dari -> ke eksplisit untuk kedua event transisi
    assert act["details"]["from"]["active"] is False
    assert act["details"]["to"]["active"] is True
    assert act["details"]["to"]["mode"] == "GLOBAL_HALT"
    assert rel["details"]["from"]["mode"] == "GLOBAL_HALT"
    assert rel["details"]["to"]["active"] is False
    assert rel["details"]["conditions"]["daily_drawdown_pct"] is not None


@pytest.mark.asyncio
async def test_release_global_halt_without_checklist_keeps_activation_reason(client_2fa):
    """Release GLOBAL_HALT yang ditolak tidak boleh mencatat event palsu."""
    await client_2fa.post("/kill-switch", json={"mode": "GLOBAL_HALT", "reason": "darurat"})
    r = await client_2fa.post("/kill-switch/release", json={})
    assert r.status_code == 400
    assert not any(e["action"] == "RELEASE" for e in await _events())


@pytest.mark.asyncio
async def test_pause_strategy_single_event_with_transition_details(client_2fa):
    """PAUSE_STRATEGY: satu event ACTIVATE (tanpa duplikat) + from/to + alasan."""
    r = await client_2fa.post("/kill-switch", json={
        "mode": "PAUSE_STRATEGY", "strategy": "london_breakout"})
    assert r.status_code == 200, r.text
    activate_events = [e for e in await _events("ACTIVATE") if e["mode"] == "PAUSE_STRATEGY"]
    assert len(activate_events) == 1
    ev = activate_events[0]
    assert ev["reason"] and "london_breakout" in ev["reason"]
    assert "di-pause" in ev["reason"]
    assert "tester" in ev["reason"]
    assert ev["actor"] == "tester"
    assert ev["strategy"] == "london_breakout"
    assert ev["details"]["paused_strategies"] == ["london_breakout"]
    assert ev["details"]["from"]["active"] is False
    assert ev["details"]["to"]["mode"] == "PAUSE_STRATEGY"


@pytest.mark.asyncio
async def test_release_strategy_event_records_actor_and_from_to(client_2fa):
    """Pelepasan satu strategi: reason menyebut aktor, details from -> to."""
    await client_2fa.post("/kill-switch", json={
        "mode": "PAUSE_STRATEGY", "strategy": "london_breakout"})
    r = await client_2fa.post("/kill-switch/release", json={"strategy": "london_breakout"})
    assert r.status_code == 200, r.text
    assert r.json()["state"]["active"] is False
    releases = [e for e in await _events("RELEASE") if e["strategy"] == "london_breakout"]
    assert len(releases) == 1
    ev = releases[0]
    assert "resume strategi london_breakout" in ev["reason"]
    assert "tester" in ev["reason"]
    assert ev["actor"] == "tester"
    assert ev["details"]["from"]["mode"] == "PAUSE_STRATEGY"
    assert ev["details"]["to"]["active"] is False
    assert ev["details"]["paused_strategies"] == []


@pytest.mark.asyncio
async def test_triggers_updated_event_has_previous_values(client_2fa):
    """TRIGGERS_UPDATED: reason menyebut aktor, details memuat nilai lama."""
    r = await client_2fa.put("/kill-switch/triggers",
                             json={"password": "testpass", "daily_drawdown_pct": 3.0})
    assert r.status_code == 200, r.text
    ev = (await _events("TRIGGERS_UPDATED"))[-1]
    assert "tester" in ev["reason"]
    assert ev["actor"] == "tester"
    assert ev["details"]["updates"] == {"daily_drawdown_pct": 3.0}
    assert ev["details"]["previous"]["daily_drawdown_pct"] == \
        kill_switch.DEFAULT_TRIGGERS["daily_drawdown_pct"]


@pytest.mark.asyncio
async def test_escalation_event_records_from_to(client):
    """ESCALATE: from = mode lama, to = mode baru (bukan salinan alasan)."""
    await client.post("/kill-switch", json={"mode": "STOP_NEW_ORDERS", "reason": "awal"})
    await kill_switch.activate("GLOBAL_HALT", reason="drawdown total 8% > 5%",
                               source="auto:total_drawdown", actor="auto")
    ev = (await _events("ESCALATE"))[-1]
    assert ev["reason"] == "drawdown total 8% > 5%"
    assert ev["actor"] == "auto"
    assert ev["details"]["from"]["mode"] == "STOP_NEW_ORDERS"
    assert ev["details"]["to"]["mode"] == "GLOBAL_HALT"
    assert ev["details"]["previous"]["reason"] == "awal"


@pytest.mark.asyncio
async def test_status_endpoint(client):
    await client.post("/kill-switch", json={"mode": "STOP_NEW_ORDERS"})
    r = await client.get("/kill-switch")
    assert r.status_code, r.text
    body = r.json()
    assert body["state"]["active"] is True
    assert "metrics" in body and "triggers" in body
    assert body["slippage_warning"] == SLIPPAGE_WARNING


@pytest.mark.asyncio
async def test_triggers_update(client_2fa):
    r = await client_2fa.put("/kill-switch/triggers",
                             json={"password": "testpass", "daily_drawdown_pct": 5.0})
    assert r.status_code, r.text
    assert r.json()["triggers"]["daily_drawdown_pct"] == 5.0
    r = await client_2fa.put("/kill-switch/triggers",
                             json={"password": "testpass", "modes": {"ea_offline": "STOP_NEW_ORDERS"}})
    assert r.json()["triggers"]["modes"]["ea_offline"] == "STOP_NEW_ORDERS"
    r = await client_2fa.put("/kill-switch/triggers",
                             json={"password": "testpass", "modes": {"ea_offline": "MODE_ANEH"}})
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_triggers_update_ea_offline_split(client_2fa):
    """A12 (6 s, tandai offline) dan ambang halt (60 s) disetel terpisah, ter-audit."""
    r = await client_2fa.put(
        "/kill-switch/triggers",
        json={"password": "testpass", "ea_offline_seconds": 6.0, "ea_offline_halt_seconds": 60.0},
    )
    assert r.status_code, r.text
    triggers = r.json()["triggers"]
    assert triggers["ea_offline_seconds"] == 6.0
    assert triggers["ea_offline_halt_seconds"] == 60.0
    async with db.pool().connection() as conn:
        rows = await (await conn.execute(
            "select key, new_value from settings_audit "
            "where key = 'kill_switch_triggers' order by id desc limit 1"
        )).fetchall()
    assert rows, "perubahan trigger wajib tercatat di settings_audit"
    assert rows[0]["new_value"]["ea_offline_halt_seconds"] == 60.0


# ---------------------------------------------------------------- auto-trigger (simulasi)

@pytest.mark.asyncio
async def test_trigger_daily_drawdown(client):
    # 3.2% dari daily_start_balance 10000 = -320
    await _insert_closed_position(901, profit=-320.0)
    fired = await kill_switch.run_trigger_checks()
    triggers = [f["trigger"] for f in fired]
    assert "daily_drawdown" in triggers
    state = await kill_switch.get_state()
    assert state["active"] and state["mode"] == "GLOBAL_HALT"
    assert state["source"] == "auto:daily_drawdown"
    events = [e for e in await _events("ACTIVATE") if (e["source"] or "").startswith("auto:")]
    assert any(e["mode"] == "GLOBAL_HALT" and e["source"] == "auto:daily_drawdown" for e in events)


@pytest.mark.asyncio
async def test_trigger_daily_drawdown_below_threshold_no_fire(client):
    await _insert_closed_position(902, profit=-100.0)  # 1% < 3%
    fired = await kill_switch.run_trigger_checks()
    assert fired == []
    assert (await kill_switch.get_state())["active"] is False


@pytest.mark.asyncio
async def test_daily_pnl_exclude_posisi_qa(client):
    """Regresi t_baeb3ce4: posisi dari order user role 'qa' (TANPA penandaan
    QA_REATTRIBUTED sekalipun) dan posisi bertanda QA_REATTRIBUTED tidak
    dihitung daily_pnl. Kontaminasi QA memicu drawdown halt palsu (insiden
    25 Nov 18:18 WIB: 56 posisi QA -51.03 ikut terhitung). Rugi live dari
    user non-QA tetap dihitung."""
    from app.routes import _daily_pnl

    async with db.pool().connection() as conn:
        await conn.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (%s, %s, 'qa')",
            ("svc-qa-driver-dp", "uji-bukan-hash-asli"))
        await conn.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (%s, %s, 'admin')",
            ("admin-dp", "uji-bukan-hash-asli"))
        for username, profit, ticket, reattr in (
            ("admin-dp", -30.0, 910001, False),        # live: dihitung
            ("svc-qa-driver-dp", -50.0, 910002, False),  # QA: keluar
            ("admin-dp", -20.0, 910003, True),       # QA_REATTRIBUTED: keluar
        ):
            row = await conn.execute(
                "INSERT INTO orders (symbol, side, volume, status, created_at) "
                "VALUES ('XAUUSD', 'BUY', 0.01, 'FILLED', now()) RETURNING id")
            oid = (await row.fetchone())["id"]
            await conn.execute(
                "INSERT INTO order_events (order_id, from_status, to_status, payload) "
                "VALUES (%s, NULL, 'RECEIVED', %s)",
                (oid, json.dumps({"source": "api", "username": username})))
            if reattr:
                await conn.execute(
                    "INSERT INTO order_events (order_id, from_status, to_status, payload) "
                    "VALUES (%s, NULL, 'QA_REATTRIBUTED', %s)",
                    (oid, json.dumps({"username": "svc-qa-driver-dp",
                                      "task": "t_baeb3ce4"})))
            await conn.execute(
                "INSERT INTO positions (ticket, order_id, symbol, side, volume, "
                "open_price, profit, status, close_time) "
                "VALUES (%s, %s, 'XAUUSD', 'BUY', 0.01, 2000.0, %s, 'CLOSED', now())",
                (ticket, oid, profit))
    async with db.pool().connection() as conn:
        m = await kill_switch.compute_metrics(conn)
        assert m["daily_pnl"] == pytest.approx(-30.0)
        assert await _daily_pnl(conn) == pytest.approx(-30.0)


@pytest.mark.asyncio
async def test_legacy_halted_mirror_ikut_activate_dan_release(client):
    """t_baeb3ce4: flag legacy 'halted' harus mengikuti kill-switch.

    Dulu routes men-set halted=True saat auto-halt drawdown tapi tidak ada
    yang menghapusnya: setelah satu halt, semua order ditolak selamanya
    dengan pesan fallback 'kill-switch aktif (mode: STOP_NEW_ORDERS)' walau
    state kill_switch sudah inactive (insiden 25 Nov 18:34 WIB: 16 order QA
    ditolak padahal gate drawdown sudah beres)."""
    # activate mode global menyalakan mirror
    await kill_switch.activate("GLOBAL_HALT", reason="uji", source="uji", actor="uji")
    assert (await db.get_settings()).get("halted") is True
    # release penuh mematikannya
    await kill_switch.release(checklist_ack=True, source="uji", actor="uji")
    assert (await db.get_settings()).get("halted") is False
    # mirror basi (state sudah inactive, halted masih True) dibersihkan release
    await db.set_setting("halted", True)
    await kill_switch.release(checklist_ack=True, source="uji", actor="uji")
    assert (await db.get_settings()).get("halted") is False
    # PAUSE_STRATEGY tidak menghentikan strategi lain -> halted tetap False
    await kill_switch.activate("PAUSE_STRATEGY", strategy="alpha", source="uji", actor="uji")
    assert (await db.get_settings()).get("halted") is False
    await kill_switch.release(strategy="alpha", source="uji", actor="uji")


@pytest.mark.asyncio
async def test_trigger_total_drawdown(client):
    await db.set_setting("equity_high_water_mark", 10000.0)
    await _insert_position(903, profit=-850.0)  # 8.5% dari puncak
    fired = await kill_switch.run_trigger_checks()
    assert any(f["trigger"] == "total_drawdown" for f in fired)
    assert (await kill_switch.get_state())["mode"] == "GLOBAL_HALT"


@pytest.mark.asyncio
async def test_trigger_ea_offline_with_open_positions(client):
    await _insert_position(904, profit=0.0)
    # EA tidak terlihat dalam waktu sangat lama -> age besar
    import time as _time
    kill_switch._ea_seen_mono = _time.monotonic() - 9999.0
    kill_switch._ea_last_persist_mono = 0.0
    fired = await kill_switch.run_trigger_checks()
    assert any(f["trigger"] == "ea_offline" for f in fired)
    assert (await kill_switch.get_state())["mode"] == "GLOBAL_HALT"


@pytest.mark.asyncio
async def test_trigger_ea_offline_requires_open_positions(client):
    kill_switch._ea_seen_mono = None  # EA offline
    fired = await kill_switch.run_trigger_checks()
    assert not any(f["trigger"] == "ea_offline" for f in fired)


@pytest.mark.asyncio
async def test_trigger_ea_offline_uses_halt_threshold(client):
    """A12 6 s hanya menandai offline; GLOBAL_HALT menunggu ambang halt (60 s)."""
    import time as _time
    await _insert_position(906, profit=0.0)
    kill_switch._ea_last_persist_mono = _time.monotonic()  # jangan persist ke DB
    kill_switch._ea_seen_mono = _time.monotonic() - 10.0  # sudah > 6 s, belum > 60 s
    fired = await kill_switch.run_trigger_checks()
    assert not any(f["trigger"] == "ea_offline" for f in fired), \
        "hiccup 10 s tidak boleh memicu GLOBAL_HALT"
    kill_switch._ea_seen_mono = _time.monotonic() - 61.0
    fired = await kill_switch.run_trigger_checks()
    assert any(f["trigger"] == "ea_offline" for f in fired)
    assert (await kill_switch.get_state())["mode"] == "GLOBAL_HALT"


@pytest.mark.asyncio
async def test_trigger_ea_online_no_fire(client):
    await _insert_position(905, profit=0.0)
    await kill_switch.mark_ea_seen()  # EA baru saja kontak
    fired = await kill_switch.run_trigger_checks()
    assert not any(f["trigger"] == "ea_offline" for f in fired)


@pytest.mark.asyncio
async def test_trigger_consecutive_failed_orders(client):
    for i in range(3):
        await _insert_order("FAILED", created_seconds_ago=10 - i)
    fired = await kill_switch.run_trigger_checks()
    assert any(f["trigger"] == "consecutive_failed" for f in fired)
    state = await kill_switch.get_state()
    assert state["mode"] == "STOP_NEW_ORDERS"
    assert state["source"] == "auto:consecutive_failed"


@pytest.mark.asyncio
async def test_trigger_consecutive_failed_two_no_fire(client):
    for i in range(2):
        await _insert_order("FAILED", created_seconds_ago=10 - i)
    fired = await kill_switch.run_trigger_checks()
    assert not any(f["trigger"] == "consecutive_failed" for f in fired)


@pytest.mark.asyncio
async def test_trigger_consecutive_failed_ignores_risk_rejections(client):
    for i in range(3):
        await _insert_order("FAILED", created_seconds_ago=10 - i, fail_risk_rejected=True)
    fired = await kill_switch.run_trigger_checks()
    assert not any(f["trigger"] == "consecutive_failed" for f in fired)


@pytest.mark.asyncio
async def test_trigger_consecutive_failed_broken_by_filled_order(client):
    await _insert_order("FAILED", created_seconds_ago=30)
    await _insert_order("FAILED", created_seconds_ago=20)
    await _insert_order("FILLED", created_seconds_ago=10)
    await _insert_order("FAILED", created_seconds_ago=5)
    fired = await kill_switch.run_trigger_checks()
    assert not any(f["trigger"] == "consecutive_failed" for f in fired)


@pytest.mark.asyncio
async def test_release_resets_failed_streak(client_2fa):
    for i in range(3):
        await _insert_order("FAILED", created_seconds_ago=30 - i)
    await kill_switch.run_trigger_checks()
    await client_2fa.post("/kill-switch/release", json={})
    # order lama tidak boleh langsung memicu lagi
    fired = await kill_switch.run_trigger_checks()
    assert not any(f["trigger"] == "consecutive_failed" for f in fired)


@pytest.mark.asyncio
async def test_trigger_configurable_disable(client_2fa):
    await _insert_closed_position(906, profit=-500.0)  # 5% DD
    await client_2fa.put("/kill-switch/triggers", json={"daily_drawdown_pct": None})
    # None = dinonaktifkan (exclude_none membuang None) -> pakai PUT terpisah via db
    await db.set_setting("kill_switch_triggers", {"daily_drawdown_pct": None})
    fired = await kill_switch.run_trigger_checks()
    assert not any(f["trigger"] == "daily_drawdown" for f in fired)


@pytest.mark.asyncio
async def test_trigger_mode_configurable(client):
    await _insert_closed_position(907, profit=-400.0)
    await db.set_setting("kill_switch_triggers",
                         {"modes": {"daily_drawdown": "STOP_NEW_ORDERS"}})
    fired = await kill_switch.run_trigger_checks()
    assert any(f["trigger"] == "daily_drawdown" for f in fired)
    assert (await kill_switch.get_state())["mode"] == "STOP_NEW_ORDERS"


@pytest.mark.asyncio
async def test_auto_trigger_does_not_escalate_when_active_same_mode(client):
    await _insert_closed_position(908, profit=-320.0)
    await kill_switch.run_trigger_checks()
    n_before = len([e for e in await _events("ACTIVATE") if (e["source"] or "").startswith("auto:")])
    await kill_switch.run_trigger_checks()  # kondisi masih terpenuhi
    n_after = len([e for e in await _events("ACTIVATE") if (e["source"] or "").startswith("auto:")])
    assert n_before == n_after  # tidak ada event duplikat saat sudah aktif


# ---------------------------------------------------------------- flatten E2E via bridge

@pytest.mark.asyncio
async def test_stop_and_flatten_close_order_roundtrip(client, bridge_token):
    from app.worker import claim_one_order

    headers = {"Authorization": f"Bearer {bridge_token}"}
    await _insert_position(601, side="BUY", volume=0.10, profit=2.0)
    r = await client.post("/kill-switch",
                          json={"mode": "STOP_AND_FLATTEN", "confirm": True})
    order = r.json()["flatten"]["orders"][0]

    claimed = await claim_one_order()  # worker loop tidak jalan di test
    assert claimed is not None

    # EA ambil command CLOSE
    r = await client.get("/bridge/poll?timeout_s=0", headers=headers)
    cmd = r.json()
    assert cmd["action"] == "CLOSE"
    assert cmd["ticket"] == "601"  # string sesuai kontrak EA
    assert cmd["order_id"] == order["order_id"]

    # EA laporkan FILLED
    r = await client.post("/bridge/result", headers=headers, json={
        "command_id": cmd["command_id"], "status": "FILLED",
        "ticket": 999999, "price": 2001.5})
    assert r.status_code, r.text

    # posisi tertutup di DB
    pos = (await client.get("/positions")).json()
    assert pos[0]["status"] == "CLOSED"
    assert float(pos[0]["close_price"]) == 2001.5


@pytest.mark.asyncio
async def test_open_order_poll_response_has_no_action(client, bridge_token):
    """Kontrak EA lama: response poll untuk order OPEN tanpa field action/ticket."""
    from app.worker import claim_one_order

    headers = {"Authorization": f"Bearer {bridge_token}"}
    market.update_tick("XAUUSD", bid=1999.85, ask=2000.15)
    r = await client.post("/orders", json={
        "symbol": "XAUUSD", "side": "BUY", "volume": 0.1, "sl": 1998.0, "tp": 2005.0})
    assert r.status_code == 201
    claimed = await claim_one_order()  # worker loop tidak jalan di test
    assert claimed is not None
    r = await client.get("/bridge/poll?timeout_s=0", headers=headers)
    cmd = r.json()
    assert cmd is not None
    assert "action" not in cmd
    assert "ticket" not in cmd
    assert cmd["side"] == "BUY"


# ---------------------------------------------------------------- mismatch (reconciler)

@pytest.mark.asyncio
async def test_position_mismatch_triggers_kill_switch(client, bridge_token):
    headers = {"Authorization": f"Bearer {bridge_token}"}
    # posisi terbuka di DB
    await client.post("/bridge/positions", json={"positions": [
        {"ticket": 701, "symbol": "XAUUSD", "side": "BUY", "volume": 0.1,
         "open_price": 2000.0, "profit": 5.0}]}, headers=headers)
    # snapshot berikutnya: posisi hilang tanpa CLOSE order
    r = await client.post("/bridge/positions", json={"positions": []}, headers=headers)
    assert r.json()["closed"] == [701]
    state = await kill_switch.get_state()
    assert state["active"] and state["mode"] == "GLOBAL_HALT"
    assert state["source"] == "auto:position_mismatch"
    # posisi ditandai unexplained di raw
    pos = (await client.get("/positions")).json()
    assert pos[0]["raw"].get("unexplained") is True


@pytest.mark.asyncio
async def test_position_close_with_filled_close_order_is_explained(client, bridge_token):
    headers = {"Authorization": f"Bearer {bridge_token}"}
    await client.post("/bridge/positions", json={"positions": [
        {"ticket": 702, "symbol": "XAUUSD", "side": "SELL", "volume": 0.1,
         "open_price": 2000.0, "profit": -1.0}]}, headers=headers)
    # CLOSE order FILLED untuk ticket 702 (penutupan sah)
    async with db.pool().connection() as conn:
        row = await conn.execute(
            "INSERT INTO orders (symbol, side, volume, strategy, ticket, action, status) "
            "VALUES ('XAUUSD', 'BUY', 0.10, 'manual', 702, 'CLOSE', 'FILLED') RETURNING id")
        created = await row.fetchone()
        await conn.execute(
            "INSERT INTO order_events (order_id, from_status, to_status, payload) "
            "VALUES (%s, 'SENT', 'FILLED', '{}')", (created["id"],))
    # snapshot tanpa posisi
    r = await client.post("/bridge/positions", json={"positions": []}, headers=headers)
    assert r.json()["closed"] == [702]
    assert (await kill_switch.get_state())["active"] is False
    pos = (await client.get("/positions")).json()
    assert pos[0]["raw"].get("unexplained") is None


@pytest.mark.asyncio
async def test_position_mismatch_can_be_disabled(client, bridge_token):
    headers = {"Authorization": f"Bearer {bridge_token}"}
    await db.set_setting("kill_switch_triggers", {"position_mismatch": False})
    await client.post("/bridge/positions", json={"positions": [
        {"ticket": 703, "symbol": "XAUUSD", "side": "BUY", "volume": 0.1,
         "open_price": 2000.0, "profit": 1.0}]}, headers=headers)
    await client.post("/bridge/positions", json={"positions": []}, headers=headers)
    assert (await kill_switch.get_state())["active"] is False


# ---------------------------------------------------------------- persistensi

@pytest.mark.asyncio
async def test_state_persists_in_db_across_settings_reads(client):
    await client.post("/kill-switch", json={"mode": "GLOBAL_HALT", "reason": "persist test"})
    # baca ulang langsung dari settings (seperti yang dilakukan service baru saat boot)
    settings = await db.get_settings()
    raw = settings["kill_switch"]
    assert isinstance(raw, dict) and raw["active"] is True
    state = kill_switch.normalize_state(raw)
    assert state["mode"] == "GLOBAL_HALT"
    # kompatibilitas bool legacy
    assert kill_switch.normalize_state(True)["mode"] == "STOP_NEW_ORDERS"
    assert kill_switch.normalize_state(False)["active"] is False
    assert kill_switch.normalize_state(None)["active"] is False


@pytest.mark.asyncio
async def test_legacy_bool_kill_switch_still_blocks(client):
    await db.set_setting("kill_switch", True)
    tick = market.update_tick("XAUUSD", bid=1999.85, ask=2000.15)
    r = await client.post("/orders", json={
        "symbol": "XAUUSD", "side": "BUY", "volume": 0.1, "sl": 1998.0, "tp": 2005.0})
    assert r.status_code == 422


# ---------------------------------------------------------------- risk gate mode-aware

@pytest.mark.asyncio
async def test_risk_gate_pause_strategy_only_blocks_paused():
    from app.risk import RiskContext, risk_gate

    order = {"symbol": "XAUUSD", "side": "BUY", "volume": 0.1, "sl": 1998.0, "tp": 2005.0,
             "strategy": "london_breakout"}
    settings = {"kill_switch": {"active": True, "mode": "PAUSE_STRATEGY"},
                "paused_strategies": ["news_trader"]}
    d = risk_gate(order, RiskContext(settings=settings, bid=1999.85, ask=2000.15,
                                     tick_age_s=0.1))
    assert d.ok
    settings["paused_strategies"] = ["london_breakout"]
    d = risk_gate(order, RiskContext(settings=settings, bid=1999.85, ask=2000.15,
                                     tick_age_s=0.1))
    assert not d.ok
    assert any("PAUSE_STRATEGY" in r for r in d.reasons)


@pytest.mark.asyncio
async def test_risk_gate_global_halt_blocks_all():
    from app.risk import RiskContext, risk_gate

    order = {"symbol": "XAUUSD", "side": "BUY", "volume": 0.1, "sl": 1998.0, "tp": 2005.0,
             "strategy": "manual"}
    settings = {"kill_switch": {"active": True, "mode": "GLOBAL_HALT"}}
    d = risk_gate(order, RiskContext(settings=settings, bid=1999.85, ask=2000.15,
                                     tick_age_s=0.1))
    assert not d.ok
    assert any("GLOBAL_HALT" in r for r in d.reasons)


# ---------------------------------------------------------------- t_4d524475
# Satu sumber kebenaran blokir = state kill-switch; 'halted' hanya mirror.

@pytest.mark.asyncio
async def test_t4d524475_auto_halt_drawdown_mirror_lalu_release(client):
    """(1)+(2): auto-halt drawdown menyalakan mirror 'halted'; release mematikannya."""
    await _insert_closed_position(4711, profit=-320.0)  # 3.2% > 3% -> GLOBAL_HALT
    fired = await kill_switch.run_trigger_checks()
    assert any(f["trigger"] == "daily_drawdown" for f in fired), fired
    settings = await db.get_settings()
    assert (settings.get("kill_switch") or {}).get("active") is True
    assert settings.get("halted") is True

    await kill_switch.release(checklist_ack=True, source="test", actor="owner:test")
    settings = await db.get_settings()
    assert settings.get("halted") is False, "release wajib menolkan mirror 'halted'"
    assert kill_switch.halted_effective(settings) is False


@pytest.mark.asyncio
async def test_t4d524475_state_setengah_halt_disembuhkan_monitor(client):
    """(2b): kill_switch inactive + mirror basi True -> monitor menormalkannya."""
    await db.set_setting("kill_switch", dict(kill_switch.INACTIVE_STATE))
    await db.set_setting("halted", True)
    assert (await db.get_settings()).get("halted") is True

    await kill_switch.run_trigger_checks()  # satu siklus monitor
    settings = await db.get_settings()
    assert settings.get("halted") is False
    assert kill_switch.halted_effective(settings) is False

    # PAUSE_STRATEGY bukan halted global -> mirror tetap False
    await kill_switch.activate("PAUSE_STRATEGY", strategy="alpha", source="test",
                               actor="test")
    await kill_switch.sync_legacy_halted()
    assert (await db.get_settings()).get("halted") is False


@pytest.mark.asyncio
async def test_t4d524475_guard_agent_dan_risk_gate_lanjut_setelah_release(client):
    """(3)+(4): setelah release, guard agent & risk gate tidak lagi fail-closed."""
    from app import llm_agent_loop, risk

    await kill_switch.activate("GLOBAL_HALT", reason="uji", source="test", actor="test")
    settings = await db.get_settings()
    assert llm_agent_loop._agent_blocked(settings) is True
    assert risk._kill_switch_blocks({"strategy": "manual"}, settings) is not None

    await kill_switch.release(checklist_ack=True, source="test", actor="owner:test")
    settings = await db.get_settings()
    assert llm_agent_loop._agent_blocked(settings) is False
    assert risk._kill_switch_blocks({"strategy": "manual"}, settings) is None


def test_t4d524475_semua_reader_mengabaikan_mirror_basi():
    """Guard agent, auto-SL, dan gate LLM membaca state kill-switch, bukan mirror."""
    from app import auto_sl, llm_agent_loop, llm_risk

    stale = {"halted": True, "kill_switch": {"active": False, "mode": None}}
    assert llm_agent_loop._agent_blocked(stale) is False
    assert auto_sl._paused(stale) is False
    assert llm_risk.control_block_reason(stale) is None

    active = {"halted": False, "kill_switch": {"active": True, "mode": "GLOBAL_HALT"}}
    assert llm_agent_loop._agent_blocked(active) is True
    assert auto_sl._paused(active) is True
    assert llm_risk.control_block_reason(active) is not None
