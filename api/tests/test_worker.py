"""Worker loop: claim RISK_PASS -> SENT, reconciler SENT > 60s -> STUCK, sweep T4."""
import json
from datetime import datetime, timedelta, timezone

import pytest

from app import db
from app import worker as worker_module
from app.worker import (
    claim_one_order,
    reconcile_filled_closed,
    reconcile_stuck,
    resolve_stuck_orders,
)
from app.state_machine import fetchall, fetchone, transition


@pytest.fixture
async def owner_alerts(monkeypatch):
    """Rekam panggilan notify_owner di worker (guard TELEGRAM_ALERTS_OFF tetap)."""
    calls: list[str] = []

    async def fake_notify(message: str) -> None:
        calls.append(message)

    monkeypatch.setattr(worker_module, "notify_owner", fake_notify)
    return calls


PATHS: dict[str, list[str]] = {
    "RECEIVED": [],
    "RISK_PASS": ["RISK_PASS"],
    "SENT": ["RISK_PASS", "SENT"],
    "STUCK": ["RISK_PASS", "SENT", "STUCK"],
    "FILLED": ["RISK_PASS", "SENT", "FILLED"],
    "FAILED": ["FAILED"],
}


async def _insert_order(status: str, sent_age_s: int | None = None) -> dict:
    """Insert an order walked along the real event path to `status`."""
    from datetime import datetime, timedelta, timezone

    async with db.pool().connection() as conn:
        async with conn.transaction():
            row = await fetchone(
                conn,
                """
                INSERT INTO orders (symbol, side, volume, sl, tp, status)
                VALUES ('XAUUSD', 'BUY', 0.10, 1998, 2005, 'RECEIVED') RETURNING *
                """,
            )
            await conn.execute(
                "INSERT INTO order_events (order_id, from_status, to_status) "
                "VALUES (%s, NULL, 'RECEIVED')",
                (row["id"],),
            )
            for step in PATHS[status]:
                if step == "SENT" and sent_age_s is not None:
                    await transition(
                        conn, row["id"], step,
                        set_fields={"sent_at": datetime.now(timezone.utc)
                                    - timedelta(seconds=sent_age_s)},
                    )
                else:
                    await transition(conn, row["id"], step)
            return await fetchone(conn, "SELECT * FROM orders WHERE id = %s", (row["id"],))


async def _events(order_id):
    async with db.pool().connection() as conn:
        return await fetchall(
            conn,
            "SELECT to_status FROM order_events WHERE order_id = %s ORDER BY id",
            (order_id,),
        )


async def test_claim_moves_risk_pass_to_sent():
    await _insert_order("RISK_PASS")

    claimed = await claim_one_order()
    assert claimed is not None
    assert claimed["status"] == "RISK_PASS"  # pre-claim snapshot

    async with db.pool().connection() as conn:
        after = await fetchone(conn, "SELECT status, sent_at FROM orders WHERE id = %s",
                               (claimed["id"],))
    assert after["status"] == "SENT"
    assert after["sent_at"] is not None
    events = await _events(claimed["id"])
    assert [e["to_status"] for e in events] == ["RECEIVED", "RISK_PASS", "SENT"]


async def test_claim_returns_none_when_idle():
    assert await claim_one_order() is None


async def test_reconciler_stucks_old_sent_orders():
    await _insert_order("SENT", sent_age_s=120)
    stuck = await reconcile_stuck()
    assert len(stuck) == 1
    events = await _events(stuck[0]["id"])
    assert [e["to_status"] for e in events] == ["RECEIVED", "RISK_PASS", "SENT", "STUCK"]


async def test_reconciler_leaves_fresh_sent_orders():
    await _insert_order("SENT", sent_age_s=5)
    stuck = await reconcile_stuck()
    assert stuck == []


async def test_reconciler_ignores_terminal_orders():
    await _insert_order("FILLED", sent_age_s=120)
    stuck = await reconcile_stuck()
    assert stuck == []


# ── Sweep T4: order OPEN yang posisinya sudah CLOSED di DB ──


async def _seed_action_order(ticket: int, status: str = "FILLED") -> dict:
    """Order action='OPEN' dengan ticket (seperti hasil fill / adopsi orphan)."""
    async with db.pool().connection() as conn:
        async with conn.transaction():
            row = await fetchone(
                conn,
                """
                INSERT INTO orders (symbol, side, volume, status, fail_reason, ticket,
                                    price_filled, action, sent_at)
                VALUES ('XAUUSD', 'BUY', 0.10, %s,
                        CASE WHEN %s = 'FAILED' THEN 'qa-fixture' ELSE NULL END,
                        %s, 2000.0, 'OPEN', now())
                RETURNING *
                """,
                (status, status, ticket),
            )
            await conn.execute(
                "INSERT INTO order_events (order_id, from_status, to_status) "
                "VALUES (%s, 'RECEIVED', %s)",
                (row["id"], status),
            )
            return row


