"""Test RISK-B (t_f3570608): auto break-even + trailing stop deterministik.

Cakupan unit (fungsi murni, tanpa DB):
- config merge/default + validasi (flag default OFF).
- ATR(M5,14) dari candle.
- invarian only-tighten long & short, trigger BE, trail ATR + floor min,
  aktivasi trailing, stop tidak sah, data kurang -> fail-closed.

Cakupan integrasi (DB test + app in-process) ada di bagian bawah file:
flag OFF tanpa tulis, pause saat HALT/kill-switch/agent pause, antrean
bridge_commands MODIFY_SL + audit order_events, idempotensi (in-flight /
DONE / FAILED), dan E2E kontrak bridge poll -> result.
"""
from __future__ import annotations

import json

import pytest
from httpx import ASGITransport, AsyncClient

from app import auto_sl, db, kill_switch, market
from app.auto_sl import (
    atr_from_candles,
    auto_sl_config,
    decide_sl_action,
    symbol_buffers,
)
from app.main import app


@pytest.fixture(autouse=True)
async def _reset_auto_sl(_clean_db):
    """Isolasi settings auto_sl antar-test (settings tidak di-TRUNCATE)."""
    await db.set_setting("auto_sl", {"enabled": False})
    await db.set_setting("halted", False)
    await db.set_setting("kill_switch", False)
    await db.set_setting("llm_agent_pause", None)
    yield
    await db.set_setting("auto_sl", {"enabled": False})
    await db.set_setting("halted", False)
    await db.set_setting("kill_switch", False)
    await db.set_setting("llm_agent_pause", None)


def cfg_on(**over) -> dict:
    raw = {"enabled": True}
    raw.update(over)
    return auto_sl_config({"auto_sl": raw})


def _c(high: float, low: float, close: float) -> dict:
    return {"high": high, "low": low, "close": close}


# ----------------------------------------------------------- config & ATR

def test_config_default_off_and_defaults():
    cfg = auto_sl_config({})
    assert cfg["enabled"] is False          # DEFAULT OFF (owner yang aktifkan)
    assert cfg["be_trigger_r"] == 1.0
    assert cfg["trail_atr_mult"] == 1.5
    assert cfg["trail_activate_r"] == 1.0
    assert cfg["atr_timeframe"] == "M5"
    assert cfg["atr_period"] == 14
    assert cfg["be_buffer_usd"]["XAUUSD"] == 0.30


def test_config_partial_override():
    cfg = cfg_on(be_trigger_r=1.2, trail_atr_mult=2.0,
                 be_buffer_usd={"XAUUSD": 0.40})
    assert cfg["enabled"] is True
    assert cfg["be_trigger_r"] == 1.2
    assert cfg["trail_atr_mult"] == 2.0
    assert cfg["be_buffer_usd"] == {"XAUUSD": 0.40}
    # nilai yang tidak dioverride tetap default
    assert cfg["trail_min_usd"]["XAUUSD"] == 0.50


def test_config_invalid_values_fall_back():
    cfg = cfg_on(be_trigger_r="rusak", trail_atr_mult=-3, interval_s=0,
                 trail_min_usd={"XAUUSD": "x", "BTCUSD": 10})
    assert cfg["be_trigger_r"] == 1.0
    assert cfg["trail_atr_mult"] == 1.5
    assert cfg["interval_s"] == 10.0
    assert cfg["trail_min_usd"] == {"BTCUSD": 10.0}


def test_config_trail_activate_clamped_to_be_trigger():
    cfg = cfg_on(be_trigger_r=1.5, trail_activate_r=0.5)
    assert cfg["trail_activate_r"] == 1.5   # trailing selalu setelah BE


def test_atr_known_flat_series():
    candles = [_c(101, 99, 100) for _ in range(15)]
    assert atr_from_candles(candles) == pytest.approx(2.0)


