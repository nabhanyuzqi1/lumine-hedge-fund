"""Loop utama shadow runner + tripwire anti-order (PRD 9.2).

Dipisah dari iterasi agar modul tetap kecil; runner.py mengimpor dari sini.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from app import db, regime
from paper import feed
from strategies.broker_time import broker_utc_offset_hours  # offset broker A1'
from paper.runner import (LIQUIDITY_FRESH_S, TICK_WINDOW_MIN, db_timezone_offset_h,
                          load_candles, log)
from shadow import store
from shadow.fill import FillModel
from shadow.runner import (_decide, _params_for, code_commit, run_iteration,
                           shadow_enabled)
from shadow.specs import ShadowSpec, load_specs, params_hash

REGIME_STATES: dict[str, dict] = {}
REGIME_RECORDED: dict[str, str] = {}


class OrderLedgerTripwire:
    """Tripwire runtime: ledger order milik STRATEGI SHADOW tidak boleh berubah.

    Shadow tidak punya jalur tulis ke orders/bridge_commands (lihat docstring
    shadow.runner + test AST). Tripwire ini adalah jaring pengaman ketiga:
    bila count berubah, proses shadow menandai pelanggaran keras (exit code 9)
    supaya gagal terlihat, bukan diam-diam dianggap normal.

    Hanya baris yang dapat diatribusikan ke shadow yang dipantau (strategy =
    salah satu strategy_id spec, atau berawalan 'shadow'), sehingga order
    strategi LAIN (llm/manual/paper) yang sah tidak memicu false positive.
    """

    TABLES = ("orders", "bridge_commands")

    def __init__(self, strategy_ids: list[str] | None = None) -> None:
        self.strategy_ids = list(strategy_ids or [])
        self.baseline: dict[str, int] = {}

    async def arm(self, conn) -> None:
        self.baseline = {t: await self._count(conn, t) for t in self.TABLES}

    async def verify(self, conn) -> bool:
        for t in self.TABLES:
            now = await self._count(conn, t)
            if now != self.baseline.get(t):
                log(f"TRIPWIRE: {t} (shadow) berubah "
                    f"{self.baseline.get(t)} -> {now} "
                    f"selama shadow berjalan (PRD 9.2 pelanggaran)")
                return False
        return True

    async def _count(self, conn, table: str) -> int:
        ids = self.strategy_ids
        if table == "orders":
            sql = ("SELECT count(*) AS n FROM orders "
                   "WHERE substring(strategy from 1 for 6) = 'shadow'")
            args: tuple = ()
            if ids:
                sql += " OR strategy = ANY(%s)"
                args = (ids,)
        else:
            sql = ("SELECT count(*) AS n FROM bridge_commands bc "
                   "JOIN orders o ON o.id = bc.order_id "
                   "WHERE substring(o.strategy from 1 for 6) = 'shadow'")
            args = ()
            if ids:
                sql += " OR o.strategy = ANY(%s)"
                args = (ids,)
        row = await conn.execute(sql, args)
        return int((await row.fetchone())["n"])


def _regime_enabled(settings: dict) -> bool:
    return str(settings.get("regime_detection_enabled", "on")).lower() != "off"


async def tick_once(conn, states: dict[str, dict], specs: list[ShadowSpec],
                    run_ids: dict[str, object], settings: dict, fm: FillModel,
                    commit: str | None) -> None:
    """Satu siklus data live untuk semua versi shadow (data SAMA dgn paper)."""
    now = datetime.now(timezone.utc)
    for state in states.values():
        if state.get("shadow_start_ts") is None:
            state["shadow_start_ts"] = now.isoformat()
    by_symbol: dict[str, list[ShadowSpec]] = {}
    for spec in specs:
        by_symbol.setdefault(spec.symbol, []).append(spec)
    for symbol, symspecs in by_symbol.items():
        ticks = await feed.read_ticks_async(TICK_WINDOW_MIN, now, symbol=symbol)
        if not ticks:
            log(f"idle [{symbol}]: no ticks in HFM log yet")
            continue
        market_open = feed.is_market_open(ticks, now)
        tick = feed.latest(ticks)
        first = states[symspecs[0].label]
        if market_open:
            offset = feed.estimate_offset_hours(ticks)
            if offset is not None and offset != first.get("broker_offset_h"):
                for s in symspecs:
                    states[s.label]["broker_offset_h"] = offset
                log(f"[{symbol}] broker offset measured: UTC+{offset:g}")
        offset_h = first.get("broker_offset_h")
        if offset_h is None:
            offset_h = broker_utc_offset_hours(now)
        fresh = market_open and (now - tick["ts_utc"]).total_seconds() <= LIQUIDITY_FRESH_S
        spread_median = feed.spread_median_15m(ticks, now)
        db_tz = await db_timezone_offset_h(conn)
        candles = await load_candles(
            conn, symbol=symbol, db_tz_offset_h=db_tz,
            broker_offset_h=int(offset_h), now=now,
            timeframe=symspecs[0].timeframe, tf_seconds=symspecs[0].tf_seconds)

        # Regime: classifier yang SAMA dengan paper/backtest (PRD §6.5),
        # satu klasifikasi per simbol per loop, dipakai semua versi.
        regime_result = None
        if _regime_enabled(settings) and candles:
            try:
                rk = f"{symbol}:{symspecs[0].timeframe}"
                regime_result = regime.classify(
                    symbol=symbol, now=now, candles=candles,
                    liquidity={"ts": tick["ts_utc"].isoformat(),
                               "spread": tick["spread"],
                               "spread_median_15m": spread_median,
                               "fresh": fresh},
                    params=regime.default_params_for_symbol(symbol),
                    state=REGIME_STATES.get(rk),
                    tick_rate=len(ticks) / max(TICK_WINDOW_MIN - 1, 1))
                REGIME_STATES[rk] = regime_result.state
                last_bar = regime_result.state["last_bar_ts"]
                if REGIME_RECORDED.get(rk) != last_bar:
                    REGIME_RECORDED[rk] = last_bar
            except Exception as exc:  # noqa: BLE001 - regime tak boleh jatuhkan
                log(f"[{symbol}] regime error (isolated): {exc!r}")
                regime_result = None

        for spec in symspecs:
            state = states[spec.label]
            run_id = run_ids[spec.label]
            try:
                logs = await run_iteration(
                    conn, state, spec=spec, run_id=run_id, settings=settings,
                    params=_params_for(spec), tick=tick, candles=candles,
                    spread_median=spread_median, now=now, allow_entry=fresh,
                    regime_result=regime_result, code_commit_hash=commit,
                    fill_model=fm)
            except Exception as exc:  # noqa: BLE001 - isolasi satu versi
                log(f"[shadow:{spec.label}] iteration error (isolated): {exc!r}")
                logs = []
            await store.save_state(conn, spec.state_key, state)
            try:
                stats = await store.run_stats(conn, run_id, datetime(1970, 1, 1,
                                                                     tzinfo=timezone.utc))
                await store.update_run_metrics(conn, run_id, stats)
            except Exception as exc:  # noqa: BLE001 - metrics non-fatal
                log(f"[shadow:{spec.label}] metrics update failed: {exc!r}")
            for line in logs:
                log(f"[shadow:{spec.label}] {line}")
        if not market_open:
            log(f"[{symbol}] market closed (broker clock frozen); "
                f"last tick {tick['exchange_ts']}")