async def _seed_position(ticket: int, order_id: str | None, status: str = "CLOSED",
                         close_time: datetime | str | None = "now",
                         close_price: float = 2005.0, profit: float = 5.0) -> dict:
    if close_time == "now":
        close_time = datetime.now(timezone.utc)
    async with db.pool().connection() as conn:
        return await fetchone(
            conn,
            """
            INSERT INTO positions (ticket, order_id, symbol, side, volume, open_price,
                                   close_price, close_time, profit, status)
            VALUES (%s, %s, 'XAUUSD', 'BUY', 0.10, 2000.0, %s, %s, %s, %s)
            RETURNING *
            """,
            (ticket, order_id, close_price if status == "CLOSED" else None,
             close_time if status == "CLOSED" else None, profit, status),
        )


async def _order_status(order_id) -> str:
    async with db.pool().connection() as conn:
        row = await fetchone(conn, "SELECT status FROM orders WHERE id = %s", (order_id,))
    return row["status"]


async def test_sweep_transitions_filled_order_with_closed_position():
    order = await _seed_action_order(5001, "FILLED")
    await _seed_position(5001, order_id=order["id"])

    swept = await reconcile_filled_closed()
    assert [s["order_id"] for s in swept] == [str(order["id"])]
    assert await _order_status(order["id"]) == "FILLED_THEN_CLOSED"
    events = await _events(order["id"])
    assert events[-1]["to_status"] == "FILLED_THEN_CLOSED"


async def test_sweep_payload_records_close_evidence():
    closed_at = datetime(2026, 11, 22, 6, 0, 24, tzinfo=timezone.utc)
    order = await _seed_action_order(5002, "FILLED")
    await _seed_position(5002, order_id=order["id"], close_time=closed_at,
                         close_price=60093.95, profit=-0.91)

    swept = await reconcile_filled_closed()
    assert len(swept) == 1
    async with db.pool().connection() as conn:
        ev = await fetchone(
            conn,
            "SELECT * FROM order_events WHERE order_id = %s ORDER BY id DESC LIMIT 1",
            (order["id"],),
        )
    assert ev["payload"]["source"] == "worker_reconciler"
    assert ev["payload"]["ticket"] == 5002
    assert float(ev["payload"]["close_price"]) == 60093.95
    assert float(ev["payload"]["profit"]) == -0.91
    # instan sama, representasi offset timezone sesi bisa berbeda
    assert datetime.fromisoformat(ev["payload"]["close_time"]) == closed_at
    assert "race result CLOSE" in ev["payload"]["reason"]


async def test_sweep_ticket_fallback_linkage():
    """Posisi tanpa order_id tapi ticket cocok -> tetap ditutup (kasus live)."""
    order = await _seed_action_order(5003, "FILLED")
    await _seed_position(5003, order_id=None)

    swept = await reconcile_filled_closed()
    assert [s["order_id"] for s in swept] == [str(order["id"])]


async def test_sweep_orphan_owner_goes_orphan_closed():
    order = await _seed_action_order(5004, "ORPHAN_ADOPTED")
    await _seed_position(5004, order_id=order["id"])

    swept = await reconcile_filled_closed()
    assert [s["order_id"] for s in swept] == [str(order["id"])]
    assert await _order_status(order["id"]) == "ORPHAN_CLOSED"


async def test_sweep_skips_failed_owner():
    """Order FAILED sudah terminal: tidak disentuh sweep."""
    order = await _seed_action_order(5005, "FAILED")
    await _seed_position(5005, order_id=order["id"])

    assert await reconcile_filled_closed() == []
    assert await _order_status(order["id"]) == "FAILED"


async def test_sweep_skips_position_without_close_time():
    """Posisi CLOSED tanpa close_time: tidak ada bukti penutupan -> tidak disentuh."""
    order = await _seed_action_order(5006, "FILLED")
    await _seed_position(5006, order_id=order["id"], close_time=None)

    assert await reconcile_filled_closed() == []
    assert await _order_status(order["id"]) == "FILLED"


async def test_sweep_skips_open_position():
    order = await _seed_action_order(5007, "FILLED")
    await _seed_position(5007, order_id=order["id"], status="OPEN")

    assert await reconcile_filled_closed() == []
    assert await _order_status(order["id"]) == "FILLED"


