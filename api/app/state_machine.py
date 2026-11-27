"""Order state machine. Every transition appends an immutable row to order_events."""
from __future__ import annotations

from psycopg.types.json import Jsonb

import json

from psycopg import AsyncConnection

ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "RECEIVED": {"RISK_PASS", "FAILED"},
    "RISK_PASS": {"SENT"},
    "SENT": {"FILLED", "FAILED", "STUCK"},
    "STUCK": {"FILLED", "FAILED", "FILLED_THEN_CLOSED", "RECONCILED"},
    # Reconciler refinements (PRD 5.8): FILLED order whose position closed with
    # a closing deal -> FILLED_THEN_CLOSED; vanished without a deal -> FAILED.
    "FILLED": {"FILLED_THEN_CLOSED", "FAILED"},
    "FILLED_THEN_CLOSED": set(),
    # Orphan lifecycle (PRD 5.8): broker position without DB row -> adopted;
    # later seen closed with a deal -> ORPHAN_CLOSED.
    "ORPHAN_ADOPTED": {"ORPHAN_CLOSED", "FAILED"},
    "ORPHAN_CLOSED": set(),
    "RECONCILED": set(),
    "FAILED": set(),
}

TERMINAL_STATUSES = {"FILLED", "FAILED", "FILLED_THEN_CLOSED", "ORPHAN_CLOSED", "RECONCILED"}

# Kolom `orders` yang boleh ditulis lewat transition(set_fields=...). Daftar
# tertutup: nama kolom masuk ke string SQL, jadi input dari luar tidak boleh
# menambah kolom sendiri.
SET_FIELD_COLUMNS = frozenset({
    "ticket", "price_filled", "fail_reason", "fail_detail", "sent_at",
})

# Race T4 (PRD 5.8): order OPEN induk yang posisinya ditutup order CLOSE
# FILLED. Status induk -> status terminal penutupan yang sah menurut
# ALLOWED_TRANSITIONS (dipakai /bridge/result dan sweep worker).
CLOSE_OWNER_TARGETS: dict[str, str] = {
    "FILLED": "FILLED_THEN_CLOSED",
    "STUCK": "FILLED_THEN_CLOSED",
    "ORPHAN_ADOPTED": "ORPHAN_CLOSED",
}


class InvalidTransition(Exception):
    pass


async def fetchone(conn: AsyncConnection, sql: str, params: tuple = ()):
    cur = await conn.execute(sql, params)
    return await cur.fetchone()


async def fetchall(conn: AsyncConnection, sql: str, params: tuple = ()):
    cur = await conn.execute(sql, params)
    return await cur.fetchall()


async def transition(
    conn: AsyncConnection,
    order_id: str,
    to_status: str,
    payload: dict | None = None,
    set_fields: dict | None = None,
    jsonb_fields: tuple[str, ...] = (),
) -> dict:
    """Lock the order row, validate the transition, update orders and append order_events.

    Must be called inside a transaction (caller owns commit/rollback).
    """
    # Nama kolom diinterpolasi ke SQL, jadi WAJIB dari whitelist. Pemanggil
    # saat ini memakai konstanta, tetapi whitelist menutup jalur injeksi bila
    # kelak ada pemanggil baru yang meneruskan key dari input.
    bad_fields = sorted(set(set_fields or {}) - SET_FIELD_COLUMNS)
    if bad_fields:
        raise InvalidTransition(
            f"kolom set_fields tidak diizinkan: {', '.join(bad_fields)}")
    row = await fetchone(conn, "SELECT status FROM orders WHERE id = %s FOR UPDATE", (order_id,))
    if row is None:
        raise InvalidTransition(f"order {order_id} not found")
    from_status = row["status"]
    if to_status not in ALLOWED_TRANSITIONS.get(from_status, set()):
        raise InvalidTransition(f"illegal transition {from_status} -> {to_status}")

    assignments = ["status = %s", "updated_at = now()"]
    values: list = [to_status]
    if to_status in TERMINAL_STATUSES:
        assignments.append("resolved_at = now()")
    for field, value in (set_fields or {}).items():
        # t_afd7fe4e: kolom JSONB (mis. orders.fail_detail) butuh adapter
        # Jsonb + cast eksplisit; psycopg tidak bisa mengadaptasi dict mentah.
        if field in jsonb_fields:
            value = Jsonb(value)
            assignments.append(f"{field} = %s::jsonb")
        else:
            assignments.append(f"{field} = %s")
        values.append(value)
    values.append(order_id)
    await conn.execute(
        f"UPDATE orders SET {', '.join(assignments)} WHERE id = %s", tuple(values)
    )
    await conn.execute(
        """
        INSERT INTO order_events (order_id, from_status, to_status, payload)
        VALUES (%s, %s, %s, %s)
        """,
        (order_id, from_status, to_status, json.dumps(payload or {})),
    )
    return {"order_id": order_id, "from": from_status, "to": to_status}


async def record_event(
    conn: AsyncConnection,
    order_id: str,
    event: str,
    payload: dict | None = None,
) -> None:
    """Append a non-transition reconciler step to order_events (PRD 5.8 point 5).

    from_status == to_status == the order's current status; the event name and
    details live in the payload. Append-only, no order status change.
    """
    row = await fetchone(conn, "SELECT status FROM orders WHERE id = %s", (order_id,))
    status = row["status"] if row else None
    body = {"event": event, **(payload or {})}
    await conn.execute(
        """
        INSERT INTO order_events (order_id, from_status, to_status, payload)
        VALUES (%s, %s, %s, %s)
        """,
        (order_id, status, status, json.dumps(body)),
    )
