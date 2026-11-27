"""QA P1b v2: disconnect 10x + kill-switch 4 mode + auto-trigger + security.

Against fund2_test via ASGI (same env handling as tests/conftest.py).
Run: cd ~/fund2/api && PYTHONPATH=~/fund2/api .venv/bin/python \\
     ~/fund2/scripts/_qa_p1b_v2_rerun.py

Adaptasi P5 (2026-11-25):
- order_events append-only (PRD 19.4): TIDAK ada DELETE orders/order_events.
  Order non-terminal di-drain ke FAILED lewat state machine (event kompensasi).
- Kill-switch manual: aktivasi butuh admin; release/flatten/triggers butuh 2FA
  (PRD v2.2 §18). Sesi admin 'qaadmin' dibuat runtime dengan secret TOTP
  generate sendiri (tidak pernah dicetak/log).
- Rate-limit order diuji dengan ambang kecil (5/min) agar 12 order memicu 422.
"""
from __future__ import annotations

import asyncio
import os
import pathlib
import secrets
import sys
import time

_env_file = pathlib.Path("/home/tekka/fund2/api/.env")
if _env_file.exists() and "DATABASE_URL" not in os.environ:
    for line in _env_file.read_text().splitlines():
        if line.startswith("DATABASE_URL="):
            url = line.split("=", 1)[1]
            os.environ["DATABASE_URL"] = url[: url.rfind("/fund2")] + "/fund2_test"
            break

import json

from httpx import ASGITransport, AsyncClient

from app import db, kill_switch, market, state_machine as sm, totp as totp_mod
from app.auth import (clear_login_failures, get_login_failures, hash_password,
                      is_locked, reset_login_rate_limit)
from app.main import app
from app.worker import claim_one_order

RESULTS: list[dict] = []


