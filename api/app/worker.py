"""Background worker: 50 ms claim loop + SENT reconciler + T4 close sweep.

Claim:   RISK_PASS -> SENT        (SELECT ... FOR UPDATE SKIP LOCKED)
Reconcile: SENT older than 60 s without an EA result -> STUCK (late results can
still resolve STUCK -> FILLED/FAILED via the idempotent /bridge/result).
T4 sweep: orders OPEN whose position is already CLOSED -> FILLED_THEN_CLOSED /
ORPHAN_CLOSED (race result CLOSE vs snapshot reconciler; PRD 5.8).
STUCK resolver: orders STUCK longer than STUCK_RESOLVE_AFTER_S are reconciled
automatically (insiden 25 Nov 2026: satu order STUCK membuat portfolio gate
fail-closed selamanya karena dihitung sebagai leg pending tanpa SL).
"""
from __future__ import annotations

import asyncio
import sys
import time
from datetime import datetime, timezone

from . import config, db, fail_reason
from .sse import broadcaster
from .telegram_bot import notify_owner
from .state_machine import (
    ALLOWED_TRANSITIONS,
    CLOSE_OWNER_TARGETS,
    fetchall,
    fetchone,
    transition,
)


async def claim_one_order() -> dict | None:
    """Claim the oldest RISK_PASS order -> SENT. Returns the claimed order or None."""
    async with db.pool().connection() as conn:
        async with conn.transaction():
            order = await fetchone(
                conn,
                """
                SELECT * FROM orders
                WHERE status = 'RISK_PASS'
                ORDER BY created_at
                LIMIT 1
                FOR UPDATE SKIP LOCKED
                """,
            )
            if order is None:
                return None
            await transition(
                conn, order["id"], "SENT",
                {"by": "worker"},
                set_fields={"sent_at": datetime.now(timezone.utc)},
            )
            return order


async def reconcile_stuck() -> list[dict]:
    """Move SENT orders older than RECONCILE_AFTER_S to STUCK."""
    async with db.pool().connection() as conn:
        async with conn.transaction():
            rows = await fetchall(
                conn,
                """
                SELECT id FROM orders
                WHERE status = 'SENT'
                  AND sent_at < now() - (%s * interval '1 second')
                FOR UPDATE SKIP LOCKED
                """,
                (config.RECONCILE_AFTER_S,),
            )
            for row in rows:
                await transition(
                    conn, row["id"], "STUCK",
                    {"reason": f"no EA result within {config.RECONCILE_AFTER_S}s"},
                )
            return rows


async def _stuck_target_ticket(conn, order: dict) -> int | None:
    """Ticket posisi target order CLOSE: kolom ticket, fallback payload RECEIVED.

    Semua pembuat order CLOSE (flatten/kill-switch, llm_agent) mengisi kolom
    ticket saat INSERT; payload event RECEIVED membawa `position_ticket`
    (fallback untuk order lama/route lain yang hanya mencatat di event).
    """
    if order.get("ticket") is not None:
        return int(order["ticket"])
    row = await fetchone(
        conn,
        """
        SELECT payload FROM order_events
        WHERE order_id = %s AND to_status = 'RECEIVED'
        ORDER BY id
        LIMIT 1
        """,
        (order["id"],),
    )
    if row is None:
        return None
    payload = row["payload"] or {}
    for key in ("position_ticket", "ticket"):
        val = payload.get(key)
        if val is None:
            continue
        try:
            return int(val)
        except (TypeError, ValueError):
            continue
    return None