def test_atr_uses_previous_close_gap():
    candles = [_c(100, 99, 100)] + [_c(110, 105, 107) for _ in range(14)]
    # TR pertama di jendela = max(5, |110-100|, |105-100|) = 10; 13 sisanya 5.
    assert atr_from_candles(candles) == pytest.approx((10 + 13 * 5) / 14)


def test_atr_insufficient_or_invalid_data():
    assert atr_from_candles([_c(101, 99, 100)] * 14) is None   # butuh period+1
    assert atr_from_candles([{"high": "x"}]) is None
    assert atr_from_candles([]) is None


# ------------------------------------------------------------ break-even

def test_be_trigger_long():
    d = decide_sl_action(
        side="BUY", entry=2000.0, initial_sl=1995.0, current_sl=1995.0,
        bid=2005.5, ask=2005.8, atr=None, cfg=cfg_on(),
        be_buffer=0.30, trail_min=0.50,
    )
    assert d["action"] == "modify"
    assert d["target"] == 2000.30        # entry + buffer
    assert d["reason"] == "break_even"
    assert d["detail"]["r"] == 5.0
    assert d["detail"]["r_multiple"] == pytest.approx(1.1)


def test_be_not_triggered_below_1r():
    d = decide_sl_action(
        side="BUY", entry=2000.0, initial_sl=1995.0, current_sl=1995.0,
        bid=2004.9, ask=2005.2, atr=None, cfg=cfg_on(),
        be_buffer=0.30, trail_min=0.50,
    )
    assert d["action"] == "none"


def test_be_trigger_short():
    d = decide_sl_action(
        side="SELL", entry=2000.0, initial_sl=2005.0, current_sl=2005.0,
        bid=1994.2, ask=1994.5, atr=None, cfg=cfg_on(),
        be_buffer=0.30, trail_min=0.50,
    )
    assert d["action"] == "modify"
    assert d["target"] == 1999.70        # entry - buffer
    assert d["reason"] == "break_even"


# --------------------------------------------- invarian only-tighten

def test_only_tighten_long_blocks_looser():
    d = decide_sl_action(
        side="BUY", entry=2000.0, initial_sl=1995.0, current_sl=2001.0,
        bid=2005.5, ask=2005.8, atr=None, cfg=cfg_on(),
        be_buffer=0.30, trail_min=0.50,
    )
    assert d["action"] == "none"         # BE 2000.30 < SL sekarang 2001


def test_only_tighten_short_blocks_looser():
    d = decide_sl_action(
        side="SELL", entry=2000.0, initial_sl=2005.0, current_sl=1999.0,
        bid=1994.2, ask=1994.5, atr=None, cfg=cfg_on(),
        be_buffer=0.30, trail_min=0.50,
    )
    assert d["action"] == "none"         # BE 1999.70 > SL sekarang 1999


def test_no_current_sl_allows_be():
    d = decide_sl_action(
        side="BUY", entry=2000.0, initial_sl=1995.0, current_sl=None,
        bid=2005.5, ask=2005.8, atr=None, cfg=cfg_on(),
        be_buffer=0.30, trail_min=0.50,
    )
    assert d["action"] == "modify"
    assert d["target"] == 2000.30


# --------------------------------------------------------------- trailing

def test_trail_after_be_activation_long():
    d = decide_sl_action(
        side="BUY", entry=2000.0, initial_sl=1995.0, current_sl=2000.30,
        bid=2007.0, ask=2007.3, atr=2.0, cfg=cfg_on(),
        be_buffer=0.30, trail_min=0.50,
    )
    # dist = max(0.50, 1.5 x 2.0) = 3.0 -> 2007 - 3.0 = 2004.0 (lebih ketat dari BE)
    assert d["action"] == "modify"
    assert d["target"] == 2004.0
    assert d["reason"] == "trail_atr"


def test_trail_min_floor_when_atr_tiny():
    d = decide_sl_action(
        side="BUY", entry=2000.0, initial_sl=1995.0, current_sl=2000.30,
        bid=2007.0, ask=2007.3, atr=0.1, cfg=cfg_on(),
        be_buffer=0.30, trail_min=0.50,
    )
    assert d["target"] == 2006.5         # dist = max(0.50, 0.15) = 0.50