async def test_sweep_is_idempotent():
    order = await _seed_action_order(5008, "FILLED")
    await _seed_position(5008, order_id=order["id"])

    first = await reconcile_filled_closed()
    assert [s["order_id"] for s in first] == [str(order["id"])]
    assert await reconcile_filled_closed() == []
    assert await _order_status(order["id"]) == "FILLED_THEN_CLOSED"


# ── Auto-reconciler STUCK > STUCK_RESOLVE_AFTER_S (insiden 25 Nov 2026) ──


async def _insert_stuck_close(ticket: int | None, age_s: int = 1000,
                              received_payload: dict | None = None) -> dict:
    """Order action='CLOSE' yang sudah STUCK selama `age_s` detik."""
    payload = ({"source": "dashboard", "action": "CLOSE", "position_ticket": ticket}
               if received_payload is None else received_payload)
    async with db.pool().connection() as conn:
        async with conn.transaction():
            row = await fetchone(
                conn,
                """
                INSERT INTO orders (symbol, side, volume, sl, tp, status, ticket, action)
                VALUES ('XAUUSD', 'SELL', 0.10, NULL, NULL, 'RECEIVED', %s, 'CLOSE')
                RETURNING *
                """,
                (ticket,),
            )
            await conn.execute(
                """
                INSERT INTO order_events (order_id, from_status, to_status, payload)
                VALUES (%s, NULL, 'RECEIVED', %s)
                """,
                (row["id"], json.dumps(payload)),
            )
            for step in ("RISK_PASS", "SENT", "STUCK"):
                await transition(conn, row["id"], step)
            await conn.execute(
                "UPDATE orders SET updated_at = now() - (%s * interval '1 second') "
                "WHERE id = %s",
                (age_s, row["id"]),
            )
            return row


async def _insert_stuck_open(age_s: int = 1000) -> dict:
    """Order action='OPEN' (default) tanpa ticket yang sudah STUCK `age_s` detik."""
    async with db.pool().connection() as conn:
        async with conn.transaction():
            row = await fetchone(
                conn,
                """
                INSERT INTO orders (symbol, side, volume, sl, tp, status)
                VALUES ('XAUUSD', 'BUY', 0.10, 1998, 2005, 'RECEIVED')
                RETURNING *
                """,
            )
            await conn.execute(
                "INSERT INTO order_events (order_id, from_status, to_status) "
                "VALUES (%s, NULL, 'RECEIVED')",
                (row["id"],),
            )
            for step in ("RISK_PASS", "SENT", "STUCK"):
                await transition(conn, row["id"], step)
            await conn.execute(
                "UPDATE orders SET updated_at = now() - (%s * interval '1 second') "
                "WHERE id = %s",
                (age_s, row["id"]),
            )
            return row


async def _last_event(order_id) -> dict:
    async with db.pool().connection() as conn:
        return await fetchone(
            conn,
            "SELECT * FROM order_events WHERE order_id = %s ORDER BY id DESC LIMIT 1",
            (order_id,),
        )


async def test_stuck_close_with_closed_position_becomes_filled():
    """Kasus insiden: CLOSE STUCK, posisi target sudah CLOSED -> FILLED + bukti."""
    order = await _insert_stuck_close(6001)
    closed_at = datetime(2026, 11, 25, 3, 28, 5, tzinfo=timezone.utc)
    await _seed_position(6001, order_id=None, close_time=closed_at,
                         close_price=3552.58, profit=-1.35)

    resolved, alerts = await resolve_stuck_orders()

    assert [r["order_id"] for r in resolved] == [str(order["id"])]
    assert resolved[0]["status"] == "FILLED"
    assert resolved[0]["ticket"] == 6001
    assert alerts == []
    assert await _order_status(order["id"]) == "FILLED"
    ev = await _last_event(order["id"])
    assert ev["from_status"] == "STUCK" and ev["to_status"] == "FILLED"
    assert ev["payload"]["source"] == "auto:reconciler"
    assert ev["payload"]["ticket"] == 6001
    assert float(ev["payload"]["close_price"]) == 3552.58
    assert datetime.fromisoformat(ev["payload"]["close_time"]) == closed_at
    assert float(ev["payload"]["profit"]) == -1.35
    async with db.pool().connection() as conn:
        row = await fetchone(conn, "SELECT price_filled FROM orders WHERE id = %s",
                             (order["id"],))
    assert float(row["price_filled"]) == 3552.58


async def test_stuck_close_ticket_fallback_from_received_payload():
    """Kolom ticket NULL tapi payload RECEIVED membawa position_ticket."""
    order = await _insert_stuck_close(None, received_payload={
        "source": "dashboard", "action": "CLOSE", "position_ticket": 6002})
    await _seed_position(6002, order_id=None)

    resolved, alerts = await resolve_stuck_orders()

    assert [r["order_id"] for r in resolved] == [str(order["id"])]
    assert resolved[0]["status"] == "FILLED"
    assert resolved[0]["ticket"] == 6002
    assert alerts == []


