"""Negative/isolation tests shadow strategy (PRD 9.2 + DoD t_f2v22a4).

DoD: "shadow tidak bisa kirim order (teruji negatif)". Tiga lapis bukti:

1. AST: modul shadow tidak meng-import jalur order (app.bridge, app.worker,
   kill-switch, routes, HTTP client) dan SQL-nya tidak menyentuh
   orders / bridge_commands / paper_orders.
2. Runtime E2E: iterasi shadow penuh dengan monkeypatch yang membuat setiap
   fungsi pengirim order melempar; iterasi tetap sukses mencatat sinyal dan
   count orders / bridge_commands / paper_orders tidak berubah (tripwire).
3. Ledger tripwire modul (OrderLedgerTripwire) mendeteksi perubahan count.
"""
from __future__ import annotations

import ast
import asyncio
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app import db, supervisor
from shadow import runner, store
from shadow.fill import FillModel
from shadow.loop import OrderLedgerTripwire
from shadow.specs import ShadowSpec

UTC = timezone.utc
NOW = datetime(2026, 11, 24, 9, 30, 30, tzinfo=UTC)
TICK = {"bid": 1999.85, "ask": 2000.15, "spread": 0.30, "ts_utc": NOW}
SHADOW_DIR = Path(runner.__file__).resolve().parent

INTENT = {
    "strategy_id": "london_breakout", "strategy_version": "1.0.0",
    "signal_id": "abc123", "client_order_id": "c" * 32, "symbol": "XAUUSD",
    "side": "BUY", "order_type": "MARKET", "volume": 0.04,
    "requested_price": None, "stop_loss": 1990.0, "take_profit": 2015.0,
    "created_at": NOW.isoformat(), "expires_at": NOW.isoformat(),
    "reason_code": "STRATEGY_SIGNAL", "reason": "isolation test",
    "context_hash": "h" * 16, "sl_distance": 10.0, "risk_usd": 20.0,
}
SPEC = ShadowSpec(label="lb-iso", strategy_id="london_breakout",
                  strategy_version="1.0.0", module="strategies.london_breakout")

FORBIDDEN_MODULES = (
    "app.bridge", "app.worker", "app.kill_switch", "app.routes",
    "httpx", "requests", "aiohttp", "urllib.request", "socket",
)
FORBIDDEN_SQL = ("INSERT INTO orders", "INTO bridge_commands",
                 "INSERT INTO paper_orders", "UPDATE orders", "DELETE FROM orders")


def _shadow_sources() -> dict[str, str]:
    return {p.name: p.read_text() for p in sorted(SHADOW_DIR.glob("*.py"))}


def test_ast_no_order_path_imports():
    """Lapis 1: shadow tidak meng-import modul jalur order / HTTP client."""
    for name, src in _shadow_sources().items():
        tree = ast.parse(src, filename=name)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    root = alias.name.split(".")[0]
                    assert alias.name not in FORBIDDEN_MODULES, (
                        f"{name} meng-import {alias.name} (jalur order, PRD 9.2)")
                    assert root not in {"httpx", "requests", "aiohttp", "socket"}, (
                        f"{name} meng-import HTTP/socket client: {alias.name}")
            elif isinstance(node, ast.ImportFrom):
                root = (node.module or "").split(".")[0]
                assert node.module not in FORBIDDEN_MODULES, (
                    f"{name} meng-import dari {node.module} (jalur order, PRD 9.2)")
                assert root not in {"httpx", "requests", "aiohttp", "socket"}, (
                    f"{name} meng-import HTTP/socket client: {node.module}")


def test_ast_no_order_table_writes():
    """Lapis 1b: SQL shadow tidak menulis ke tabel order mana pun."""
    for name, src in _shadow_sources().items():
        low = src.lower()
        for fragment in FORBIDDEN_SQL:
            assert fragment.lower() not in low, (
                f"{name} memuat SQL '{fragment}' (shadow tak boleh sentuh "
                f"ledger order, PRD 9.2)")


@pytest.fixture
async def iso_setup(_clean_db):
    await db.set_setting("max_volume", 1.0)
    await db.set_setting("max_spread", 0.50)
    await db.set_setting("max_orders_per_min", 10)
    await db.set_setting("halted", False)
    await db.set_setting("kill_switch", False)
    async with db.pool().connection() as conn:
        run_id = await store.ensure_run(
            conn, strategy_id="london_breakout", strategy_version="1.0.0",
            label=SPEC.label, symbol="XAUUSD", timeframe="5m",
            params_hash="iso", code_commit="test123", config={})
        yield conn, run_id


async def _count(conn, table: str) -> int:
    row = await conn.execute(f"SELECT count(*) AS n FROM {table}")
    return int((await row.fetchone())["n"])