def test_trail_not_active_below_activation_r():
    d = decide_sl_action(
        side="BUY", entry=2000.0, initial_sl=1995.0, current_sl=1995.0,
        bid=2005.5, ask=2005.8, atr=2.0, cfg=cfg_on(trail_activate_r=2.0),
        be_buffer=0.30, trail_min=0.50,
    )
    assert d["action"] == "modify"
    assert d["target"] == 2000.30        # profit 1.1R < aktivasi 2R -> hanya BE
    assert d["reason"] == "break_even"


def test_trail_requires_atr():
    d = decide_sl_action(
        side="BUY", entry=2000.0, initial_sl=1995.0, current_sl=1995.0,
        bid=2010.0, ask=2010.3, atr=None, cfg=cfg_on(),
        be_buffer=0.30, trail_min=0.50,
    )
    assert d["action"] == "modify"
    assert d["target"] == 2000.30        # ATR tidak tersedia -> BE saja
    assert d["reason"] == "break_even"


def test_trail_only_tightens_vs_current_sl():
    d = decide_sl_action(
        side="BUY", entry=2000.0, initial_sl=1995.0, current_sl=2005.0,
        bid=2007.0, ask=2007.3, atr=2.0, cfg=cfg_on(),
        be_buffer=0.30, trail_min=0.50,
    )
    assert d["action"] == "none"         # trail 2004 < SL sekarang 2005


# ---------------------------------------------------------- fail-closed

def test_invalid_stop_beyond_price_skipped():
    d = decide_sl_action(
        side="BUY", entry=2000.0, initial_sl=1999.99, current_sl=1999.99,
        bid=2000.01, ask=2000.04, atr=None, cfg=cfg_on(),
        be_buffer=0.30, trail_min=0.50,
    )
    assert d["action"] == "none"         # BE 2000.30 >= harga -> stop tidak sah


def test_r_must_be_positive():
    for init in (2000.0, None):
        d = decide_sl_action(
            side="BUY", entry=2000.0, initial_sl=init, current_sl=None,
            bid=2010.0, ask=2010.3, atr=None, cfg=cfg_on(),
            be_buffer=0.30, trail_min=0.50,
        )
        assert d["action"] == "none"


def test_missing_tick_fail_closed():
    d = decide_sl_action(
        side="BUY", entry=2000.0, initial_sl=1995.0, current_sl=1995.0,
        bid=None, ask=None, atr=None, cfg=cfg_on(),
        be_buffer=0.30, trail_min=0.50,
    )
    assert d["action"] == "none"


def test_target_rounded_5dp():
    d = decide_sl_action(
        side="BUY", entry=2000.123456, initial_sl=1995.0, current_sl=1995.0,
        bid=2005.5, ask=2005.8, atr=None, cfg=cfg_on(),
        be_buffer=0.30, trail_min=0.50,
    )
    assert d["target"] == 2000.42346     # numeric(12,5)


def test_symbol_buffers_default_and_unknown():
    cfg = auto_sl_config({})
    assert symbol_buffers(cfg, "XAUUSD") == (0.30, 0.50)
    assert symbol_buffers(cfg, "EURUSD") == (0.0, 0.0)


# =============================================================== integrasi

async def _enable_auto_sl(**over) -> None:
    raw = {"enabled": True}
    raw.update(over)
    await db.set_setting("auto_sl", raw)


