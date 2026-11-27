"""Test migrasi skema v2.2 (PRD 19.3/19.4) — t_f2v22a21.

Verifikasi DoD: migrasi jalan bersih dari nol (dilakukan fixture _db_session
lewat db.apply_schema -> alembic upgrade head), semua tabel logical ada,
order_events menolak UPDATE/DELETE/TRUNCATE.
"""
from __future__ import annotations

import psycopg
import pytest

from app import db

# 23 tabel logical minimal PRD 19.3 + tabel operasional P1 (bridge_commands,
# paper_orders, paper_state, kill_switch_events) + katalog alembic.
PRD_19_3_TABLES = [
    "users", "sessions", "settings", "settings_audit",
    "orders", "order_events", "positions", "position_snapshots",
    "candles", "liquidity_samples", "signals",
    "strategies", "strategy_versions", "strategy_approvals",
    "backtest_runs", "paper_runs", "shadow_runs", "regime_observations",
    "risk_decisions", "system_events", "reconciliation_runs",
    "deployment_records", "research_reports",
]
OPERATIONAL_TABLES = [
    "bridge_commands", "paper_orders", "paper_state", "kill_switch_events",
    "alembic_version",
]


async def _table_names() -> set[str]:
    async with db.pool().connection() as conn:
        cur = await conn.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
        rows = await cur.fetchall()
    return {r["tablename"] for r in rows}


async def test_all_prd_19_3_tables_exist():
    names = await _table_names()
    missing = [t for t in PRD_19_3_TABLES if t not in names]
    assert not missing, f"tabel PRD 19.3 hilang: {missing}"


async def test_operational_tables_exist():
    names = await _table_names()
    missing = [t for t in OPERATIONAL_TABLES if t not in names]
    assert not missing, f"tabel operasional hilang: {missing}"


async def test_alembic_version_at_head():
    """Head aktual dibaca dari direktori alembic/versions (bukan hardcoded):
    test ini pernah stale saat migrasi d004/e005 ditambahkan worker lain."""
    import re
    from pathlib import Path

    versions_dir = Path(__file__).resolve().parent.parent / "alembic" / "versions"
    revs = {}
    for f in versions_dir.glob("*.py"):
        text = f.read_text()
        m = re.search(r'^revision\s*=\s*"(\w+)"', text, re.M)
        d = re.search(r'^down_revision\s*=\s*("(\w+)"|None)', text, re.M)
        if m:
            revs[m.group(1)] = d.group(2) if d and d.group(2) else None
    children = {d for d in revs.values() if d}
    heads = sorted(set(revs) - children)
    assert len(heads) == 1, f"head alembic harus tunggal, dapat: {heads}"

    async with db.pool().connection() as conn:
        cur = await conn.execute("SELECT version_num FROM alembic_version")
        row = await cur.fetchone()
    assert row is not None
    assert row["version_num"] == heads[0]


async def test_candles_and_liquidity_samples_partitioned():
    async with db.pool().connection() as conn:
        cur = await conn.execute(
            """
            SELECT c.relname
            FROM pg_class c JOIN pg_partitioned_table pt ON pt.partrelid = c.oid
            WHERE c.relnamespace = 'public'::regnamespace
            """
        )
        rows = await cur.fetchall()
    partitioned = {r["relname"] for r in rows}
    assert "candles" in partitioned
    assert "liquidity_samples" in partitioned


async def _insert_open_order() -> object:
    """Order + satu event RECEIVED; dipakai ulang karena rollback uji trigger."""
    async with db.pool().connection() as conn:
        cur = await conn.execute(
            "INSERT INTO orders (symbol, side, volume) VALUES ('XAUUSD', 'BUY', 0.01) "
            "RETURNING id")
        order_id = (await cur.fetchone())["id"]
        await conn.execute(
            "INSERT INTO order_events (order_id, to_status) VALUES (%s, 'RECEIVED')",
            (order_id,))
    return order_id


