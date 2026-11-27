"""AUDIT-F2 (t_7c070c31): kill-switch anti-flapping + release owner-only.

Bukti insiden (live kill_switch_events, 25 Nov 2026 18:07-18:21 WIB):
  34 ACTIVATE / 33 RELEASE bergantian tiap ~2 menit. ACTIVATE dari
  `auto:daily_drawdown_risk_gate` (mode GLOBAL_HALT hardcode), RELEASE dari
  source `kanban:t_baeb3ce4` actor `svc-qa-driver` (driver QA). Setiap siklus
  mengirim alert Telegram ke owner.

Kontrak yang diuji di sini:
1. release() menolak source `kanban:`/`auto:` dan actor `svc-*`/`agent*`
   (ReleaseForbidden); route /kill-switch/release hanya admin + 2FA + source
   dashboard (role qa diuji di test_agent_role.py).
2. Aktivasi idempotent: mode+reason sama -> tidak ada event baru (tidak ada
   alert ulang).
3. Flapping guard: ACTIVATE/RELEASE berulang untuk trigger+mode yang sama di
   dalam jendela dedupe hanya di-alert sekali (yang pertama tetap terkirim).
4. Satu mode untuk daily drawdown: risk gate dan evaluator trigger sama-sama
   membaca kill_switch_triggers.modes.daily_drawdown.
"""
from __future__ import annotations

import pytest

from app import alerts, db, kill_switch

START = 10000.0
_GAP = "auto:daily_drawdown_risk_gate"


async def _rows(sql: str, params: tuple = ()):
    async with db.pool().connection() as conn:
        cur = await conn.execute(sql, params)
        return await cur.fetchall()


async def _actions() -> list[str]:
    return [r["action"] for r in await _rows("SELECT action FROM kill_switch_events ORDER BY id")]


async def _event_count(action: str | None = None) -> int:
    if action:
        rows = await _rows(
            "SELECT count(*) AS n FROM kill_switch_events WHERE action = %s", (action,))
    else:
        rows = await _rows("SELECT count(*) AS n FROM kill_switch_events")
    return int(rows[0]["n"])


# ------------------------------------------------------------ 1. release guard

@pytest.mark.parametrize(
    "source,actor",
    [
        ("kanban:t_baeb3ce4", "owner"),
        ("kanban:t_f2p5a1", "svc-qa-driver"),
        ("auto:daily_drawdown_risk_gate", "auto"),
        ("dashboard", "svc-qa-driver"),
        ("dashboard", "agent-llm"),
        ("dashboard", "auto"),
    ],
)
async def test_release_ditolak_untuk_worker_kanban_dan_akun_service(client, source, actor):
    """Driver QA/worker kanban/service tidak bisa me-release (raise, state utuh)."""
    await kill_switch.activate("STOP_NEW_ORDERS", reason="uji guard",
                               source="test", actor="tester")

    with pytest.raises(kill_switch.ReleaseForbidden):
        await kill_switch.release(checklist_ack=True, source=source, actor=actor)

    assert (await kill_switch.get_state())["active"] is True
    assert "RELEASE" not in await _actions()


async def test_release_dashboard_owner_tetap_boleh(client):
    """Regresi: jalur owner (dashboard + actor owner) tetap bisa me-release."""
    await kill_switch.activate("STOP_NEW_ORDERS", reason="uji", source="test",
                               actor="tester")
    state = await kill_switch.release(checklist_ack=True, source="dashboard",
                                      actor="owner")
    assert state["active"] is False
    assert (await kill_switch.get_state())["active"] is False
    assert "RELEASE" in await _actions()


async def test_route_release_menolak_source_kanban(client_2fa):
    """Source dari body request tidak bisa dipakai menandai event worker."""
    await kill_switch.activate("STOP_NEW_ORDERS", reason="uji", source="test",
                               actor="tester")
    resp = await client_2fa.post(
        "/kill-switch/release",
        json={"checklist_ack": True, "source": "kanban:t_baeb3ce4"},
    )
    assert resp.status_code == 403, resp.text
    assert (await kill_switch.get_state())["active"] is True


async def test_route_release_dashboard_admin_2fa_berhasil(client_2fa):
    await kill_switch.activate("STOP_NEW_ORDERS", reason="uji", source="test",
                               actor="tester")
    resp = await client_2fa.post("/kill-switch/release", json={"checklist_ack": True})
    assert resp.status_code == 200, resp.text
    assert resp.json()["state"]["active"] is False
    row = (await _rows(
        "SELECT source, actor FROM kill_switch_events WHERE action = 'RELEASE' "
        "ORDER BY id DESC LIMIT 1"))[0]
    assert row["source"] == "dashboard"
    assert row["actor"] == "tester"


# -------------------------------------------------------- 2. aktivasi idempotent

async def test_aktivasi_idempotent_tidak_menulis_event_berulang(client):
    """Mode+reason sama: satu event, activated_at tidak berubah (tanpa alert ulang)."""
    first = await kill_switch.activate(
        "GLOBAL_HALT", reason="drawdown harian 10.42% >= 10.0%", source=_GAP, actor="auto")
    second = await kill_switch.activate(
        "GLOBAL_HALT", reason="drawdown harian 10.42% >= 10.0%", source=_GAP, actor="auto")
    third = await kill_switch.activate(
        "GLOBAL_HALT", reason="drawdown harian 10.51% >= 10.0%", source=_GAP, actor="auto")

    assert second["activated_at"] == first["activated_at"]
    assert third["activated_at"] == first["activated_at"]
    assert await _event_count("ACTIVATE") == 1
    assert await _actions() == ["ACTIVATE"]