async def _open_llm_position(ticket: int, *, strategy: str = "llm",
                             side: str = "BUY", entry: float = 2000.0,
                             initial_sl: float = 1995.0,
                             current_sl: float | None = 1995.0,
                             tp: float | None = 2010.0) -> str:
    """Order pembuka FILLED + posisi OPEN ter-link (pola test_llm_agent_v2).

    orders.sl = SL AWAL (dasar R); positions.sl = SL broker saat ini.
    """
    async with db.pool().connection() as conn:
        row = await (await conn.execute(
            "INSERT INTO orders (symbol, side, volume, sl, tp, strategy, status) "
            "VALUES ('XAUUSD', %s, 0.01, %s, %s, %s, 'FILLED') RETURNING id",
            (side, initial_sl, tp, strategy),
        )).fetchone()
        await conn.execute(
            "INSERT INTO positions (ticket, order_id, symbol, side, volume, "
            "open_price, sl, tp, profit, status) "
            "VALUES (%s, %s, 'XAUUSD', %s, 0.01, %s, %s, %s, 0, 'OPEN')",
            (ticket, row["id"], side, entry, current_sl, tp),
        )
        return str(row["id"])


async def _commands() -> list[dict]:
    async with db.pool().connection() as conn:
        rows = await (await conn.execute(
            "SELECT * FROM bridge_commands ORDER BY created_at")).fetchall()
        return [dict(r) for r in rows]


async def _auto_events() -> list[dict]:
    async with db.pool().connection() as conn:
        rows = await (await conn.execute(
            "SELECT * FROM order_events WHERE to_status = 'AUTO_SL_MODIFY' "
            "ORDER BY id")).fetchall()
        return [dict(r) for r in rows]


async def _set_position_sl(ticket: int, sl: float | None) -> None:
    async with db.pool().connection() as conn:
        await conn.execute(
            "UPDATE positions SET sl = %s WHERE ticket = %s", (sl, ticket))


async def test_flag_off_no_writes():
    """DEFAULT OFF: tidak ada command/audit, SL tidak berubah (behavior lama)."""
    await _open_llm_position(880001)
    market.update_tick("XAUUSD", bid=2005.6, ask=2005.9)
    summary = await auto_sl.run_cycle()
    assert summary == {"skipped": "flag_off"}
    assert await _commands() == []
    assert await _auto_events() == []
    async with db.pool().connection() as conn:
        pos = await (await conn.execute(
            "SELECT sl FROM positions WHERE ticket = 880001")).fetchone()
    assert float(pos["sl"]) == 1995.0


@pytest.mark.parametrize("pause_kind", ["kill_switch", "agent_pause"])
async def test_paused_when_trading_stopped(pause_kind):
    """Pause saat GLOBAL_HALT / kill-switch / pause agent.

    (Flag mirror 'halted' tidak lagi jadi pemicu sendiri: t_4d524475.)
    """
    await _enable_auto_sl()
    await _open_llm_position(880002)
    market.update_tick("XAUUSD", bid=2005.6, ask=2005.9)
    if pause_kind == "kill_switch":
        await kill_switch.activate("GLOBAL_HALT", reason="test", source="test")
    else:
        await db.set_setting("llm_agent_pause", {"active": True})
    summary = await auto_sl.run_cycle()
    assert summary == {"skipped": "paused"}
    assert await _commands() == []
    assert await _auto_events() == []


async def test_halted_mirror_basi_tidak_mematikan_auto_sl():
    """t_4d524475: mirror 'halted' basi bukan alasan pause; kill-switch yang menentukan."""
    await _enable_auto_sl()
    await _open_llm_position(880009)
    market.update_tick("XAUUSD", bid=2005.6, ask=2005.9)
    await db.set_setting("halted", True)
    await db.set_setting("kill_switch", {"active": False, "mode": None})
    summary = await auto_sl.run_cycle()
    assert summary != {"skipped": "paused"}, summary


