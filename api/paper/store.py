"""Persistence for the paper ledger (paper_orders) and runner state (paper_state)."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from uuid import UUID

DEFAULT_STATE = {
    "balance": 10000.0,
    "paper_start_ts": None,
    "days_observed": [],
    "broker_offset_h": None,
    "position": None,
}


def _json(value) -> str:
    return json.dumps(value, default=str)


async def load_state(conn, key: str) -> dict:
    row = await conn.execute("SELECT value FROM paper_state WHERE key = %s", (key,))
    found = await row.fetchone()
    state = dict(DEFAULT_STATE)
    if found:
        state.update(found["value"] or {})
    return state


async def save_state(conn, key: str, state: dict) -> None:
    await conn.execute(
        """
        INSERT INTO paper_state (key, value, updated_at) VALUES (%s, %s, now())
        ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = now()
        """,
        (key, _json(state)),
    )


async def open_position_row(conn, mode: str, strategy: str | None = None):
    """Latest OPEN paper order, optionally scoped to one strategy.

    Multi-strategy runners recover their own position only; a None strategy
    keeps the legacy behaviour (any OPEN row in the mode).
    """
    if strategy is None:
        row = await conn.execute(
            """
            SELECT * FROM paper_orders
            WHERE mode = %s AND status = 'OPEN'
            ORDER BY created_at DESC LIMIT 1
            """,
            (mode,),
        )
    else:
        row = await conn.execute(
            """
            SELECT * FROM paper_orders
            WHERE mode = %s AND status = 'OPEN' AND strategy = %s
            ORDER BY created_at DESC LIMIT 1
            """,
            (mode, strategy),
        )
    return await row.fetchone()


async def trades_today(conn, strategy: str, day_start: datetime, mode: str = "PAPER") -> int:
    row = await conn.execute(
        """
        SELECT count(*) AS n FROM paper_orders
        WHERE strategy = %s AND mode = %s AND status IN ('OPEN', 'CLOSED')
          AND created_at >= %s
        """,
        (strategy, mode, day_start),
    )
    found = await row.fetchone()
    return int(found["n"]) if found else 0


async def daily_pnl(conn, mode: str, day_start: datetime) -> float:
    row = await conn.execute(
        "SELECT COALESCE(SUM(profit), 0) AS p FROM paper_orders "
        "WHERE mode = %s AND status = 'CLOSED' AND closed_at >= %s",
        (mode, day_start),
    )
    found = await row.fetchone()
    return float(found["p"]) if found else 0.0


async def orders_since(conn, mode: str, since: datetime) -> int:
    row = await conn.execute(
        "SELECT count(*) AS n FROM paper_orders WHERE mode = %s AND created_at >= %s",
        (mode, since),
    )
    found = await row.fetchone()
    return int(found["n"]) if found else 0


async def insert_order(conn, *, mode: str, intent, entry_price: float,
                       risk_decision: dict, reason: str, opened_at: datetime) -> UUID:
    row = await conn.execute(
        """
        INSERT INTO paper_orders (mode, strategy, symbol, side, volume, sl, tp,
                                  status, risk_decision, entry_price, reason, opened_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, 'OPEN', %s, %s, %s, %s)
        RETURNING id
        """,
        (mode, intent.strategy, intent.symbol, intent.side, intent.volume,
         intent.sl, intent.tp, _json(risk_decision), entry_price, reason, opened_at),
    )
    return (await row.fetchone())["id"]


async def insert_rejected(conn, *, mode: str, intent, risk_decision: dict,
                          reason: str, at: datetime) -> None:
    await conn.execute(
        """
        INSERT INTO paper_orders (mode, strategy, symbol, side, volume, sl, tp,
                                  status, risk_decision, reason, created_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, 'REJECTED', %s, %s, %s)
        """,
        (mode, intent.strategy, intent.symbol, intent.side, intent.volume,
         intent.sl, intent.tp, _json(risk_decision), reason, at),
    )


async def close_order(conn, order_id, exit_price: float, profit: float,
                      reason: str, closed_at: datetime) -> None:
    await conn.execute(
        """
        UPDATE paper_orders
        SET status = 'CLOSED', exit_price = %s, profit = %s, reason = reason || ' | exit: ' || %s,
            closed_at = %s
        WHERE id = %s
        """,
        (exit_price, profit, reason, closed_at, order_id),
    )


async def recent_orders(conn, mode: str, limit: int = 20):
    rows = await conn.execute(
        "SELECT * FROM paper_orders WHERE mode = %s ORDER BY created_at DESC LIMIT %s",
        (mode, limit),
    )
    return await rows.fetchall()


def day_start_utc(now: datetime) -> datetime:
    return datetime(now.year, now.month, now.day, tzinfo=timezone.utc)
