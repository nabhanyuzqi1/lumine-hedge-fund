"""GET /strategies + POST /strategies/{id}/mode (Strategy Lab, PRD P1b)."""

from __future__ import annotations

import itertools
import json
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from app import db
from app.main import app
from paper.store import save_state

UTC = timezone.utc
_BASE_TS = datetime(2026, 11, 20, 8, 0, 0, tzinfo=UTC)
_SEQ = itertools.count()


def _next_ts() -> datetime:
    """Timestamp naik monoton per pemanggilan dalam satu proses pytest."""
    return _BASE_TS + timedelta(seconds=next(_SEQ))


async def _seed_paper_order(**over) -> None:
    row = {
        "mode": "PAPER", "strategy": "london_breakout", "symbol": "XAUUSD",
        "side": "BUY", "volume": 0.1, "sl": 1998.0, "tp": 2010.0,
        "status": "CLOSED", "entry_price": 2000.0, "exit_price": 2002.0,
        "profit": 10.0,
    }
    row.update(over)
    row.setdefault("created_at", _next_ts())
    if "closed_at" not in row:
        row["closed_at"] = row["created_at"] if row["status"] == "CLOSED" else None
    async with db.pool().connection() as conn:
        await conn.execute(
            """
            INSERT INTO paper_orders (mode, strategy, symbol, side, volume, sl, tp,
                                      status, entry_price, exit_price, profit,
                                      created_at, closed_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (row["mode"], row["strategy"], row["symbol"], row["side"], row["volume"],
             row["sl"], row["tp"], row["status"], row["entry_price"],
             row["exit_price"], row["profit"], row["created_at"], row["closed_at"]),
        )


async def _seed_strategy_row(strategy_id: str = "london_breakout", *,
                             status: str = "PAPER", enabled: bool = True,
                             current_version: str | None = "1.0.0",
                             breaker: dict | None = None) -> None:
    """Baris registry supervisor (tabel strategies) untuk satu strategi."""
    async with db.pool().connection() as conn:
        await conn.execute(
            """
            INSERT INTO strategies (strategy_id, name, status, environment,
                                    config, current_version, enabled, circuit_breaker)
            VALUES (%s, %s, %s, 'dev', '{}'::jsonb, %s, %s, %s::jsonb)
            ON CONFLICT (strategy_id) DO NOTHING
            """,
            (strategy_id, strategy_id, status, current_version, enabled,
             json.dumps(breaker or {})),
        )


async def _seed_shadow_run(strategy_id: str = "london_breakout", *,
                           status: str = "RUNNING", label: str = "lb-base",
                           signal_count: int = 0,
                           created_at: datetime | None = None,
                           completed_at: datetime | None = None) -> str:
    run_id = uuid4()
    async with db.pool().connection() as conn:
        await conn.execute(
            """
            INSERT INTO shadow_runs (run_id, strategy_id, strategy_version, label,
                                     symbol, timeframe, status, signal_count,
                                     created_at, completed_at)
            VALUES (%s, %s, '1.0.0', %s, 'XAUUSD', 'M5', %s, %s, %s, %s)
            """,
            (run_id.hex, strategy_id, label, status, signal_count,
             created_at or _next_ts(), completed_at),
        )
    return str(run_id)


@pytest.fixture(autouse=True)
async def _reset_strategy_settings():
    """settings table tidak di-truncate conftest — bersihkan key mode strategi."""
    yield
    async with db.pool().connection() as conn:
        await conn.execute("DELETE FROM settings WHERE key LIKE 'strategy_mode_%'")


async def test_strategies_requires_auth():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/strategies")
        assert resp.status_code == 401


async def test_strategies_list_returns_registered_strategies(client):
    resp = await client.get("/strategies")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list) and len(data) == 3
    s = data[0]
    assert s["id"] == "london_breakout"
    assert s["track"] == "A"
    assert s["mode"] == "paper"  # default sebelum pernah diubah
    # field statistik numerik (UI memformat langsung, tidak boleh null)
    for key in ("win", "pf", "dd", "sharpe", "trades", "balance"):
        assert isinstance(s[key], (int, float)), key
    assert s["curve"] == [10000.0]
    assert s["open_position"] is None
    # strategi #2 terdaftar dengan state-nya sendiri
    mr = data[1]
    assert mr["id"] == "mean_reversion"
    assert mr["track"] == "A"  # rule-based; Track B = ML (PRD 5.3)
    assert mr["mode"] == "paper"
    assert mr["balance"] == 10000.0
    assert mr["open_position"] is None
    # strategi #3 (multipair P2): BTCUSD 24/7, simbol & state sendiri
    btc = data[2]
    assert btc["id"] == "btc_range_breakout"
    assert btc["symbol"] == "BTCUSD"
    assert btc["track"] == "A"
    assert btc["mode"] == "paper"
    assert btc["balance"] == 10000.0
    assert btc["open_position"] is None


async def test_strategy_state_isolated_per_strategy(client):
    """Ledger & state strategi #2 tidak tercampur dengan strategi #1."""
    await _seed_paper_order(profit=10.0)                                   # london WIN
    await _seed_paper_order(strategy="mean_reversion", profit=7.0)         # mr WIN
    async with db.pool().connection() as conn:
        await save_state(conn, "runner_mean_reversion", {
            "balance": 10007.0,
            "days_observed": ["2026-11-22"],
            "position": None,
        })
    resp = await client.get("/strategies")
    by_id = {s["id"]: s for s in resp.json()}
    assert by_id["london_breakout"]["balance"] == 10010.0
    assert by_id["london_breakout"]["trades"] == 1
    assert by_id["mean_reversion"]["balance"] == 10007.0
    assert by_id["mean_reversion"]["trades"] == 1
    assert by_id["mean_reversion"]["paper_days"] == 1
    assert by_id["mean_reversion"]["runner_updated_at"] is not None


async def test_strategies_stats_from_paper_ledger(client):
    await _seed_paper_order(profit=10.0)                       # WIN
    await _seed_paper_order(profit=-4.0, side="SELL")          # LOSS
    await _seed_paper_order(profit=6.0)                        # WIN
    resp = await client.get("/strategies")
    s = resp.json()[0]
    assert s["trades"] == 3
    assert s["win"] == round(2 / 3, 4)
    assert s["pf"] == 4.0        # gross profit 16 / gross loss 4
    assert s["curve"] == [10000.0, 10010.0, 10006.0, 10012.0]
    assert s["balance"] == 10012.0
    assert 0 < s["dd"] < 1


async def test_strategies_open_position_from_runner_state(client):
    await _seed_paper_order(status="OPEN", profit=0.0)
    async with db.pool().connection() as conn:
        await save_state(conn, "runner", {
            "balance": 10005.5,
            "days_observed": ["2026-11-20", "2026-11-21"],
            "position": {"order_id": "x", "side": "BUY", "volume": 0.1,
                         "entry_price": 2000.0, "sl": 1998.0, "tp": 2010.0},
        })
    resp = await client.get("/strategies")
    s = resp.json()[0]
    assert s["balance"] == 10005.5
    assert s["paper_days"] == 2
    assert s["open_position"]["side"] == "BUY"
    assert s["runner_updated_at"] is not None


async def test_set_mode_persists_and_returns_summary(client_2fa):
    resp = await client_2fa.post("/strategies/london_breakout/mode", json={"mode": "live"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["mode"] == "live"
    # gerbang paper belum lolos -> peringatan informatif, tidak memblokir
    assert "warning" in body
    assert (await client_2fa.get("/strategies")).json()[0]["mode"] == "live"

    resp = await client_2fa.post("/strategies/london_breakout/mode", json={"mode": "paper"})
    assert resp.json()["mode"] == "paper"
    assert "warning" not in resp.json()


async def test_set_mode_off_allowed(client):
    resp = await client.post("/strategies/london_breakout/mode", json={"mode": "off"})
    assert resp.status_code == 200
    assert resp.json()["mode"] == "off"


async def test_set_mode_invalid_422(client):
    resp = await client.post("/strategies/london_breakout/mode", json={"mode": "yolo"})
    assert resp.status_code == 422


async def test_set_mode_unknown_strategy_404(client):
    resp = await client.post("/strategies/ma-cross-h1/mode", json={"mode": "paper"})
    assert resp.status_code == 404


async def test_set_mode_requires_csrf(client):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test",
                           cookies=dict(client.cookies)) as c:
        resp = await c.post("/strategies/london_breakout/mode", json={"mode": "live"})
        assert resp.status_code == 403


# ── AUDIT-C: satu API terenrichment untuk Lab + Dashboard ───────────────────
# Kontrak: /strategies mengembalikan mode, lifecycle status, active/pause,
# P&L paper, winrate, equity_mini (<=30 titik), dan shadow run terbaru.
# Dashboard paper/shadow memfilter `mode` dari respons ini (1:1 dengan Lab).

ENRICHED_KEYS = ("mode", "status", "active", "pause_reasons", "lifecycle",
                 "pnl", "winrate", "equity_mini", "shadow")


async def test_strategies_enriched_fields_for_unregistered_paper(client):
    """DB baru (tanpa baris `strategies`) tetap mengembalikan bentuk lengkap."""
    resp = await client.get("/strategies")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 3
    for s in data:
        for key in ENRICHED_KEYS:
            assert key in s, key
        assert s["mode"] == "paper"
        assert s["status"] == "UNREGISTERED"
        assert s["active"] is False
        assert s["pause_reasons"] == ["lifecycle:unregistered"]
        assert s["lifecycle"]["registered"] is False
        assert s["lifecycle"]["breaker_state"] == "CLOSED"
        assert s["pnl"] == {"realized": 0.0, "start_balance": 10000.0,
                            "balance": 10000.0, "return_pct": 0.0,
                            "open_trades": 0, "currency": "USD"}
        assert s["winrate"] == s["win"] == 0.0
        assert s["equity_mini"] == [{"t": None, "v": 10000.0}]
        assert s["shadow"] is None


async def test_strategies_lifecycle_status_and_active_from_supervisor(client):
    await _seed_strategy_row("london_breakout", status="PAPER", enabled=True,
                             current_version="1.1.0")
    await _seed_strategy_row("mean_reversion", status="DISABLED", enabled=False,
                             current_version="1.0.0")
    by_id = {s["id"]: s for s in (await client.get("/strategies")).json()}

    lb = by_id["london_breakout"]
    assert lb["status"] == "PAPER"
    assert lb["active"] is True
    assert lb["pause_reasons"] == []
    assert lb["lifecycle"] == {
        "registered": True, "status": "PAPER", "enabled": True,
        "current_version": "1.1.0", "breaker_state": "CLOSED",
        "consecutive_errors": 0, "breaker_opened_at": None,
        "updated_at": lb["lifecycle"]["updated_at"],
    }
    assert lb["lifecycle"]["updated_at"] is not None

    mr = by_id["mean_reversion"]
    assert mr["status"] == "DISABLED"
    assert mr["active"] is False
    assert mr["pause_reasons"] == ["lifecycle:disabled"]

    # strategi tanpa baris registry tetap "UNREGISTERED" dan tidak aktif
    btc = by_id["btc_range_breakout"]
    assert btc["status"] == "UNREGISTERED"
    assert btc["active"] is False


async def test_strategies_pause_reasons_kill_switch_and_breaker(client):
    opened = "2026-11-25T10:00:00+00:00"
    await _seed_strategy_row("london_breakout", status="LIVE", enabled=True,
                             breaker={"state": "OPEN", "consecutive_errors": 5,
                                      "opened_at": opened,
                                      "last_error": "timeout"})
    await _seed_strategy_row("mean_reversion", status="SHADOW", enabled=True)
    await db.set_setting("paused_strategies", ["mean_reversion"])

    by_id = {s["id"]: s for s in (await client.get("/strategies")).json()}
    lb = by_id["london_breakout"]
    assert lb["active"] is False
    assert lb["pause_reasons"] == ["breaker:open"]
    assert lb["lifecycle"]["breaker_state"] == "OPEN"
    assert lb["lifecycle"]["consecutive_errors"] == 5
    assert lb["lifecycle"]["breaker_opened_at"] == opened

    mr = by_id["mean_reversion"]
    assert mr["active"] is False
    assert mr["pause_reasons"] == ["kill_switch:paused"]
    assert mr["status"] == "SHADOW"


async def test_strategies_pnl_winrate_equity_match_paper_ledger(client):
    """Nilai rekap == sumber ledger paper_orders + paper_state (bukan hitungan UI)."""
    await _seed_paper_order(profit=10.0)                       # WIN
    await _seed_paper_order(profit=-4.0, side="SELL")          # LOSS
    await _seed_paper_order(profit=6.0)                        # WIN
    await _seed_paper_order(strategy="mean_reversion", profit=7.0)
    await _seed_paper_order(mode="REPLAY", profit=99.0)        # bukan ledger paper
    await _seed_paper_order(status="REJECTED", profit=0.0)     # bukan trade

    data = (await client.get("/strategies")).json()
    by_id = {s["id"]: s for s in data}
    lb = by_id["london_breakout"]

    assert lb["trades"] == 3
    assert lb["winrate"] == lb["win"] == round(2 / 3, 4)
    assert lb["pnl"] == {"realized": 12.0, "start_balance": 10000.0,
                         "balance": 10012.0, "return_pct": 0.12,
                         "open_trades": 0, "currency": "USD"}
    assert lb["balance"] == 10012.0
    # equity_mini = titik kurva yang sama dengan `curve`, plus timestamp per trade
    assert [p["v"] for p in lb["equity_mini"]] == lb["curve"] == [
        10000.0, 10010.0, 10006.0, 10012.0]
    assert lb["equity_mini"][0]["t"] is None
    assert all(p["t"] for p in lb["equity_mini"][1:])
    # urut waktu
    stamps = [p["t"] for p in lb["equity_mini"][1:]]
    assert stamps == sorted(stamps)

    mr = by_id["mean_reversion"]
    assert mr["pnl"]["realized"] == 7.0
    assert mr["trades"] == 1

    # konsistensi silang: total realized semua strategi == total ledger paper
    async with db.pool().connection() as conn:
        cur = await conn.execute(
            "SELECT COALESCE(sum(profit), 0) AS total FROM paper_orders "
            "WHERE mode = 'PAPER' AND status = 'CLOSED'")
        ledger_total = float((await cur.fetchone())["total"])
    assert sum(s["pnl"]["realized"] for s in data) == round(ledger_total, 2)


async def test_strategies_equity_mini_capped_at_30_points(client):
    for i in range(40):
        await _seed_paper_order(profit=1.0)
    lb = (await client.get("/strategies")).json()[0]
    assert len(lb["curve"]) == 41          # kurva penuh tetap tersedia
    assert len(lb["equity_mini"]) == 30    # mini = 30 titik terakhir
    assert [p["v"] for p in lb["equity_mini"]] == lb["curve"][-30:]
    assert lb["equity_mini"][-1]["v"] == 10040.0
    assert lb["pnl"]["realized"] == 40.0


async def test_strategies_open_trades_and_mode_off_stay_separate(client):
    await _seed_strategy_row("london_breakout", status="PAPER", enabled=True)
    await _seed_paper_order(status="OPEN", profit=0.0)
    resp = await client.post("/strategies/london_breakout/mode", json={"mode": "off"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["mode"] == "off"
    assert body["active"] is True          # lifecycle tetap aktif
    assert body["pause_reasons"] == []     # mode != status pause supervisor
    assert body["pnl"]["open_trades"] == 1
    assert body["equity_mini"] == [{"t": None, "v": 10000.0}]

    data = (await client.get("/strategies")).json()
    assert data[0]["mode"] == "off"


async def test_strategies_shadow_summary_latest_run_per_strategy(client):
    old = _next_ts()
    newer = old + timedelta(hours=2)
    old_run = await _seed_shadow_run("london_breakout", status="COMPLETED",
                                     label="lb-base", signal_count=3,
                                     created_at=old, completed_at=newer)
    new_run = await _seed_shadow_run("london_breakout", status="RUNNING",
                                     label="lb-v2", signal_count=1,
                                     created_at=newer)
    await _seed_shadow_run("btc_range_breakout", status="RUNNING",
                           label="btc-base", signal_count=7, created_at=newer)

    by_id = {s["id"]: s for s in (await client.get("/strategies")).json()}
    lb = by_id["london_breakout"]["shadow"]
    assert lb["run_id"] == new_run
    assert lb["run_id"] != old_run
    assert lb["status"] == "RUNNING"
    assert lb["label"] == "lb-v2"
    assert lb["signal_count"] == 1
    assert lb["is_simulation"] is True
    assert lb["created_at"] is not None
    assert lb["completed_at"] is None

    btc = by_id["btc_range_breakout"]["shadow"]
    assert btc["label"] == "btc-base" and btc["signal_count"] == 7
    # strategi tanpa shadow run -> null (bukan field hilang)
    assert by_id["mean_reversion"]["shadow"] is None


async def test_shadow_summary_matches_shadow_runs_endpoint(client):
    """Ringkasan shadow di /strategies == run terbaru dari /shadow/runs (1:1)."""
    t0 = _next_ts()
    await _seed_shadow_run("london_breakout", status="COMPLETED", label="lb-old",
                           signal_count=2, created_at=t0,
                           completed_at=t0 + timedelta(minutes=30))
    await _seed_shadow_run("london_breakout", status="RUNNING", label="lb-new",
                           signal_count=4, created_at=t0 + timedelta(hours=1))
    await _seed_shadow_run("mean_reversion", status="RUNNING", label="mr-base",
                           signal_count=1, created_at=t0 + timedelta(hours=1))

    runs = (await client.get("/shadow/runs")).json()["runs"]
    latest_by_strategy: dict[str, dict] = {}
    for run in runs:
        latest_by_strategy.setdefault(run["strategy_id"], run)

    for s in (await client.get("/strategies")).json():
        expected = latest_by_strategy.get(s["id"])
        if expected is None:
            assert s["shadow"] is None
            continue
        assert s["shadow"]["run_id"] == expected["run_id"], s["id"]
        assert s["shadow"]["status"] == expected["status"]
        assert s["shadow"]["label"] == expected["label"]
        assert s["shadow"]["signal_count"] == expected["signal_count"]