async def test_be_queues_modify_and_audit():
    """Profit >= 1R -> SL ke entry+buffer, tercatat command + audit."""
    await _enable_auto_sl()
    order_id = await _open_llm_position(880003, tp=2010.0)
    market.update_tick("XAUUSD", bid=2005.6, ask=2005.9)
    summary = await auto_sl.run_cycle()
    assert summary["modified"] == 1

    cmds = await _commands()
    assert len(cmds) == 1
    cmd = cmds[0]
    assert cmd["action"] == "MODIFY_SL"
    assert str(cmd["order_id"]) == order_id
    payload = cmd["payload"]
    assert payload["ticket"] == 880003
    assert payload["sl"] == 2000.30
    assert payload["tp"] == 2010.0      # TP existing WAJIB ikut (EA SLTP)
    assert payload["reason"] == "auto_break_even"
    assert payload["detail"]["r"] == 5.0

    events = await _auto_events()
    assert len(events) == 1
    ev = events[0]["payload"]
    assert ev["reason"] == "break_even"
    assert ev["sl"] == 2000.30
    assert ev["r"] == 5.0
    assert ev["r_multiple"] == pytest.approx(1.12)
    assert ev["atr"] is None

    async with db.pool().connection() as conn:
        pos = await (await conn.execute(
            "SELECT sl FROM positions WHERE ticket = 880003")).fetchone()
    assert float(pos["sl"]) == 2000.30  # posisi langsung mencerminkan target


async def test_idempotent_second_cycle():
    """Modify yang sama tidak dikirim ulang (SL sudah di target)."""
    await _enable_auto_sl()
    await _open_llm_position(880004)
    market.update_tick("XAUUSD", bid=2005.6, ask=2005.9)
    assert (await auto_sl.run_cycle())["modified"] == 1
    assert (await auto_sl.run_cycle())["modified"] == 0
    assert len(await _commands()) == 1


async def test_idempotent_in_flight_command():
    """Command QUEUED/DELIVERED untuk ticket memblokir kiriman baru."""
    await _enable_auto_sl()
    await _open_llm_position(880005)
    market.update_tick("XAUUSD", bid=2005.6, ask=2005.9)
    assert (await auto_sl.run_cycle())["modified"] == 1
    # Simulasi snapshot broker belum ikut: positions.sl kembali lama.
    await _set_position_sl(880005, 1995.0)
    for status in ("QUEUED", "DELIVERED"):
        async with db.pool().connection() as conn:
            await conn.execute(
                "UPDATE bridge_commands SET status = %s", (status,))
        assert (await auto_sl.run_cycle())["modified"] == 0
    assert len(await _commands()) == 1


async def test_idempotent_done_target_recent():
    """DONE baru (snapshot bisa telat) -> target yang sama tidak diulang."""
    await _enable_auto_sl()
    await _open_llm_position(880006)
    market.update_tick("XAUUSD", bid=2005.6, ask=2005.9)
    assert (await auto_sl.run_cycle())["modified"] == 1
    async with db.pool().connection() as conn:
        await conn.execute(
            "UPDATE bridge_commands SET status = 'DONE', resolved_at = now()")
    await _set_position_sl(880006, 1995.0)
    assert (await auto_sl.run_cycle())["modified"] == 0
    assert len(await _commands()) == 1


async def test_idempotent_failed_target_recent():
    """Target yang baru FAILED tidak di-spam ulang."""
    await _enable_auto_sl()
    await _open_llm_position(880007)
    market.update_tick("XAUUSD", bid=2005.6, ask=2005.9)
    async with db.pool().connection() as conn:
        await conn.execute(
            "INSERT INTO bridge_commands (order_id, action, payload, status, "
            "fail_reason, resolved_at) SELECT order_id, 'MODIFY_SL', %s, "
            "'FAILED', 'invalid stops', now() FROM positions WHERE ticket = 880007",
            (json.dumps({"ticket": 880007, "sl": 2000.30, "tp": 2010.0,
                         "reason": "auto_break_even"}),),
        )
    assert (await auto_sl.run_cycle())["modified"] == 0
    assert len(await _commands()) == 1