def rec(area: str, name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append({"area": area, "name": name, "ok": ok, "detail": detail})
    print(f"[{'PASS' if ok else 'FAIL'}] {area}/{name} {detail}")


def rec_dev(area: str, name: str, detail: str) -> None:
    """Deviation: bukan failure, tapi menyimpang dari PRD (dicatat terpisah)."""
    RESULTS.append({"area": area, "name": name, "ok": None, "detail": detail})
    print(f"[DEV ] {area}/{name} {detail}")


async def fresh_client(username: str = "qa") -> AsyncClient:
    async with db.pool().connection() as conn:
        try:
            await conn.execute("DELETE FROM users WHERE username = %s", (username,))
        except Exception:
            await conn.execute("ROLLBACK")
        # user lama bisa punya orders (FK): pakai ulang bila masih ada
        row = await conn.execute(
            "INSERT INTO users (username, password_hash) VALUES (%s, %s) "
            "ON CONFLICT (username) DO UPDATE SET password_hash = EXCLUDED.password_hash "
            "RETURNING id",
            (username, hash_password("qapass")),
        )
        await row.fetchone()
    c = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
    r = await c.post("/auth/login", json={"username": username, "password": "qapass"})
    assert r.status_code == 200, r.text
    return c


async def csrf(c: AsyncClient) -> str:
    return (await c.get("/auth/me")).json()["csrf_token"]


def bridge(token: str) -> dict:
    return {"Authorization": "Bearer " + token}


async def wait_order_window(max_n: int = 15, timeout_s: int = 120) -> None:
    """Tunggu sampai order dalam window 60 detik < max_n.

    Append-only: order run sebelumnya tetap terhitung rate limit 60s
    (_orders_last_minute menghitung SELURUH tabel). Tanpa waits, section
    yang butuh 201 bisa kena 422 'order rate limit exceeded' palsu.
    """
    t0 = time.time()
    n = -1
    while time.time() - t0 < timeout_s:
        async with db.pool().connection() as conn:
            cur = await conn.execute(
                "SELECT count(*) AS n FROM orders WHERE created_at > now() - interval '60 seconds'")
            n = (await cur.fetchone())["n"]
        if n < max_n:
            if time.time() - t0 > 1:
                print(f"  [wait] order window bersih ({n} < {max_n}) setelah {time.time()-t0:.0f}s")
            return
        await asyncio.sleep(3)
    print(f"  [warn] order window masih {n} (>= {max_n}) setelah {timeout_s}s")


async def settings_set(key: str, value) -> None:
    await db.set_setting(key, value)


async def drain_nonterminal() -> int:
    """Order non-terminal -> FAILED via state machine (event kompensasi).

    Append-only (PRD 19.4): order_events tidak boleh DELETE/UPDATE, jadi
    pembersihan dilakukan dengan transisi sah + event baru, bukan menghapus
    sejarah. RISK_PASS harus lewat SENT dulu (transisi sah).
    """
    n = 0
    async with db.pool().connection() as conn:
        rows = await (await conn.execute(
            "SELECT id, status FROM orders WHERE status NOT IN "
            "('FILLED','FAILED','FILLED_THEN_CLOSED','ORPHAN_CLOSED','RECONCILED') "
            "ORDER BY created_at"
        )).fetchall()
        for r in rows:
            try:
                async with conn.transaction():
                    if r["status"] == "RISK_PASS":
                        await sm.transition(conn, r["id"], "SENT", {"by": "qa-drain"})
                    await sm.transition(conn, r["id"], "FAILED",
                                        {"by": "qa-drain", "reason": "qa cleanup"})
                    n += 1
            except Exception as e:
                print(f"  [drain] {r['id']} {r['status']}: {e}")
    if n:
        print(f"  [drain] {n} order non-terminal -> FAILED (event kompensasi)")
    return n


_adm: dict = {"client": None, "csrf": None, "secret": None, "until": 0.0}


async def admin_ensure() -> AsyncClient:
    """Sesi admin + assertion 2FA untuk release/flatten/triggers (PRD §18).

    User 'qaadmin' dibuat runtime di fund2_test dengan secret TOTP generate
    sendiri; secret & password tidak pernah dicetak/log. Assertion di-refresh
    bila mendekati expiry (window TWOFA_WINDOW_MIN = 5 menit; challenge rate
    limit 5/300s aman untuk refresh ±4 menit).
    """
    if _adm["client"] is None:
        password = secrets.token_urlsafe(18)
        secret = totp_mod.generate_secret()
        async with db.pool().connection() as conn:
            await conn.execute(
                "INSERT INTO users (username, password_hash, role, totp_secret, totp_enabled, totp_last_counter) "
                "VALUES ('qaadmin', %s, 'admin', %s, TRUE, -1) "
                "ON CONFLICT (username) DO UPDATE SET "
                "password_hash = EXCLUDED.password_hash, role = 'admin', "
                "totp_secret = EXCLUDED.totp_secret, totp_enabled = TRUE, "
                "totp_last_counter = -1",
                (hash_password(password), secret),
            )
        c = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
        r = await c.post("/auth/login", json={"username": "qaadmin", "password": password})
        assert r.status_code == 200, r.text
        _adm["client"] = c
        _adm["csrf"] = (await c.get("/auth/me")).json()["csrf_token"]
        c.headers["x-csrf-token"] = _adm["csrf"]  # default header semua request
        _adm["secret"] = secret
    if time.time() > _adm["until"] - 45:
        r = await _adm["client"].post(
            "/auth/2fa/challenge",
            json={"code": totp_mod.totp_at(_adm["secret"], None)},
            headers={"x-csrf-token": _adm["csrf"]})
        assert r.status_code == 200, r.text
        _adm["until"] = time.time() + 4 * 60
    return _adm["client"]


async def clean_slate() -> None:
    async with db.pool().connection() as conn:
        for t in ("positions", "candles", "sessions",
                  "kill_switch_events", "bridge_commands"):
            try:
                async with conn.transaction():
                    await conn.execute(f"DELETE FROM {t}")
            except Exception as e:
                print(f"[skip] DELETE {t}: {e}")
    await drain_nonterminal()
    for k, v in {
        "max_volume": 1.0, "max_daily_drawdown": 100.0, "max_spread": 0.50,
        "max_orders_per_min": 60, "halted": False, "kill_switch": False,
        "paused_strategies": [], "trigger_ack": None,
        "allowed_symbols": ["XAUUSD"],
    }.items():
        await settings_set(k, v)
    market._latest.clear()
    reset_login_rate_limit()
    kill_switch._ea_seen_mono = None


async def release_if_active(c: AsyncClient | None = None) -> None:
    st = await kill_switch.get_state()
    if st["active"]:
        await kill_switch.release(checklist_ack=True)
    await settings_set("halted", False)


async def disconnect_10x() -> None:
    """10x siklus: EA hidup -> order FILLED -> posisi terbuka -> EA crash ->
    order baru ditolak (data basi) -> EA reconnect -> snapshot -> rekonsiliasi.

    Genap: posisi masih terbuka di broker  -> snapshot OPEN  -> DB tetap OPEN.
    Ganjil : posisi ditutup broker saat offline (SL/TP) -> EA laporkan deal
             (snapshot berisi posisi status CLOSED + close_price/time) -> DB CLOSED.
    """
    area = "disconnect"
    bridge_token = (await db.get_settings())["bridge_token"]
    passed = 0
    details = []
    for i in range(1, 11):
        async with db.pool().connection() as conn:
            for t in ("positions", "candles",
                      "kill_switch_events", "bridge_commands"):
                try:
                    async with conn.transaction():
                        await conn.execute(f"DELETE FROM {t}")
                except Exception as e:
                    print(f"  [skip] DELETE {t}: {str(e).splitlines()[0]}")
        await drain_nonterminal()
        await release_if_active()
        market._latest.clear()
        c = await fresh_client(f"qa{i}")
        try:
            r = await c.post("/bridge/tick", json={"symbol": "XAUUSD", "bid": 1999.85, "ask": 2000.15}, headers=bridge(bridge_token))
            assert r.status_code == 200
            r = await c.post("/orders", json={"symbol": "XAUUSD", "side": "BUY", "volume": 0.01, "sl": 1998.0, "tp": 2005.0}, headers={"x-csrf-token": await csrf(c)})
            assert r.status_code == 201, r.text
            order = r.json()
            claimed = None
            for _ in range(20):
                claimed = await claim_one_order()
                if claimed:
                    break
            assert claimed is not None, "worker did not claim"
            r = await c.get("/bridge/poll?timeout_s=1", headers=bridge(bridge_token))
            cmd = r.json()
            assert cmd and cmd["command_id"] == order["command_id"]
            ticket = 700000 + i
            r = await c.post("/bridge/result", json={"command_id": cmd["command_id"], "status": "FILLED", "ticket": ticket, "price": 2000.17}, headers=bridge(bridge_token))
            assert r.status_code == 200
            snap_open = [{"ticket": ticket, "order_id": order["id"], "symbol": "XAUUSD", "side": "BUY", "volume": 0.01, "open_price": 2000.17, "profit": 1.25, "status": "OPEN"}]
            r = await c.post("/bridge/positions", json={"positions": snap_open}, headers=bridge(bridge_token))
            pos = (await c.get("/positions")).json()
            assert len(pos) == 1 and pos[0]["status"] == "OPEN"

            # EA crash: tick basi -> order baru harus ditolak (proteksi data basi)
            stale = market.latest("XAUUSD")
            stale["ts"] = time.time() - 30
            with market._lock:
                market._latest["XAUUSD"] = stale
            r = await c.post("/orders", json={"symbol": "XAUUSD", "side": "BUY", "volume": 0.01, "sl": 1998.0, "tp": 2005.0}, headers={"x-csrf-token": await csrf(c)})
            offline_rejected = r.status_code == 422 and any(("fresh" in x or "data" in x) for x in r.json().get("rejected_reasons", []))

            # EA reconnect + snapshot
            if i % 2 == 0:
                r = await c.post("/bridge/positions", json={"positions": snap_open}, headers=bridge(bridge_token))
                pos = (await c.get("/positions")).json()
                recon_ok = len(pos) == 1 and pos[0]["status"] == "OPEN" and pos[0]["ticket"] == ticket
                variant = "open-preserved"
            else:
                deal = [dict(snap_open[0], status="CLOSED", close_price=1999.10, close_time="2026-11-21T11:00:00Z", profit=-1.07)]
                r = await c.post("/bridge/positions", json={"positions": deal}, headers=bridge(bridge_token))
                pos = (await c.get("/positions")).json()
                recon_ok = len(pos) == 1 and pos[0]["status"] == "CLOSED" and pos[0]["ticket"] == ticket
                variant = "closed-with-deal"
            st = await kill_switch.get_state()
            no_false_ks = not st["active"]

            detail = (await c.get(f"/orders/{order['id']}")).json()
            chain = [e["to_status"] for e in detail["events"]]
            events_ok = chain == ["RECEIVED", "RISK_PASS", "SENT", "FILLED"]

            ok = offline_rejected and recon_ok and events_ok and no_false_ks
            passed += ok
            details.append(f"i{i}({variant}): offline_reject={offline_rejected} recon={recon_ok} events={events_ok} ks_off={no_false_ks}")
            print(f"  iter {i}: {'OK' if ok else 'BROKEN'} {details[-1]}")
        except Exception as exc:
            details.append(f"i{i}: EXC {exc!r}")
            print(f"  iter {i}: EXC {exc!r}")
        finally:
            try:
                await c.aclose()
            except Exception:
                pass
    rec(area, "disconnect_10x_reconcile", passed == 10, f"{passed}/10")


async def mismatch_killswitch() -> None:
    """Posisi hilang dari snapshot broker TANPA penutupan yang bisa dijelaskan
    -> kill-switch otomatis (PRD 5.7 auto-trigger reconciler + 5.8 poin 4)."""
    area = "killswitch"
    bridge_token = (await db.get_settings())["bridge_token"]
    c = await fresh_client("qamis")
    try:
        market.update_tick("XAUUSD", 1999.85, 2000.15)
        snap = [{"ticket": 800100, "symbol": "XAUUSD", "side": "BUY", "volume": 0.01, "open_price": 2000.0, "profit": 0.5, "status": "OPEN"}]
        r = await c.post("/bridge/positions", json={"positions": snap}, headers=bridge(bridge_token))
        assert r.status_code == 200
        # snapshot kosong: posisi menghilang tanpa jejak penutupan
        r = await c.post("/bridge/positions", json={"positions": []}, headers=bridge(bridge_token))
        st = await kill_switch.get_state()
        fired = st["active"] and st["mode"] == "GLOBAL_HALT"
        rec(area, "mismatch_auto_killswitch", fired, f"state={st['mode']} active={st['active']}")
        async with db.pool().connection() as conn:
            cur = await conn.execute("SELECT raw FROM positions WHERE ticket = 800100")
            row = await cur.fetchone()
            cur = await conn.execute(
                "SELECT source, mode FROM kill_switch_events ORDER BY id DESC LIMIT 1")
            ev = await cur.fetchone()
        flagged = row is not None and (row["raw"] or {}).get("unexplained") is True
        rec(area, "mismatch_position_flagged", flagged, f"raw={row['raw'] if row else None}")
        rec(area, "mismatch_event_audited", ev is not None and "auto" in (ev["source"] or ""), f"event={tuple(ev) if ev else None}")
        await release_if_active()
    finally:
        await c.aclose()


async def kill_switch_tests() -> None:
    area = "killswitch"
    bridge_token = (await db.get_settings())["bridge_token"]
    c = await fresh_client("qaks")
    adm = await admin_ensure()  # aktivasi butuh admin; release/flatten butuh 2FA
    try:
        async with db.pool().connection() as conn:
            await conn.execute("DELETE FROM positions")
        market.update_tick("XAUUSD", 1999.85, 2000.15)

        # 1. manual endpoint + mode STOP_NEW_ORDERS (admin; PRD §18: tanpa 2FA)
        r = await adm.post("/kill-switch", json={"mode": "STOP_NEW_ORDERS", "reason": "qa manual"})
        st = r.json().get("state", {})
        rec(area, "manual_stop_new_orders", r.status_code == 200 and st.get("active") and st.get("mode") == "STOP_NEW_ORDERS", f"{r.status_code} {st.get('mode')}")

        # 2. order ditolak saat aktif
        r = await c.post("/orders", json={"symbol": "XAUUSD", "side": "BUY", "volume": 0.01, "sl": 1998.0, "tp": 2005.0}, headers={"x-csrf-token": await csrf(c)})
        body = r.json()
        rec(area, "orders_blocked_when_active", r.status_code == 422 and any("kill-switch" in x for x in body.get("rejected_reasons", [])), f"{r.status_code} {body.get('rejected_reasons')}")

        # 3. GET status lengkap
        r = await c.get("/kill-switch")
        js = r.json()
        rec(area, "status_endpoint", r.status_code == 200 and "state" in js and "triggers" in js and "metrics" in js and "events" in js, f"{r.status_code} keys={sorted(js)}")

        # 4. release (2FA wajib, PRD §18)
        r = await adm.post("/kill-switch/release", json={})
        rec(area, "release", r.status_code == 200 and r.json()["state"]["active"] is False, f"{r.status_code}")

        # 5. GLOBAL_HALT: release tanpa checklist ditolak, dengan checklist boleh
        await adm.post("/kill-switch", json={"mode": "GLOBAL_HALT", "reason": "qa"})
        r = await adm.post("/kill-switch/release", json={})
        rec(area, "global_halt_release_needs_checklist", r.status_code == 400, f"{r.status_code}")
        r = await adm.post("/kill-switch/release", json={"checklist_ack": True})
        rec(area, "global_halt_release_with_checklist", r.status_code == 200 and r.json()["state"]["active"] is False, f"{r.status_code}")

        # 6. PAUSE_STRATEGY: strategi di-pause ditolak, strategi lain boleh
        await adm.post("/kill-switch", json={"mode": "PAUSE_STRATEGY", "strategy": "breakout"})
        market.update_tick("XAUUSD", 1999.85, 2000.15)
        r1 = await c.post("/orders", json={"symbol": "XAUUSD", "side": "BUY", "volume": 0.01, "sl": 1998.0, "tp": 2005.0, "strategy": "breakout"}, headers={"x-csrf-token": await csrf(c)})
        r2 = await c.post("/orders", json={"symbol": "XAUUSD", "side": "BUY", "volume": 0.01, "sl": 1998.0, "tp": 2005.0, "strategy": "manual"}, headers={"x-csrf-token": await csrf(c)})
        rec(area, "pause_strategy_scoped", r1.status_code == 422 and r2.status_code == 201, f"breakout={r1.status_code} manual={r2.status_code}")
        await adm.post("/kill-switch/release", json={"strategy": "breakout"})

        # 7. auto-halt drawdown harian via risk gate -> GLOBAL_HALT ter-audit
        async with db.pool().connection() as conn:
            await conn.execute(
                "INSERT INTO positions (ticket, symbol, side, volume, open_price, close_price, profit, status, close_time) "
                "VALUES (900001, 'XAUUSD', 'BUY', 0.10, 2000, 1990, -150.0, 'CLOSED', now())")
        market.update_tick("XAUUSD", 1999.85, 2000.15)
        r = await c.post("/orders", json={"symbol": "XAUUSD", "side": "BUY", "volume": 0.01, "sl": 1998.0, "tp": 2005.0}, headers={"x-csrf-token": await csrf(c)})
        st = await kill_switch.get_state()
        async with db.pool().connection() as conn:
            cur = await conn.execute("SELECT COUNT(*) AS n FROM kill_switch_events WHERE source='auto:daily_drawdown_risk_gate'")
            n = (await cur.fetchone())["n"]
        rec(area, "auto_halt_daily_drawdown", r.status_code == 422 and st["active"] and st["mode"] == "GLOBAL_HALT" and n >= 1, f"{r.status_code} mode={st['mode']} audit={n}")
        await release_if_active()
        async with db.pool().connection() as conn:
            await conn.execute("DELETE FROM positions WHERE ticket = 900001")

        # 8. auto-trigger EA offline > 60s dengan posisi terbuka
        async with db.pool().connection() as conn:
            await conn.execute(
                "INSERT INTO positions (ticket, symbol, side, volume, open_price, profit, status) "
                "VALUES (800002, 'XAUUSD', 'BUY', 0.01, 2000, 0.5, 'OPEN')")
        kill_switch._ea_seen_mono = time.monotonic() - 120  # EA tidak terlihat 120s
        fired = await kill_switch.run_trigger_checks()
        st = await kill_switch.get_state()
        names = [f["trigger"] for f in fired]
        rec(area, "auto_trigger_ea_offline", "ea_offline" in names and st["active"] and st["mode"] == "GLOBAL_HALT", f"fired={names}")
        kill_switch._ea_seen_mono = time.monotonic()
        await release_if_active()
        async with db.pool().connection() as conn:
            await conn.execute("DELETE FROM positions WHERE ticket = 800002")

        # 9. auto-trigger 3 FAILED beruntun (gagal eksekusi, bukan ditolak risk)
        await drain_nonterminal()  # bersihkan order non-terminal sisa langkah sebelumnya
        for _ in range(3):
            market.update_tick("XAUUSD", 1999.85, 2000.15)
            r = await c.post("/orders", json={"symbol": "XAUUSD", "side": "BUY", "volume": 0.01, "sl": 1998.0, "tp": 2005.0}, headers={"x-csrf-token": await csrf(c)})
            assert r.status_code == 201, r.text
            oid = r.json()["id"]
            await claim_one_order()
            rr = await c.get("/bridge/poll?timeout_s=1", headers=bridge(bridge_token))
            cmd = rr.json()
            await c.post("/bridge/result", json={"command_id": cmd["command_id"], "status": "FAILED", "reason": "qa-exec-fail"}, headers=bridge(bridge_token))
        fired = await kill_switch.run_trigger_checks()
        st = await kill_switch.get_state()
        names = [f["trigger"] for f in fired]
        rec(area, "auto_trigger_3_failed", "consecutive_failed" in names and st["active"] and st["mode"] == "STOP_NEW_ORDERS", f"fired={names} mode={st['mode']}")
        await release_if_active()

        # 10. flatten (STOP_AND_FLATTEN / /kill-switch/flatten, 2FA wajib §18)
        await drain_nonterminal()  # bersihkan order non-terminal sisa
        async with db.pool().connection() as conn:
            await conn.execute(
                "INSERT INTO positions (ticket, symbol, side, volume, open_price, profit, status) "
                "VALUES (800003, 'XAUUSD', 'BUY', 0.01, 2000, 0.5, 'OPEN')")
        r = await adm.post("/kill-switch/flatten", json={"confirm": False})
        rec(area, "flatten_needs_confirm", r.status_code == 400, f"{r.status_code}")
        r = await adm.post("/kill-switch/flatten", json={"confirm": True})
        js = r.json()
        n_flat = js.get("flatten", {}).get("requested", 0)
        rec(area, "flatten_creates_close_orders", r.status_code == 200 and n_flat == 1, f"{r.status_code} requested={n_flat}")
        await claim_one_order()
        rr = await c.get("/bridge/poll?timeout_s=1", headers=bridge(bridge_token))
        cmd = rr.json()
        close_cmd_ok = cmd and cmd.get("action") == "CLOSE" and cmd.get("ticket") == "800003"
        await c.post("/bridge/result", json={"command_id": cmd["command_id"], "status": "FILLED", "price": 2000.5}, headers=bridge(bridge_token))
        r = await c.post("/bridge/positions", json={"positions": []}, headers=bridge(bridge_token))
        pos = (await c.get("/positions")).json()
        tgt = [p for p in pos if p["ticket"] == 800003]
        rec(area, "flatten_close_command_e2e", close_cmd_ok and len(tgt) == 1 and tgt[0]["status"] == "CLOSED", f"cmd_ok={close_cmd_ok} pos={[(p['ticket'], p['status']) for p in pos]}")
        st = await kill_switch.get_state()
        if st["active"]:
            await release_if_active()

        # 11. PUT triggers: ubah threshold (2FA wajib, PRD §18)
        r = await adm.put("/kill-switch/triggers", json={"consecutive_failed_orders": 5})
        t = (await c.get("/kill-switch")).json()["triggers"]
        rec(area, "triggers_update", r.status_code == 200 and t.get("consecutive_failed_orders") == 5, f"{r.status_code} now={t.get('consecutive_failed_orders')}")
        await adm.put("/kill-switch/triggers", json={"consecutive_failed_orders": 3})

        # 12. persistence di DB (bertahan restart)
        r_act = await adm.post("/kill-switch", json={"mode": "STOP_NEW_ORDERS", "reason": "qa-persist"})
        async with db.pool().connection() as conn:
            cur = await conn.execute("SELECT value FROM settings WHERE key='kill_switch'")
            raw = (await cur.fetchone())["value"]
        rec(area, "state_persisted_in_db", r_act.status_code == 200 and isinstance(raw, dict) and raw.get("active") is True and raw.get("mode") == "STOP_NEW_ORDERS", f"post={r_act.status_code} raw={raw}")
        await release_if_active()
    finally:
        await c.aclose()


async def security() -> None:
    area = "security"
    bridge_token = (await db.get_settings())["bridge_token"]
    async with db.pool().connection() as conn:
        await conn.execute(
            "INSERT INTO users (username, password_hash) VALUES ('qa', %s) "
            "ON CONFLICT (username) DO UPDATE SET password_hash = EXCLUDED.password_hash",
            (hash_password("qapass"),),
        )

    # login rate limit: 12 percobaan gagal -> 429; lockout DB mengunci akun
    reset_login_rate_limit()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        codes = []
        wrongpw = "wr" + "ong"  # dibangun agar tidak tertukar dengan kredensial asli
        for _ in range(12):
            r = await c.post("/auth/login", json={"username": "qa", "password": wrongpw})
            codes.append(r.status_code)
        rec(area, "login_rate_limit_429", codes.count(429) >= 1, f"codes={codes}")
        async with db.pool().connection() as conn:
            f = await get_login_failures(conn, "qa")
        rec(area, "account_lockout_after_failures", is_locked(f),
            f"failed_count={f['failed_count'] if f else None} locked_until={f['locked_until'] if f else None}")
        async with db.pool().connection() as conn:  # buka kunci utk test sesi
            await clear_login_failures(conn, "qa")

    # sesi: cookie flags + CSRF + logout
    reset_login_rate_limit()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.post("/auth/login", json={"username": "qa", "password": "qapass"})
        setc = r.headers.get("set-cookie", "")
        rec(area, "cookie_httponly_samesite", "httponly" in setc.lower() and "samesite=strict" in setc.lower(), setc.split(";")[-2:].__repr__())
        rec_dev(area, "cookie_secure_absent", "Secure belum diset (loopback P1); WAJIB flip saat cutover domain (PRD 7)")
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c2:
            r2 = await c2.get("/orders")
            rec(area, "orders_requires_session", r2.status_code == 401, f"{r2.status_code}")
        r3 = await c.post("/orders", json={"symbol": "XAUUSD", "side": "BUY", "volume": 0.01, "sl": 1998, "tp": 2005})
        rec(area, "orders_requires_csrf", r3.status_code == 403, f"{r3.status_code}")
        tok = (await c.get("/auth/me")).json()["csrf_token"]
        await c.post("/auth/logout", headers={"x-csrf-token": tok})
        r4 = await c.get("/auth/me")
        rec(area, "logout_invalidates", r4.status_code == 401, f"{r4.status_code}")

    # bridge auth: Bearer required
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/bridge/poll?timeout_s=0")
        no_tok = r.status_code == 401
        r = await c.get("/bridge/poll?timeout_s=0", headers={"Authorization": "Bearer salah"})
        bad_tok = r.status_code == 401
        rec(area, "bridge_bearer_required", no_tok and bad_tok, f"no={no_tok} bad={bad_tok}")
        r = await c.get("/bridge/poll?timeout_s=0", headers=bridge(bridge_token))
        rec(area, "bridge_bearer_valid_ok", r.status_code == 200, f"{r.status_code}")

    # HMAC: EA kirim header X-Fund2-* tapi API minta Bearer -> 401 utk EA asli
    hdrs = {"X-Fund2-Timestamp": str(int(time.time())), "X-Fund2-Nonce": "a" * 32, "X-Fund2-Signature": "b" * 64}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/bridge/poll?timeout_s=0", headers=hdrs)
        rec_dev(area, "hmac_not_accepted_by_api", f"EA v5.00 kirim HMAC X-Fund2-* -> API 401 {r.status_code} (API masih Bearer; kontrak HMAC di dummy_bridge/EA v0 saja). Real EA belum bisa konek.")

    # /bridge/heartbeat tidak ada (EA kirim tiap 2 detik -> 405 -> backoff)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.post("/bridge/heartbeat", json={"ts": int(time.time()), "symbol": "XAUUSD", "bid": 2000, "ask": 2000.3, "spread": 0.3, "ea": "v0"}, headers=bridge(bridge_token))
        rec_dev(area, "heartbeat_endpoint_missing", f"POST /bridge/heartbeat -> {r.status_code}; EA MarkBridgeFail tiap 2 dtk (backoff s.d. 60s)")

    # tick batch format EA vs API
    ea_body = {"symbol": "XAUUSD", "ticks": [{"ts": int(time.time() * 1000), "bid": 2000.1, "ask": 2000.4, "spread": 0.3}]}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.post("/bridge/tick", json=ea_body, headers=bridge(bridge_token))
        rec_dev(area, "tick_batch_format_mismatch", f"EA kirim {{symbol,ticks:[..]}} -> API {r.status_code} (API minta {{symbol,bid,ask}})")

    # password hash adaptif (Argon2id sejak migrasi; bcrypt legacy masih sah utk rehash)
    async with db.pool().connection() as conn:
        cur = await conn.execute("SELECT password_hash FROM users WHERE username='qa'")
        row = await cur.fetchone()
    ph = row["password_hash"] if row else ""
    rec(area, "password_adaptive_hash", ph.startswith("$argon2") or ph.startswith("$2"),
        f"prefix={ph[:9]} (Argon2id; bcrypt legacy direhash saat login)")

    # order rate limit per menit (ambang diturunkan agar 12 order memicu 422)
    c = await fresh_client("qarate")
    try:
        await settings_set("max_orders_per_min", 5)
        rejected = 0
        for _ in range(12):
            market.update_tick("XAUUSD", 1999.85, 2000.15)
            r = await c.post("/orders", json={"symbol": "XAUUSD", "side": "BUY", "volume": 0.01, "sl": 1998.0, "tp": 2005.0}, headers={"x-csrf-token": await csrf(c)})
            if r.status_code == 422 and any("rate" in x for x in r.json().get("rejected_reasons", [])):
                rejected += 1
        rec(area, "orders_per_minute_limit", rejected >= 1, f"{rejected}/12 ditolak rate limit")
    finally:
        await settings_set("max_orders_per_min", 60)
        await c.aclose()


async def main() -> int:
    await db.init_pool()
    await db.apply_schema()
    await db.seed_defaults()
    try:
        await wait_order_window(15)
        await clean_slate()
        await disconnect_10x()
        await wait_order_window(15)  # order disconnect masih dalam window 60s
        await clean_slate()
        await mismatch_killswitch()
        await kill_switch_tests()
        await clean_slate()
        await security()
    finally:
        await db.close_pool()
    fails = [r for r in RESULTS if r["ok"] is False]
    devs = [r for r in RESULTS if r["ok"] is None]
    pathlib.Path("/home/tekka/fund2/docs/qa_p1b_results.json").write_text(json.dumps(RESULTS, indent=2))
    print(f"\nTOTAL {len(RESULTS)} checks: {len(RESULTS) - len(fails) - len(devs)} pass, {len(fails)} fail, {len(devs)} deviation")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