async def test_stuck_close_with_open_position_fails_with_alert():
    """Posisi target masih OPEN -> FAILED + alert Telegram (perhatian manual)."""
    order = await _insert_stuck_close(6003)
    await _seed_position(6003, order_id=None, status="OPEN")

    resolved, alerts = await resolve_stuck_orders()

    assert [r["order_id"] for r in resolved] == [str(order["id"])]
    assert resolved[0]["status"] == "FAILED"
    assert await _order_status(order["id"]) == "FAILED"
    ev = await _last_event(order["id"])
    assert ev["payload"]["source"] == "auto:reconciler"
    assert ev["payload"]["reason"] == "no EA result, position still open"
    async with db.pool().connection() as conn:
        row = await fetchone(conn, "SELECT fail_reason FROM orders WHERE id = %s",
                             (order["id"],))
    # Fail reason kini terstruktur: <kode>: <pesan> (stage=<tahap>).
    assert row["fail_reason"].startswith("ea_no_result")
    assert "position still open" in row["fail_reason"]
    assert len(alerts) == 1
    assert "6003" in alerts[0]
    assert "perlu perhatian manual" in alerts[0]


async def test_stuck_close_without_position_row_fails_with_alert():
    """Posisi target tidak ada di DB -> FAILED + alert (jangan mengklaim FILLED)."""
    order = await _insert_stuck_close(6004)

    resolved, alerts = await resolve_stuck_orders()

    assert resolved[0]["status"] == "FAILED"
    assert await _order_status(order["id"]) == "FAILED"
    ev = await _last_event(order["id"])
    assert ev["payload"]["reason"] == "no EA result, target position not found in DB"
    assert len(alerts) == 1
    assert "6004" in alerts[0]


async def test_stuck_open_without_ticket_fails_with_alert():
    """OPEN STUCK tanpa ticket -> FAILED + alert (order tidak pernah dieksekusi)."""
    order = await _insert_stuck_open()

    resolved, alerts = await resolve_stuck_orders()

    assert [r["order_id"] for r in resolved] == [str(order["id"])]
    assert resolved[0]["status"] == "FAILED"
    assert resolved[0]["ticket"] is None
    assert await _order_status(order["id"]) == "FAILED"
    ev = await _last_event(order["id"])
    assert ev["payload"]["reason"] == "no EA result, order never executed"
    assert len(alerts) == 1
    assert "tidak pernah dieksekusi" in alerts[0]


async def test_fresh_stuck_orders_are_untouched():
    """STUCK yang belum lewat grace period tetap menunggu late /bridge/result."""
    close_order = await _insert_stuck_close(6005, age_s=60)
    open_order = await _insert_stuck_open(age_s=60)

    resolved, alerts = await resolve_stuck_orders()

    assert resolved == []
    assert alerts == []
    assert await _order_status(close_order["id"]) == "STUCK"
    assert await _order_status(open_order["id"]) == "STUCK"


async def test_open_stuck_with_ticket_is_left_for_late_result():
    """OPEN STUCK yang punya ticket dibiarkan (late result / sweep T4)."""
    async with db.pool().connection() as conn:
        async with conn.transaction():
            row = await fetchone(
                conn,
                """
                INSERT INTO orders (symbol, side, volume, sl, tp, status, ticket, action)
                VALUES ('XAUUSD', 'BUY', 0.10, 1998, 2005, 'RECEIVED', 6006, 'OPEN')
                RETURNING *
                """,
            )
            await conn.execute(
                "INSERT INTO order_events (order_id, from_status, to_status) "
                "VALUES (%s, NULL, 'RECEIVED')",
                (row["id"],),
            )
            for step in ("RISK_PASS", "SENT", "STUCK"):
                await transition(conn, row["id"], step)
            await conn.execute(
                "UPDATE orders SET updated_at = now() - interval '1000 seconds' "
                "WHERE id = %s", (row["id"],))

    resolved, alerts = await resolve_stuck_orders()

    assert resolved == []
    assert alerts == []
    assert await _order_status(row["id"]) == "STUCK"


async def test_resolve_stuck_is_idempotent():
    """Order terminal tidak disentuh lagi: pemanggilan kedua tidak melakukan apa-apa."""
    order = await _insert_stuck_close(6007)
    await _seed_position(6007, order_id=None)

    first, first_alerts = await resolve_stuck_orders()
    assert [r["order_id"] for r in first] == [str(order["id"])]
    second, second_alerts = await resolve_stuck_orders()
    assert second == []
    assert second_alerts == []
    assert await _order_status(order["id"]) == "FILLED"
