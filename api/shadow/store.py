"""Persistence for shadow runs (shadow_runs) + shadow signals (shadow_signals).

Shadow TIDAK PERNAH menulis ke orders / bridge_commands / paper_orders
(PRD 9.2): satu-satunya output adalah baris shadow_runs + shadow_signals +
signals (source='SHADOW', ditulis supervisor sandbox).
"""
from __future__ import annotations

import json
from datetime import datetime
from uuid import UUID

DEFAULT_STATE = {
    "sim_balance": 10000.0,   # SALDO SIMULASI, bukan realized P&L (PRD 9.2)
    "shadow_start_ts": None,
    "broker_offset_h": None,
    "position": None,
    "is_simulation": True,
}


def _json(value) -> str:
    return json.dumps(value, default=str)


async def load_state(conn, key: str) -> dict:
    row = await conn.execute("SELECT value FROM paper_state WHERE key = %s", (key,))
    found = await row.fetchone()
    state = dict(DEFAULT_STATE)
    if found:
        state.update(found["value"] or {})
    state["is_simulation"] = True  # tidak boleh di-overwrite dari DB
    return state


async def save_state(conn, key: str, state: dict) -> None:
    await conn.execute(
        """
        INSERT INTO paper_state (key, value, updated_at) VALUES (%s, %s, now())
        ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = now()
        """,
        (key, _json(state)),
    )


async def ensure_run(conn, *, strategy_id: str, strategy_version: str, label: str,
                     symbol: str, timeframe: str, params_hash: str,
                     code_commit: str | None, config: dict) -> UUID:
    """Run row aktif utk (strategy_id, label); params/kode berubah -> run baru.

    Run lama pada label yang sama ditutup COMPLETED dengan note perubahan
    (PRD 9.2: beri label perubahan kode/parameter yang diuji).
    """
    row = await conn.execute(
        """
        SELECT run_id, config FROM shadow_runs
        WHERE strategy_id = %s AND label = %s AND status = 'RUNNING'
        ORDER BY created_at DESC LIMIT 1
        """,
        (strategy_id, label),
    )
    found = await row.fetchone()
    if found:
        cfg = found["config"] or {}
        if cfg.get("params_hash") == params_hash and cfg.get("code_commit") == code_commit:
            return UUID(str(found["run_id"]))
        await conn.execute(
            "UPDATE shadow_runs SET status = 'COMPLETED', completed_at = now(), "
            "note = %s WHERE run_id = %s",
            (f"spec changed: params_hash {cfg.get('params_hash')} -> {params_hash}, "
             f"code_commit {cfg.get('code_commit')} -> {code_commit}",
             found["run_id"]),
        )
    run_id = uuid4_hex()
    await conn.execute(
        """
        INSERT INTO shadow_runs (run_id, strategy_id, strategy_version, label,
                                 symbol, timeframe, status, config)
        VALUES (%s, %s, %s, %s, %s, %s, 'RUNNING', %s)
        """,
        (run_id, strategy_id, strategy_version, label, symbol, timeframe,
         _json({"params_hash": params_hash, "code_commit": code_commit, **config})),
    )
    return UUID(run_id)


def uuid4_hex() -> str:
    import uuid
    return uuid.uuid4().hex


async def insert_signal(conn, *, run_id: UUID, signal_ref: str | None,
                        strategy_id: str, strategy_version: str, label: str,
                        symbol: str, timeframe: str, ts: datetime,
                        ref_bid: float, ref_ask: float, spread: float,
                        spread_median_15m: float | None, regime_label: str | None,
                        regime_confidence: float | None, side: str | None,
                        volume: float | None, sl: float | None, tp: float | None,
                        reason: str, params_hash: str, code_commit: str | None,
                        sim_status: str, sim_fill_price: float | None,
                        sim_cost_usd: float | None, detail: dict) -> int:
    row = await conn.execute(
        """
        INSERT INTO shadow_signals
            (run_id, signal_ref, strategy_id, strategy_version, label, symbol,
             timeframe, ts, ref_bid, ref_ask, spread, spread_median_15m,
             regime_label, regime_confidence, side, volume, sl, tp, reason,
             params_hash, code_commit, is_simulation, sim_status,
             sim_fill_price, sim_cost_usd, sim_opened_at, detail)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                TRUE,%s,%s,%s,%s,%s)
        RETURNING id
        """,
        (run_id, signal_ref, strategy_id, strategy_version, label, symbol,
         timeframe, ts, ref_bid, ref_ask, spread, spread_median_15m,
         regime_label, regime_confidence, side, volume, sl, tp, reason,
         params_hash, code_commit, sim_status, sim_fill_price, sim_cost_usd,
         ts, _json(detail)),
    )
    return int((await row.fetchone())["id"])