async def test_order_events_insert_ok_update_delete_truncate_rejected():
    order_id = await _insert_open_order()

    # UPDATE ditolak (PRD 19.4)
    async with db.pool().connection() as conn:
        with pytest.raises(psycopg.errors.RaiseException, match="append-only"):
            await conn.execute(
                "UPDATE order_events SET to_status = 'FILLED' WHERE order_id = %s",
                (order_id,))

    # DELETE ditolak (PRD 19.4) — row-level trigger butuh baris yang ada
    async with db.pool().connection() as conn:
        with pytest.raises(psycopg.errors.RaiseException, match="append-only"):
            await conn.execute("DELETE FROM order_events WHERE order_id = %s", (order_id,))

    # TRUNCATE ditolak (ledger tidak boleh dibuang massal)
    async with db.pool().connection() as conn:
        with pytest.raises(psycopg.errors.RaiseException, match="append-only"):
            await conn.execute("TRUNCATE order_events")

    # INSERT tetap boleh (append-only = boleh tambah)
    async with db.pool().connection() as conn:
        cur = await conn.execute(
            "INSERT INTO order_events (order_id, from_status, to_status) "
            "VALUES (%s, 'RECEIVED', 'VALIDATED') RETURNING id", (order_id,))
        assert (await cur.fetchone())["id"]


async def test_settings_changes_audited():
    await db.set_setting("max_spread", 0.42)
    async with db.pool().connection() as conn:
        cur = await conn.execute(
            "SELECT key, new_value FROM settings_audit WHERE key = 'max_spread' "
            "ORDER BY id DESC LIMIT 1")
        row = await cur.fetchone()
    assert row is not None
    assert float(row["new_value"]) == 0.42


async def test_strategy_versions_immutable_once_final():
    # Blok 1: buat strategi + versi DRAFT, edit boleh (commit)
    async with db.pool().connection() as conn:
        await conn.execute(
            "INSERT INTO strategies (strategy_id, name) VALUES ('t-strat', 'Test')")
        cur = await conn.execute(
            "INSERT INTO strategy_versions (strategy_id, version, status) "
            "VALUES ('t-strat', '1.0.0', 'DRAFT') RETURNING id")
        vid = (await cur.fetchone())["id"]
        await conn.execute(
            "UPDATE strategy_versions SET change_reason = 'x' WHERE id = %s", (vid,))

    # Blok 2: finalisasi APPROVED (commit)
    async with db.pool().connection() as conn:
        await conn.execute("UPDATE strategy_versions SET status = 'APPROVED' WHERE id = %s",
                           (vid,))

    # Blok 3: UPDATE versi final ditolak (PRD 11.1)
    async with db.pool().connection() as conn:
        with pytest.raises(psycopg.errors.RaiseException, match="immutable"):
            await conn.execute(
                "UPDATE strategy_versions SET params = '{\"a\": 1}' WHERE id = %s", (vid,))

    # Blok 4: DELETE versi final juga ditolak
    async with db.pool().connection() as conn:
        with pytest.raises(psycopg.errors.RaiseException, match="immutable"):
            await conn.execute("DELETE FROM strategy_versions WHERE id = %s", (vid,))


async def test_strategy_approvals_append_only():
    async with db.pool().connection() as conn:
        await conn.execute(
            "INSERT INTO strategies (strategy_id, name) VALUES ('t-strat2', 'Test 2')")
        cur = await conn.execute(
            "INSERT INTO strategy_versions (strategy_id, version) "
            "VALUES ('t-strat2', '1.0.0') RETURNING id")
        vid = (await cur.fetchone())["id"]
        cur = await conn.execute(
            "INSERT INTO strategy_approvals (strategy_version_id, stage, decision, reviewer) "
            "VALUES (%s, 'BACKTEST_REVIEW', 'APPROVED', 'qa') RETURNING id", (vid,))
        aid = (await cur.fetchone())["id"]
        with pytest.raises(psycopg.errors.RaiseException, match="append-only"):
            await conn.execute(
                "UPDATE strategy_approvals SET decision = 'REJECTED' WHERE id = %s", (aid,))
