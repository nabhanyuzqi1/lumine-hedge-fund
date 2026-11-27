"""State machine tests: legal/illegal transitions + event log appends."""
import pytest

from app import db
from app.state_machine import InvalidTransition, fetchone, transition


PATHS: dict[str, list[str]] = {
    "RECEIVED": [],
    "RISK_PASS": ["RISK_PASS"],
    "SENT": ["RISK_PASS", "SENT"],
    "STUCK": ["RISK_PASS", "SENT", "STUCK"],
    "FILLED": ["RISK_PASS", "SENT", "FILLED"],
    "FAILED": ["FAILED"],
}


async def _insert_order(status="RECEIVED", **kwargs) -> str:
    """Insert an order and walk it along the real event path to `status`."""
    async with db.pool().connection() as conn:
        async with conn.transaction():
            row = await fetchone(
                conn,
                """
                INSERT INTO orders (symbol, side, volume, sl, tp, status)
                VALUES ('XAUUSD', 'BUY', 0.10, 1998, 2005, 'RECEIVED') RETURNING id
                """,
            )
            await conn.execute(
                "INSERT INTO order_events (order_id, from_status, to_status) "
                "VALUES (%s, NULL, 'RECEIVED')",
                (row["id"],),
            )
            for step in PATHS[status]:
                await transition(conn, row["id"], step)
        return row["id"]


async def _events(order_id) -> list[dict]:
    async with db.pool().connection() as conn:
        cur = await conn.execute(
            "SELECT from_status, to_status FROM order_events WHERE order_id = %s ORDER BY id",
            (order_id,),
        )
        return await cur.fetchall()


async def test_valid_transition_appends_event():
    oid = await _insert_order("RECEIVED")
    async with db.pool().connection() as conn:
        async with conn.transaction():
            result = await transition(conn, oid, "RISK_PASS", {"risk": "pass"})
    assert result["from"] == "RECEIVED"
    assert result["to"] == "RISK_PASS"
    events = await _events(oid)
    assert events == [{"from_status": None, "to_status": "RECEIVED"},
                      {"from_status": "RECEIVED", "to_status": "RISK_PASS"}]


async def test_illegal_transition_rejected():
    oid = await _insert_order("RECEIVED")
    async with db.pool().connection() as conn:
        async with conn.transaction():
            with pytest.raises(InvalidTransition):
                await transition(conn, oid, "SENT")  # RECEIVED -> SENT is illegal
    events = await _events(oid)
    assert len(events) == 1  # nothing appended


async def test_terminal_state_locked():
    oid = await _insert_order("FILLED")
    async with db.pool().connection() as conn:
        async with conn.transaction():
            with pytest.raises(InvalidTransition):
                await transition(conn, oid, "SENT")


async def test_stuck_can_resolve_to_filled():
    oid = await _insert_order("STUCK")
    async with db.pool().connection() as conn:
        async with conn.transaction():
            await transition(conn, oid, "FILLED", {"source": "bridge-late"})


async def test_full_happy_path_transitions():
    oid = await _insert_order("RECEIVED")
    async with db.pool().connection() as conn:
        async with conn.transaction():
            await transition(conn, oid, "RISK_PASS")
            await transition(conn, oid, "SENT")
            await transition(conn, oid, "FILLED")
    events = await _events(oid)
    assert [e["to_status"] for e in events] == ["RECEIVED", "RISK_PASS", "SENT", "FILLED"]


async def test_unknown_order_raises():
    async with db.pool().connection() as conn:
        async with conn.transaction():
            with pytest.raises(InvalidTransition):
                await transition(conn, "00000000-0000-0000-0000-000000000000", "SENT")


async def test_transition_missing_order_rejected():
    """Branch order tidak ada di tabel -> InvalidTransition (bukan crash lain)."""
    async with db.pool().connection() as conn:
        async with conn.transaction():
            with pytest.raises(InvalidTransition, match="not found"):
                await transition(conn, "00000000-0000-0000-0000-000000000000",
                                 "RISK_PASS")