async def test_trail_uses_atr_m5():
    """Trailing aktif: SL = harga - max(min_trail, k x ATR(M5,14))."""
    await _enable_auto_sl()
    await _open_llm_position(880008)
    async with db.pool().connection() as conn:
        for i in range(15):
            await conn.execute(
                "INSERT INTO candles (symbol, timeframe, ts, open, high, low, close) "
                "VALUES ('XAUUSD', 'M5', now() - (%s || ' minutes')::interval, "
                "2000, 2001, 1999, 2000)", (str(i * 5),))
    # profit 7.0 = 1.4R -> trail dist = max(0.50, 1.5 x 2.0) = 3.0
    market.update_tick("XAUUSD", bid=2007.0, ask=2007.3)
    summary = await auto_sl.run_cycle()
    assert summary["modified"] == 1
    cmd = (await _commands())[0]
    assert cmd["payload"]["sl"] == 2004.0
    assert cmd["payload"]["reason"] == "auto_trail_atr"
    assert cmd["payload"]["detail"]["atr"] == pytest.approx(2.0)
    events = await _auto_events()
    assert events[0]["payload"]["atr"] == pytest.approx(2.0)
    assert events[0]["payload"]["reason"] == "trail_atr"


async def test_only_tighten_existing_sl_beyond_be():
    """SL sekarang sudah lebih ketat dari BE -> tidak ada modify."""
    await _enable_auto_sl()
    await _open_llm_position(880009, current_sl=2003.0)
    market.update_tick("XAUUSD", bid=2005.6, ask=2005.9)
    assert (await auto_sl.run_cycle())["modified"] == 0
    assert await _commands() == []


async def test_non_llm_position_untouched():
    """Scope loop = posisi strategy 'llm'; posisi manual tidak disentuh."""
    await _enable_auto_sl()
    await _open_llm_position(880010, strategy="manual")
    market.update_tick("XAUUSD", bid=2005.6, ask=2005.9)
    summary = await auto_sl.run_cycle()
    assert summary["positions"] == 0
    assert await _commands() == []


async def test_no_tick_no_action():
    """Tick belum ada (mis. API baru restart) -> tidak menebak."""
    await _enable_auto_sl()
    await _open_llm_position(880011)
    summary = await auto_sl.run_cycle()
    assert summary["modified"] == 0
    assert summary["skipped"][0]["why"] == "no_tick"


async def test_e2e_bridge_poll_result_flow(bridge_token):
    """E2E: loop antre MODIFY_SL -> EA poll -> result FILLED -> DONE."""
    await _enable_auto_sl()
    await _open_llm_position(880012, tp=2010.0)
    market.update_tick("XAUUSD", bid=2005.6, ask=2005.9)
    assert (await auto_sl.run_cycle())["modified"] == 1

    headers = {"Authorization": f"Bearer {bridge_token}"}
    async with AsyncClient(transport=ASGITransport(app=app),
                           base_url="http://test") as c:
        r = await c.get("/bridge/poll", params={"timeout_s": 0}, headers=headers)
        assert r.status_code == 200, r.text
        cmd = r.json()
        assert cmd["action"] == "MODIFY_SL"
        assert cmd["ticket"] == "880012"
        assert cmd["sl"] == 2000.30
        assert cmd["tp"] == 2010.0

        r = await c.post("/bridge/result", headers=headers, json={
            "command_id": cmd["command_id"], "status": "FILLED",
            "ticket": 880012,
        })
        assert r.status_code == 200, r.text
        assert r.json() == {"ok": True, "duplicate": False, "status": "DONE"}

        # snapshot posisi berikutnya membawa SL baru (kontrak EA 5 detik)
        r = await c.post("/bridge/positions", headers=headers, json={
            "positions": [{
                "ticket": 880012, "symbol": "XAUUSD", "side": "BUY",
                "volume": 0.01, "open_price": 2000.0, "sl": 2000.30,
                "tp": 2010.0, "profit": 5.6, "status": "OPEN",
            }],
        })
        assert r.status_code == 200, r.text

    cmds = await _commands()
    assert cmds[0]["status"] == "DONE"
    async with db.pool().connection() as conn:
        pos = await (await conn.execute(
            "SELECT sl FROM positions WHERE ticket = 880012")).fetchone()
    assert float(pos["sl"]) == 2000.30
    # siklus berikutnya: tidak ada modify baru (idempoten, SL sudah di target)
    assert (await auto_sl.run_cycle())["modified"] == 0
    assert len(await _commands()) == 1