async def record_exit(conn, signal_id: int, *, exit_price: float, pnl_usd: float,
                      cost_usd: float, exit_reason: str, closed_at: datetime) -> None:
    await conn.execute(
        """
        UPDATE shadow_signals
        SET sim_exit_price = %s, sim_pnl_usd = %s, sim_cost_usd = sim_cost_usd + %s,
            sim_exit_reason = %s, sim_closed_at = %s
        WHERE id = %s
        """,
        (exit_price, pnl_usd, cost_usd, exit_reason, closed_at, signal_id),
    )


async def run_stats(conn, run_id: UUID, since: datetime) -> dict:
    """Hitungan utk risk gate shadow + registry metrics (dari shadow_signals)."""
    row = await conn.execute(
        """
        SELECT count(*) FILTER (WHERE sim_status = 'FILLED') AS filled,
               count(*) FILTER (WHERE sim_status = 'REJECTED') AS rejected,
               count(*) FILTER (WHERE sim_status = 'REGIME_BLOCKED') AS regime_blocked,
               count(*) FILTER (WHERE sim_pnl_usd IS NOT NULL) AS closed,
               count(*) FILTER (WHERE sim_pnl_usd > 0) AS wins,
               count(*) FILTER (WHERE sim_pnl_usd < 0) AS losses,
               COALESCE(SUM(sim_pnl_usd) FILTER (WHERE sim_pnl_usd IS NOT NULL), 0) AS sim_pnl,
               count(*) FILTER (WHERE created_at >= %s) AS recent
        FROM shadow_signals WHERE run_id = %s
        """,
        (since, run_id),
    )
    found = await row.fetchone() or {}
    return {k: (int(found[k]) if found.get(k) is not None else 0)
            for k in ("filled", "rejected", "regime_blocked", "closed",
                      "wins", "losses", "recent")} | {
        "sim_pnl": float(found.get("sim_pnl") or 0.0)}


async def update_run_metrics(conn, run_id: UUID, stats: dict) -> None:
    await conn.execute(
        """
        UPDATE shadow_runs SET signal_count = %s, metrics = %s,
                               period_end = now()
        WHERE run_id = %s
        """,
        (stats["filled"] + stats["rejected"] + stats["regime_blocked"],
         _json(stats), run_id),
    )


async def daily_pnl(conn, run_id: UUID, day_start: datetime) -> float:
    row = await conn.execute(
        "SELECT COALESCE(SUM(sim_pnl_usd), 0) AS p FROM shadow_signals "
        "WHERE run_id = %s AND sim_closed_at >= %s",
        (run_id, day_start),
    )
    found = await row.fetchone()
    return float(found["p"] or 0.0)


async def orders_last_minute(conn, run_id: UUID, since: datetime) -> int:
    row = await conn.execute(
        "SELECT count(*) AS n FROM shadow_signals "
        "WHERE run_id = %s AND sim_status = 'FILLED' AND created_at >= %s",
        (run_id, since),
    )
    found = await row.fetchone()
    return int(found["n"] or 0)


async def recent_signals(conn, run_id: UUID, limit: int = 10):
    rows = await conn.execute(
        "SELECT * FROM shadow_signals WHERE run_id = %s "
        "ORDER BY created_at DESC LIMIT %s",
        (run_id, limit),
    )
    return await rows.fetchall()