async def resolve_stuck_orders() -> tuple[list[dict], list[str]]:
    """Auto-reconciler order STUCK > STUCK_RESOLVE_AFTER_S (insiden 25 Nov 2026).

    Order STUCK tanpa hasil EA dihitung sebagai leg pending tanpa SL oleh
    portfolio gate (collect_legs) dan membuat SEMUA order baru ditolak
    selamanya. Setelah grace period, order STUCK diselesaikan berdasarkan
    bukti di tabel positions:

    - action=CLOSE, posisi target CLOSED -> FILLED (bukti close_price /
      close_time / profit, source 'auto:reconciler') - sama seperti
      rekonsiliasi manual QA pada insiden;
    - action=CLOSE, posisi target masih OPEN -> FAILED + alert Telegram
      (posisi tanpa close perlu perhatian manual);
    - action=CLOSE, posisi target tidak ada di DB -> FAILED + alert
      (tidak ada bukti eksekusi; jangan mengklaim FILLED);
    - action=OPEN tanpa ticket -> FAILED + alert (order tidak pernah
      dieksekusi). Order OPEN yang punya ticket dibiarkan untuk late
      /bridge/result atau sweep T4.

    Semua transisi lewat transition() (append-only order_events). Hasil EA
    yang datang terlambat tetap diterima /bridge/result sebagai duplicate
    ack (status terminal idempotent).
    """
    resolved: list[dict] = []
    alerts: list[str] = []
    async with db.pool().connection() as conn:
        async with conn.transaction():
            rows = await fetchall(
                conn,
                """
                SELECT * FROM orders
                WHERE status = 'STUCK'
                  AND updated_at < now() - (%s * interval '1 second')
                ORDER BY created_at
                FOR UPDATE SKIP LOCKED
                """,
                (config.STUCK_RESOLVE_AFTER_S,),
            )
            for order in rows:
                oid = str(order["id"])
                if order.get("action") == "CLOSE":
                    ticket = await _stuck_target_ticket(conn, order)
                    pos = None
                    if ticket is not None:
                        pos = await fetchone(
                            conn, "SELECT * FROM positions WHERE ticket = %s", (ticket,)
                        )
                    if pos is not None and pos["status"] == "CLOSED":
                        await transition(
                            conn, order["id"], "FILLED",
                            {
                                "source": "auto:reconciler",
                                "ticket": ticket,
                                "close_price": (float(pos["close_price"])
                                                if pos["close_price"] is not None
                                                else None),
                                "close_time": (pos["close_time"].isoformat()
                                               if pos["close_time"] else None),
                                "profit": (float(pos["profit"])
                                           if pos["profit"] is not None else None),
                                "reason": "no EA result, namun posisi target "
                                          "terkonfirmasi CLOSED di DB",
                            },
                            set_fields={"price_filled": pos["close_price"],
                                        "fail_reason": None},
                        )
                        resolved.append({"order_id": oid, "status": "FILLED",
                                         "ticket": ticket})
                        continue
                    if pos is not None:
                        reason = "no EA result, position still open"
                        alerts.append(
                            f"⚠️ STUCK CLOSE {oid[:8]} {order['symbol']} -> FAILED: "
                            f"posisi {ticket} masih OPEN tanpa hasil EA "
                            "(perlu perhatian manual).")
                    else:
                        reason = "no EA result, target position not found in DB"
                        alerts.append(
                            f"⚠️ STUCK CLOSE {oid[:8]} {order['symbol']} -> FAILED: "
                            f"posisi target {ticket} tidak ditemukan di DB "
                            "(perlu perhatian manual).")
                    fail = fail_reason.from_text(
                        reason, stage=fail_reason.STAGE_RECONCILER,
                        default_code="ea_no_result")
                    await transition(
                        conn, order["id"], "FAILED",
                        {"source": "auto:reconciler", "ticket": ticket,
                         "reason": reason, "fail": fail},
                        set_fields={"fail_reason": fail_reason.render(fail),
                                    "fail_detail": fail},
                        jsonb_fields=("fail_detail",),
                    )
                    resolved.append({"order_id": oid, "status": "FAILED",
                                     "ticket": ticket})
                else:
                    # action=OPEN: tanpa ticket berarti EA tidak pernah
                    # mengeksekusi (ticket hanya diisi oleh /bridge/result).
                    if order.get("ticket") is not None:
                        continue
                    reason = "no EA result, order never executed"
                    fail = fail_reason.from_text(
                        reason, stage=fail_reason.STAGE_RECONCILER,
                        default_code="ea_no_result")
                    await transition(
                        conn, order["id"], "FAILED",
                        {"source": "auto:reconciler", "ticket": None,
                         "reason": reason, "fail": fail},
                        set_fields={"fail_reason": fail_reason.render(fail),
                                    "fail_detail": fail},
                        jsonb_fields=("fail_detail",),
                    )
                    resolved.append({"order_id": oid, "status": "FAILED",
                                     "ticket": None})
                    alerts.append(
                        f"⚠️ STUCK OPEN {oid[:8]} {order['symbol']} "
                        f"{order['side']} {float(order['volume'])} lot -> FAILED: "
                        "order tidak pernah dieksekusi (tanpa ticket/result EA).")
    return resolved, alerts