async def test_aktivasi_mode_lebih_berat_tetap_eskalasi_sekali(client):
    await kill_switch.activate("STOP_NEW_ORDERS", reason="a", source=_GAP, actor="auto")
    await kill_switch.activate("GLOBAL_HALT", reason="b", source=_GAP, actor="auto")
    await kill_switch.activate("GLOBAL_HALT", reason="b", source=_GAP, actor="auto")
    assert await _actions() == ["ACTIVATE", "ESCALATE"]


# --------------------------------------------------------- 3. flapping guard

async def _insert_event(conn, action: str, mode: str, *, source: str, actor: str,
                        reason: str) -> None:
    await kill_switch.record_event(conn, action, mode, source=source, actor=actor,
                                   reason=reason)


async def test_flapping_guard_alert_hanya_sekali_per_siklus(client):
    """3 siklus ACTIVATE/RELEASE identik -> 2 alert (satu per action), bukan 6."""
    async with db.pool().connection() as conn:
        for i in range(3):
            await _insert_event(conn, "ACTIVATE", "GLOBAL_HALT", source=_GAP,
                                actor="auto", reason=f"drawdown harian {10 + i}%")
            await _insert_event(conn, "RELEASE", "GLOBAL_HALT", source="dashboard",
                                actor="owner", reason="release owner")
    new_last, texts = await alerts.ks_poll_once(0)
    assert new_last > 0
    assert len(texts) == 2, texts
    assert "KILL-SWITCH AKTIF" in texts[0]
    assert "NONAKTIF" in texts[1]


async def test_flapping_guard_bisa_dimatikan_dan_eskalasi_selalu_dikirim(client, monkeypatch):
    """KS_ALERT_DEDUPE_S=0 -> semua dikirim; ESCALATE tidak pernah diredam."""
    monkeypatch.setattr(alerts, "KS_ALERT_DEDUPE_S", 0)
    async with db.pool().connection() as conn:
        for _ in range(2):
            await _insert_event(conn, "ACTIVATE", "STOP_NEW_ORDERS", source=_GAP,
                                actor="auto", reason="x")
            await _insert_event(conn, "ESCALATE", "GLOBAL_HALT", source=_GAP,
                                actor="auto", reason="y")
    _, texts = await alerts.ks_poll_once(0)
    assert len(texts) == 4, texts


# ------------------------------------- 4. satu mode untuk daily drawdown (A6)

@pytest.fixture
async def _f2_env(_clean_db):
    await db.set_setting("daily_start_balance", START)
    await db.set_setting("max_tick_age_s", 3.0)
    await db.set_setting("kill_switch_triggers", {
        "daily_drawdown_pct": 3.0,
        "modes": {"daily_drawdown": "STOP_NEW_ORDERS"},
    })
    yield


_TICKET = [7700]


async def _seed_daily_loss(profit: float) -> None:
    _TICKET[0] += 1
    async with db.pool().connection() as conn:
        await conn.execute(
            "INSERT INTO positions (ticket, symbol, side, volume, open_price, "
            "close_price, profit, status, close_time) "
            "VALUES (%s, 'XAUUSD', 'BUY', 0.01, 2000, 1990, %s, 'CLOSED', now())",
            (_TICKET[0], profit),
        )


async def _csrf(client) -> str:
    return (await client.get("/auth/me")).json()["csrf_token"]


async def test_risk_gate_pakai_mode_dari_settings(_f2_env, client, tick_2000):
    """Risk gate memakai modes.daily_drawdown, bukan hardcode GLOBAL_HALT."""
    for _ in range(4):  # -400 USD = 4% dari saldo awal 10.000
        await _seed_daily_loss(-100.0)

    resp = await client.post(
        "/orders",
        json={"symbol": "XAUUSD", "side": "BUY", "volume": 0.1, "sl": 1998.0,
              "tp": 2010.0, "strategy": "manual"},
        headers={"x-csrf-token": await _csrf(client)},
    )
    assert resp.status_code == 422, resp.text

    state = await kill_switch.get_state()
    assert state["active"] is True
    assert state["mode"] == "STOP_NEW_ORDERS"   # dari settings, bukan GLOBAL_HALT
    assert state["source"] == _GAP

    row = (await _rows(
        "SELECT mode, source FROM kill_switch_events WHERE action = 'ACTIVATE' "
        "ORDER BY id DESC LIMIT 1"))[0]
    assert row["mode"] == "STOP_NEW_ORDERS"
    assert row["source"] == _GAP


async def test_evaluator_dan_risk_gate_memakai_mode_yang_sama(_f2_env):
    """Evaluator trigger memakai mode yang sama dengan trigger_mode() risk gate."""
    for _ in range(4):
        await _seed_daily_loss(-100.0)

    assert await kill_switch.trigger_mode("daily_drawdown") == "STOP_NEW_ORDERS"
    fired = await kill_switch.run_trigger_checks()
    daily = [f for f in fired if f["trigger"] == "daily_drawdown"]
    assert daily and daily[0]["mode"] == "STOP_NEW_ORDERS"

    state = await kill_switch.get_state()
    assert state["mode"] == "STOP_NEW_ORDERS"