async def test_iteration_never_touches_order_ledger(iso_setup, monkeypatch):
    """Lapis 2 E2E: sinyal masuk; orders/bridge_commands/paper_orders nol.

    Semua fungsi pengirim order yang bisa dijangkau di-patch untuk melempar;
    iterasi shadow tetap sukses karena tidak pernah memanggilnya.
    """
    conn, run_id = iso_setup

    def _boom(*a, **k):  # setiap sentuhan jalur order = ledak
        raise AssertionError("shadow memanggil jalur order (pelanggaran PRD 9.2)")

    monkeypatch.setattr(supervisor, "decide", _boom, raising=False)
    import app.bridge as bridge
    for name in dir(bridge):
        if name.startswith("send") or name in ("place_order", "submit"):
            monkeypatch.setattr(bridge, name, _boom, raising=False)

    async def fake_decide(conn, **kwargs):
        from types import SimpleNamespace
        return SimpleNamespace(
            strategy_id="london_breakout", status="PAPER", intent=INTENT,
            rejected=False, reason=None, reason_code=None, breaker={},
            signal_id="abc123")

    monkeypatch.setattr(runner, "_decide", fake_decide)
    state = dict(store.DEFAULT_STATE)
    before = {t: await _count(conn, t)
              for t in ("orders", "bridge_commands", "paper_orders")}
    logs = await runner.run_iteration(
        conn, state, spec=SPEC, run_id=run_id,
        settings=await db.get_settings(), params=None, tick=TICK, candles=[],
        spread_median=0.25, now=NOW, allow_entry=True,
        code_commit_hash="test123", fill_model=FillModel())
    after = {t: await _count(conn, t)
             for t in ("orders", "bridge_commands", "paper_orders")}
    assert before == after == {"orders": 0, "bridge_commands": 0,
                               "paper_orders": 0}
    assert any("SIM ENTRY" in line for line in logs)
    rows = await conn.execute(
        "SELECT sim_status FROM shadow_signals WHERE run_id = %s", (run_id,))
    assert [r["sim_status"] for r in await rows.fetchall()] == ["FILLED"]


async def test_tripwire_detects_order_insert(iso_setup):
    """Lapis 3: tripwire mendeteksi insert order milik shadow (bila terjadi).

    Order strategi LAIN (llm/manual) yang sah TIDAK memicu tripwire.
    """
    conn, _ = iso_setup
    trip = OrderLedgerTripwire(strategy_ids=["london_breakout"])
    await trip.arm(conn)
    assert await trip.verify(conn)
    # order strategi lain: sah, tripwire tetap OK
    await conn.execute(
        "INSERT INTO orders (symbol, side, volume, sl, tp, status, strategy) "
        "VALUES ('XAUUSD', 'BUY', 0.01, 1, 2, 'RISK_PASS', 'llm')")
    assert await trip.verify(conn)
    # order milik shadow: pelanggaran
    await conn.execute(
        "INSERT INTO orders (symbol, side, volume, sl, tp, status, strategy) "
        "VALUES ('XAUUSD', 'BUY', 0.01, 1, 2, 'RISK_PASS', 'london_breakout')")
    assert not await trip.verify(conn)


async def test_tick_once_records_and_tripwire_ok(_clean_db, monkeypatch):
    """tick_once (isi loop utama): sinyal tercatat dari tick live, tripwire OK.

    decide() dipatch supaya test tidak men-spawn sandbox; jalur data
    (feed/candle/regime/store/tripwire) tetap asli.
    """
    from shadow import loop as shadow_loop
    from types import SimpleNamespace

    await db.set_setting("max_volume", 1.0)
    await db.set_setting("max_spread", 0.50)
    await db.set_setting("max_orders_per_min", 10)
    await db.set_setting("kill_switch", False)
    await db.set_setting("halted", False)
    await db.set_setting("shadow_strategies", [
        {"label": "lb-e2e", "module": "strategies.london_breakout",
         "params": {}}])

    async def fake_decide(conn, **kwargs):
        return SimpleNamespace(
            strategy_id="london_breakout", status="PAPER", intent=INTENT,
            rejected=False, reason=None, reason_code=None, breaker={},
            signal_id="abc123")

    monkeypatch.setattr(runner, "_decide", fake_decide)
    from shadow.specs import load_specs, params_hash
    settings = await db.get_settings()
    specs, errors = load_specs(settings)
    assert not errors and len(specs) == 1
    fm = FillModel()
    async with db.pool().connection() as conn:
        trip = OrderLedgerTripwire()
        await trip.arm(conn)
        run_ids = {}
        for spec in specs:
            run_ids[spec.label] = await store.ensure_run(
                conn, strategy_id=spec.strategy_id,
                strategy_version=spec.strategy_version, label=spec.label,
                symbol=spec.symbol, timeframe=spec.timeframe,
                params_hash=params_hash(spec.params), code_commit="test123",
                config={})
            states = {spec.label: dict(store.DEFAULT_STATE)}
            await shadow_loop.tick_once(
                conn, states, specs, run_ids, settings, fm, "test123")
        assert await trip.verify(conn)
        assert await _count(conn, "orders") == 0
        assert await _count(conn, "bridge_commands") == 0
        rows = await conn.execute(
            "SELECT sim_status FROM shadow_signals WHERE label = 'lb-e2e'")
        found = [r["sim_status"] for r in await rows.fetchall()]
    # Tick live mungkin menghasilkan sinyal atau tidak tergantung jam pasar;
    # yang wajib: loop jalan, tripwire OK, tanpa jejak order.
    assert all(s in ("FILLED", "REJECTED", "REGIME_BLOCKED") for s in found)