async def reconcile_filled_closed() -> list[dict]:
    """Jaring pengaman race T4: order OPEN dengan posisi sudah CLOSED di DB.

    /bridge/result untuk order CLOSE yang FILLED menutup posisi di DB secara
    langsung; bila ia menang melawan snapshot reconciler, posisi tidak pernah
    terlihat "hilang" dan order OPEN induk stuck di FILLED selamanya. Sweep
    ini mencari order OPEN non-terminal yang posisinya sudah CLOSED (bukti:
    close_time terisi) dan mentransisikannya sesuai CLOSE_OWNER_TARGETS.
    Linkage induk mengikuti resolusi owner reconciler: positions.order_id,
    dengan fallback ticket. Juga memulihkan backlog lama sebelum fix result.
    Idempotent: order terminal tidak tersentuh.
    """
    async with db.pool().connection() as conn:
        async with conn.transaction():
            rows = await fetchall(
                conn,
                """
                SELECT o.id, o.status, o.ticket, p.close_price, p.close_time, p.profit
                FROM orders o
                JOIN positions p ON o.id = p.order_id OR o.ticket = p.ticket
                WHERE o.action = 'OPEN'
                  AND o.status = ANY(%s)
                  AND p.status = 'CLOSED'
                  AND p.close_time IS NOT NULL
                ORDER BY o.created_at
                """,
                (list(CLOSE_OWNER_TARGETS),),
            )
            transitioned: list[dict] = []
            seen: set[str] = set()
            for row in rows:
                if row["id"] in seen:  # OR-join bisa memproduksi duplikat
                    continue
                seen.add(row["id"])
                target = CLOSE_OWNER_TARGETS.get(row["status"])
                if target is None or target not in ALLOWED_TRANSITIONS.get(
                        row["status"], set()):
                    continue
                # Kunci ulang + cek status: /bridge/result atau reconciler
                # bisa menang race di antara SELECT dan transisi.
                cur = await fetchone(
                    conn, "SELECT status FROM orders WHERE id = %s FOR UPDATE", (row["id"],)
                )
                if cur is None or cur["status"] != row["status"]:
                    continue
                await transition(
                    conn, row["id"], target,
                    {
                        "source": "worker_reconciler",
                        "ticket": row["ticket"],
                        "close_price": (float(row["close_price"])
                                        if row["close_price"] is not None else None),
                        "close_time": (row["close_time"].isoformat()
                                       if row["close_time"] else None),
                        "profit": float(row["profit"]) if row["profit"] is not None else None,
                        "reason": "posisi sudah CLOSED di DB "
                                  "(race result CLOSE vs snapshot reconciler)",
                    },
                )
                transitioned.append({"order_id": str(row["id"]), "status": target,
                                     "ticket": row["ticket"]})
            return transitioned


async def worker_loop(stop: asyncio.Event) -> None:
    last_log = 0.0
    while not stop.is_set():
        try:
            order = await claim_one_order()
            if order is not None:
                broadcaster.publish(
                    {"type": "order", "order_id": str(order["id"]), "status": "SENT"}
                )
                continue  # drain the queue before sleeping
            stuck = await reconcile_stuck()
            if stuck:
                broadcaster.publish(
                    {"type": "reconcile", "stuck": [str(r["id"]) for r in stuck]}
                )
            resolved, alerts = await resolve_stuck_orders()
            for item in resolved:
                broadcaster.publish({"type": "order", **item})
            for message in alerts:
                await notify_owner(message)
            closed = await reconcile_filled_closed()
            for item in closed:
                broadcaster.publish({"type": "order", **item})
        except Exception as exc:  # keep the loop alive no matter what
            now = time.time()
            if now - last_log > 5:
                print(f"[worker] error: {exc}", file=sys.stderr, flush=True)
                last_log = now
        await asyncio.sleep(config.WORKER_INTERVAL_S)
