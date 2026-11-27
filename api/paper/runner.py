"""Fund2 paper runner: all registered strategies in PAPER mode.

Never sends orders to the broker. Every loop:
  read HFM tick log -> market open? -> load M5 candles (broker time -> UTC)
  -> per strategy: manage open paper position (SL/TP/time exit)
  -> decide(context) -> risk gate -> persist paper fill.

Each strategy owns paper_state key `runner_<id>` (legacy: london_breakout
keeps `runner`), settings keys `strategy_mode_<id>` / `strategy_params_<id>`.

Run:  .venv/bin/python -m paper.runner [--once] [--status]
"""

from __future__ import annotations

import asyncio
import importlib
import json
import signal
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from app import db, regime, supervisor, degradation, degradation_store
from app.risk import RiskContext, risk_gate
from paper import feed, store
from paper.broker import PaperBroker, PaperPosition, unrealized
from strategies.broker_time import broker_utc_offset_hours, stored_to_utc
from strategies.london_breakout import STRATEGY_ID as LB_STRATEGY_ID
from strategies.london_breakout import STRATEGY_VERSION as LB_STRATEGY_VERSION
from strategies.london_breakout import StrategyParams as LBStrategyParams
from strategies.london_breakout import decide as lb_decide
from strategies.mean_reversion import STRATEGY_ID as MR_STRATEGY_ID
from strategies.mean_reversion import STRATEGY_VERSION as MR_STRATEGY_VERSION
from strategies.mean_reversion import StrategyParams as MRStrategyParams
from strategies.mean_reversion import decide as mr_decide
from strategies.btc_range_breakout import STRATEGY_ID as BTC_STRATEGY_ID
from strategies.btc_range_breakout import STRATEGY_VERSION as BTC_STRATEGY_VERSION
from strategies.btc_range_breakout import StrategyParams as BTCStrategyParams
from strategies.btc_range_breakout import decide as btc_decide

POLL_S = 15
TICK_WINDOW_MIN = 16
LIQUIDITY_FRESH_S = 60
SYMBOL = "XAUUSD"  # legacy default (strategi #1/#2); spek strategi membawa simbolnya
TIMEFRAME = "M5"   # kanonik DB/PRD; dulu "5m" bikin XAUUSD cari candle yang tak pernah ada (t_fbdb7329)
CANDLE_LIMIT = 300

MODE = "PAPER"

# ── Regime detection (PRD v2.2 §6) ──────────────────────────────────────────
# Classifier murni app.regime dipakai SAMA dengan backtest (PRD §6.5).
# State hysteresis in-memory per simbol:timeframe - aman di-restart (state
# None -> label mentah diadopsi; tidak mempengaruhi posisi/risk). Kill-switch:
# settings regime_detection_enabled = "off".
REGIME_STATES: dict[str, dict] = {}      # key "SYMBOL:TF" -> hysteresis state
REGIME_RECORDED: dict[str, str] = {}     # key "SYMBOL:TF" -> bar ts terakhir yang dicatat

# ── Degradation detection (PRD v2.2 §10, t_f2v22a5) ─────────────────────────
# Evaluasi periodik per strategi (eval_interval_s) + gate entry: DEGRADED =
# tidak boleh tambah risiko baru; HALTED = berhenti entry baru. Status hanya
# naik otomatis; re-enable hanya owner (API + 2FA). Kegagalan evaluasi tidak
# menghentikan runner (isolasi per strategi, pola regime).
DEG_STATUS: dict[str, str] = {}      # strategy_id -> status terakhir
DEG_LAST_EVAL: dict[str, datetime] = {}
DEG_LOGGED: dict[str, str] = {}      # anti-spam log perubahan status
_MODULE_CACHE: dict[str, object] = {}


def _strategy_module(spec: StrategySpec):
    """Modul strategi (utk ALLOWED_REGIMES); None = legacy tanpa modul."""
    if not spec.module:
        return None
    if spec.module not in _MODULE_CACHE:
        _MODULE_CACHE[spec.module] = importlib.import_module(spec.module)
    return _MODULE_CACHE[spec.module]


def regime_enabled(settings: dict) -> bool:
    return str(settings.get("regime_detection_enabled", "on")).lower() != "off"


async def record_regime(conn, *, symbol: str, timeframe: str, result,
                        context: str, ref_type: str | None = None,
                        ref_id=None) -> None:
    """Tulis satu baris regime_observations (PRD §6.4).

    Non-fatal: kegagalan insert tidak boleh menghentikan runner.
    """
    try:
        await conn.execute(
            """
            INSERT INTO regime_observations
                (symbol, timeframe, ts, regime, confidence, classifier_version,
                 params, features, data_quality, reason, context, ref_type, ref_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (symbol, timeframe, result.ts, result.label, result.confidence,
             result.classifier_version, json.dumps({"version": regime.REGIME_VERSION}),
             json.dumps(result.features, default=str),
             json.dumps(result.data_quality, default=str),
             result.reason, context, ref_type,
             str(ref_id) if ref_id is not None else None))
    except Exception as exc:  # noqa: BLE001 - recording tidak boleh jatuhkan runner
        log(f"regime observation insert failed (non-fatal): {exc!r}")


@dataclass(frozen=True)
class StrategySpec:
    """One strategy the paper runner trades. State lives in paper_state.<state_key>.

    Multipair P2: tiap spek membawa simbol, timeframe kanonik, dan contract
    size-nya sendiri (XAUUSD 100 oz/lot, BTCUSD 1 BTC/lot - t_f2mp1). Default
    = nilai legacy strategi XAUUSD M5 agar spek lama tidak berubah perilaku.

    Isolation (PRD v2.2 §5): bila ``module`` diisi, decide() dijalankan di
    subprocess terisolasi lewat app.supervisor (sandbox + schema validation
    + circuit breaker + lifecycle). None = jalur legacy in-process (dipakai
    test/dry-run; backtest tetap in-process demi kecepatan).
    """

    id: str
    state_key: str
    params_cls: type
    decide: object
    module: str | None = None
    version: str = "0.0.0"
    symbol: str = SYMBOL
    timeframe: str = TIMEFRAME
    tf_seconds: int = 300
    contract_size: float = 100.0
    allowed_regimes: list | None = None  # PRD §6.4; None = baca dari modul


# Legacy compat: london_breakout keeps the original state/mode/params keys.
# Prod specs menjalankan decide() via supervisor sandbox (PRD v2.2 §5).
STRATEGIES: list[StrategySpec] = [
    StrategySpec(LB_STRATEGY_ID, "runner", LBStrategyParams, lb_decide,
                 module="strategies.london_breakout", version=LB_STRATEGY_VERSION),
    StrategySpec(MR_STRATEGY_ID, f"runner_{MR_STRATEGY_ID}", MRStrategyParams,
                 mr_decide, module="strategies.mean_reversion",
                 version=MR_STRATEGY_VERSION),
    StrategySpec(
        BTC_STRATEGY_ID, f"runner_{BTC_STRATEGY_ID}", BTCStrategyParams, btc_decide,
        module="strategies.btc_range_breakout", version=BTC_STRATEGY_VERSION,
        symbol="BTCUSD", timeframe="H1", tf_seconds=3600, contract_size=1.0,
    ),
]
SPEC_BY_ID = {s.id: s for s in STRATEGIES}
SPECS_BY_SYMBOL: dict[str, list[StrategySpec]] = {}
for _spec in STRATEGIES:
    SPECS_BY_SYMBOL.setdefault(_spec.symbol, []).append(_spec)


def symbol_spread_max(symbol: str, settings: dict) -> float:
    """Ambang spread absolut per simbol (A9): symbol_specs, fallback settings."""
    spec = (settings.get("symbol_specs") or {}).get(symbol) or {}
    if spec.get("spread_abs_max_usd") is not None:
        return float(spec["spread_abs_max_usd"])
    return float(settings.get("max_spread", 0.50))


def log(message: str) -> None:
    print(f"[{datetime.now(timezone.utc).isoformat(timespec='seconds')}] {message}",
          file=sys.stderr, flush=True)


def load_params(settings: dict, spec: StrategySpec) -> StrategyParams:
    override = settings.get(f"strategy_params_{spec.id}") or {}
    known = {f for f in spec.params_cls.__dataclass_fields__}
    return spec.params_cls(**{k: v for k, v in override.items() if k in known})


def strategy_mode(settings: dict, spec: StrategySpec) -> str:
    return str(settings.get(f"strategy_mode_{spec.id}", "paper")).lower()


async def degradation_tick(conn, *, spec: StrategySpec, settings: dict,
                           now: datetime) -> str:
    """Evaluasi degradation periodik + status efektif (PRD v2.2 §10).

    return status terkini (NORMAL bila belum pernah dievaluasi). Eskalasi
    dicatat ke log + Telegram (di store); kegagalan evaluasi dilempar ke
    caller untuk diisolasi per strategi.
    """
    params = degradation.load_params(settings)
    last = DEG_LAST_EVAL.get(spec.id)
    if last is None or (now - last).total_seconds() >= params.eval_interval_s:
        DEG_LAST_EVAL[spec.id] = now
        result = await degradation_store.evaluate_strategy(
            conn, strategy_id=spec.id, symbol=spec.symbol,
            timeframe=spec.timeframe, now=now, settings=settings)
        DEG_STATUS[spec.id] = result.status
        if result.escalated:
            log(f"[{spec.id}] degradation "
                f"{result.previous_status} -> {result.status}: "
                f"{result.reason[:200]}")
    return DEG_STATUS.get(spec.id, "NORMAL")


async def db_timezone_offset_h(conn) -> int:
    row = await conn.execute("SELECT current_setting('TimeZone') AS tz")
    name = (await row.fetchone())["tz"]
    now = datetime.now(timezone.utc)
    return int(now.astimezone(ZoneInfo(name)).utcoffset().total_seconds() // 3600)


async def load_candles(conn, *, symbol: str, db_tz_offset_h: int, broker_offset_h: int,
                       now: datetime, timeframe: str = TIMEFRAME, limit: int = CANDLE_LIMIT,
                       tf_seconds: int = 300) -> list[dict]:
    """Closed candles as UTC ISO dicts, oldest first."""
    rows = await conn.execute(
        """
        SELECT ts, open, high, low, close FROM candles
        WHERE symbol = %s AND timeframe = %s
        ORDER BY ts DESC LIMIT %s
        """,
        (symbol, timeframe, limit),
    )
    found = await rows.fetchall()
    out = []
    for row in reversed(found):
        ts_utc = stored_to_utc(row["ts"], db_tz_offset_h, broker_offset_h)
        if ts_utc + timedelta(seconds=tf_seconds) > now:
            continue  # still forming
        out.append({
            "ts": ts_utc.isoformat(),
            "open": float(row["open"]),
            "high": float(row["high"]),
            "low": float(row["low"]),
            "close": float(row["close"]),
            "volume": 0,
        })
    return out


def build_context(*, symbol: str, now: datetime, candles: list[dict], tick: dict,
                  spread_median, fresh: bool, positions: list[dict], trades_today: int,
                  equity: float, settings: dict, max_spread: float | None = None) -> dict:
    if max_spread is None:
        max_spread = symbol_spread_max(symbol, settings)
    return {
        "symbol": symbol,
        "now": now.isoformat(),
        "candles": candles,
        "liquidity": {
            "ts": tick["ts_utc"].isoformat(),
            "bid": tick["bid"],
            "ask": tick["ask"],
            "spread": tick["spread"],
            "spread_median_15m": spread_median,
            "fresh": fresh,
        },
        "positions": positions,
        "trades_today": trades_today,
        "risk": {
            "equity": equity,
            "risk_per_trade": 0.005,
            "max_volume": float(settings.get("max_volume", 0.10)),
            "max_spread": max_spread,
        },
    }


async def run_iteration(conn, state: dict, *, spec: StrategySpec, mode: str,
                        settings: dict, params, tick: dict, candles: list[dict],
                        spread_median, now: datetime, allow_entry: bool,
                        bar: dict | None = None, slippage: float = 0.0,
                        dry: bool = False, regime_result=None) -> list[str]:
    """One decision cycle for one strategy. Mutates ``state`` (balance, position)."""
    logs: list[str] = []
    broker = PaperBroker(force_close_hour_utc=params.force_close_utc)
    bid, ask = float(tick["bid"]), float(tick["ask"])

    pos = PaperPosition(**state["position"]) if state.get("position") else None
    if pos is not None:
        if bar is not None:
            event = broker.on_bar(pos, bar["open"], bar["high"], bar["low"], bar["close"],
                                  float(tick["spread"]), now, slippage=slippage)
        else:
            event = broker.on_price(pos, bid, ask, now)
        if event is not None:
            state["balance"] = round(state["balance"] + event.profit, 2)
            state["position"] = None
            logs.append(
                f"CLOSE {pos.side} {pos.volume} #{pos.order_id} {event.reason} "
                f"@ {event.price:.2f} pnl {event.profit:+.2f} balance {state['balance']:.2f}"
            )
            if not dry:
                await store.close_order(conn, pos.order_id, event.price, event.profit,
                                        event.reason, now)

    open_pnl = unrealized(pos, bid, ask) if pos is not None else 0.0
    equity = round(state["balance"] + open_pnl, 2)

    if allow_entry and pos is None:
        day_start = store.day_start_utc(now)
        trades_today = await store.trades_today(conn, spec.id, day_start, mode=mode)
        context = build_context(
            symbol=spec.symbol, now=now, candles=candles, tick=tick,
            spread_median=spread_median, fresh=True, positions=[],
            trades_today=trades_today, equity=equity, settings=settings,
        )
        if spec.module is not None:
            # Isolation path (PRD v2.2 §5): decide() di subprocess terisolasi,
            # output divalidasi schema, circuit breaker + lifecycle aktif.
            decision = await supervisor.decide(
                conn, strategy_id=spec.id, strategy_version=spec.version,
                module=spec.module, context=context, params=asdict(params),
                symbol=spec.symbol, timeframe=spec.timeframe, source=MODE,
                settings=settings, seed_status="PAPER")
            if decision.rejected:
                logs.append(f"REJECTED by supervisor: {decision.reason}")
                return logs
            intent = None
            if decision.intent is not None:
                it = decision.intent  # OrderIntent tervalidasi (PRD 4.1)
                intent = SimpleNamespace(
                    symbol=it["symbol"], side=it["side"], volume=it["volume"],
                    sl=it["stop_loss"], tp=it["take_profit"],
                    strategy=it["strategy_id"], reason=it.get("reason", ""),
                    sl_distance=it.get("sl_distance") or 0.0,
                    risk_usd=it.get("risk_usd") or 0.0)
        else:
            intent = spec.decide(context, params)  # legacy in-process (test/dry)
        if intent is not None:
            # ── Gate regime (PRD v2.2 §6.2/§6.5) ──────────────────────────
            # Strategi yang mendeklarasikan ALLOWED_REGIMES hanya entry bila
            # label sekarang diizinkan; UNKNOWN selalu blokir. Regime TIDAK
            # mengubah risk limit (PRD §6.4) - ini filter kelayakan entry.
            if regime_result is not None:
                allowed = spec.allowed_regimes
                if allowed is None and spec.module:
                    allowed = regime.allowed_regimes_for(_strategy_module(spec))
                if allowed is None:
                    allowed = []
                if not regime.regime_permits_entry(regime_result.label, allowed):
                    logs.append(
                        f"ENTRY BLOCKED by regime {regime_result.label} "
                        f"(allowed={allowed}): {regime_result.reason}")
                    if not dry:
                        await record_regime(
                            conn, symbol=spec.symbol, timeframe=spec.timeframe,
                            result=regime_result, context="SIGNAL",
                            ref_type="strategy", ref_id=spec.id)
                    return logs
                if not dry:
                    await record_regime(
                        conn, symbol=spec.symbol, timeframe=spec.timeframe,
                        result=regime_result, context="SIGNAL",
                        ref_type="strategy", ref_id=spec.id)
            order = {"symbol": intent.symbol, "side": intent.side, "volume": intent.volume,
                     "sl": intent.sl, "tp": intent.tp}
            tick_age = 0.1 if bar is not None else max(
                (now - tick["ts_utc"]).total_seconds(), 0.0)
            decision = risk_gate(order, RiskContext(
                settings=settings, bid=bid, ask=ask, tick_age_s=tick_age,
                daily_pnl=await store.daily_pnl(conn, mode, day_start),
                orders_last_minute=await store.orders_since(
                    conn, mode, now - timedelta(minutes=1)),
            ))
            if decision.ok:
                entry = ask if intent.side == "BUY" else bid
                if dry:
                    order_id = f"dry-{now.isoformat()}"
                else:
                    order_id = await store.insert_order(
                        conn, mode=mode, intent=intent, entry_price=entry,
                        risk_decision={"ok": True, "reasons": []},
                        reason=intent.reason, opened_at=now)
                    if regime_result is not None:  # PRD §6.4: regime saat ORDER
                        await record_regime(
                            conn, symbol=spec.symbol, timeframe=spec.timeframe,
                            result=regime_result, context="ORDER",
                            ref_type="paper_order", ref_id=order_id)
                state["position"] = asdict(PaperPosition(
                    order_id=str(order_id), side=intent.side, volume=intent.volume,
                    entry_price=entry, sl=intent.sl, tp=intent.tp,
                    opened_at=now, strategy=intent.strategy,
                    contract_size=spec.contract_size))
                logs.append(
                    f"ENTRY {intent.side} {intent.volume} @ {entry:.2f} SL {intent.sl:.2f} "
                    f"TP {intent.tp:.2f} ({intent.reason})"
                )
            else:
                logs.append(f"REJECTED by risk gate: {decision.reasons}")
                if not dry:
                    await store.insert_rejected(
                        conn, mode=mode, intent=intent,
                        risk_decision={"ok": False, "reasons": decision.reasons},
                        reason="risk gate: " + "; ".join(decision.reasons), at=now)
    return logs


async def recover_position(conn, state: dict, mode: str = MODE,
                           strategy: str | None = None,
                           contract_size: float = 100.0) -> None:
    if state.get("position"):
        return
    row = await store.open_position_row(conn, mode, strategy)
    if row:
        state["position"] = {
            "order_id": str(row["id"]), "side": row["side"], "volume": float(row["volume"]),
            "entry_price": float(row["entry_price"]), "sl": float(row["sl"]),
            "tp": float(row["tp"]),
            "opened_at": row["opened_at"] or row["created_at"],
            "strategy": row["strategy"],
            "contract_size": contract_size,
        }
        log(f"recovered open paper position {row['id']} {row['side']} {row['volume']} "
            f"({row['strategy']})")


async def tick_once(conn, states: dict[str, dict]) -> None:
    now = datetime.now(timezone.utc)
    for state in states.values():
        if state.get("paper_start_ts") is None:
            state["paper_start_ts"] = now.isoformat()
    settings = await db.get_settings()
    db_tz_offset_h = await db_timezone_offset_h(conn)
    # Multipair: satu siklus data per simbol (tick, candle, likuiditas),
    # lalu semua strategi simbol itu memutuskan dengan datanya sendiri.
    for symbol, specs in SPECS_BY_SYMBOL.items():
        ticks = await feed.read_ticks_async(TICK_WINDOW_MIN, now, symbol=symbol)
        if not ticks:
            log(f"idle [{symbol}]: no ticks in HFM log yet")
            continue
        market_open = feed.is_market_open(ticks, now)
        tick = feed.latest(ticks)
        first_state = states[specs[0].id]
        if market_open:
            today = now.date().isoformat()
            for spec in specs:
                state = states[spec.id]
                if today not in state.setdefault("days_observed", []):
                    state["days_observed"].append(today)
                    log(f"[{symbol}] paper trading day "
                        f"{len(state['days_observed']) - 1} started: {today} ({spec.id})")
            offset = feed.estimate_offset_hours(ticks)
            if offset is not None and offset != first_state.get("broker_offset_h"):
                for spec in specs:
                    states[spec.id]["broker_offset_h"] = offset
                log(f"[{symbol}] broker offset measured: UTC+{offset:g}")
        offset_h = first_state.get("broker_offset_h")
        if offset_h is None:
            offset_h = broker_utc_offset_hours(now)

        fresh = market_open and (now - tick["ts_utc"]).total_seconds() <= LIQUIDITY_FRESH_S
        spread_median = feed.spread_median_15m(ticks, now)
        candles = await load_candles(
            conn, symbol=symbol, db_tz_offset_h=db_tz_offset_h,
            broker_offset_h=int(offset_h), now=now,
            timeframe=specs[0].timeframe, tf_seconds=specs[0].tf_seconds)

        # ── Regime detection (PRD v2.2 §6): satu klasifikasi per simbol per
        # loop, dipakai semua strategi simbol itu. Definisi SAMA dengan
        # backtest (app.regime murni, PRD §6.5). Kegagalan tidak menghentikan
        # runner (regime_result None = gate tidak aktif siklus ini).
        regime_result = None
        regime_new_bar = False
        if regime_enabled(settings) and candles:
            try:
                tick_rate = len(ticks) / max(TICK_WINDOW_MIN - 1, 1)
                rk = f"{symbol}:{specs[0].timeframe}"
                regime_result = regime.classify(
                    symbol=symbol, now=now, candles=candles,
                    liquidity={"ts": tick["ts_utc"].isoformat(),
                               "spread": tick["spread"],
                               "spread_median_15m": spread_median,
                               "fresh": fresh},
                    params=regime.default_params_for_symbol(symbol),
                    state=REGIME_STATES.get(rk), tick_rate=tick_rate)
                REGIME_STATES[rk] = regime_result.state
                regime_new_bar = (REGIME_RECORDED.get(rk)
                                  != regime_result.state["last_bar_ts"])
                if regime_new_bar:
                    REGIME_RECORDED[rk] = regime_result.state["last_bar_ts"]
                    await record_regime(conn, symbol=symbol,
                                        timeframe=specs[0].timeframe,
                                        result=regime_result, context="PERIODIC")
            except Exception as exc:  # noqa: BLE001 - regime tak boleh jatuhkan runner
                log(f"[{symbol}] regime error (isolated): {exc!r}")
                regime_result = None
                regime_new_bar = False

        # Degradation (PRD §10): status terkini semua strategi (1 query/loop);
        # evaluasi periodik per strategi dilakukan di dalam loop di bawah.
        DEG_STATUS.update(await degradation_store.statuses(conn))
        for spec in specs:
            state = states[spec.id]
            params = load_params(settings, spec)
            try:
                if regime_result is not None and regime_new_bar \
                        and state.get("position"):
                    # PRD §6.4: catat regime selama posisi terbuka (per bar).
                    await record_regime(
                        conn, symbol=spec.symbol, timeframe=spec.timeframe,
                        result=regime_result, context="POSITION",
                        ref_type="paper_order",
                        ref_id=state["position"].get("order_id"))
                # Degradation (PRD §10): evaluasi periodik + gate entry.
                # DEGRADED = tidak boleh tambah risiko baru; HALTED = stop
                # entry baru. Status persist di DB, dibaca ulang per loop.
                try:
                    deg_status = await degradation_tick(
                        conn, spec=spec, settings=settings, now=now)
                except Exception as exc:  # noqa: BLE001 - evaluasi terisolasi
                    log(f"[{spec.id}] degradation evaluation error "
                        f"(isolated): {exc!r}")
                    deg_status = DEG_STATUS.get(spec.id, "NORMAL")
                deg_allowed = degradation.entry_allowed(deg_status)
                if deg_status != DEG_LOGGED.get(spec.id):
                    DEG_LOGGED[spec.id] = deg_status
                    if not deg_allowed:
                        log(f"[{spec.id}] ENTRY BLOCKED by degradation "
                            f"{deg_status}: "
                            f"{degradation.entry_block_reason(deg_status)}")
                logs = await run_iteration(
                    conn, state, spec=spec, mode=MODE, settings=settings,
                    params=params, tick=tick, candles=candles,
                    spread_median=spread_median, now=now,
                    allow_entry=(fresh and strategy_mode(settings, spec) != "off"
                                 and deg_allowed),
                    regime_result=regime_result,
                )
            except Exception as exc:
                # Isolation (PRD 5.4): crash satu strategi tidak menghentikan
                # strategi lain; strategi ini dilewati siklus ini saja.
                log(f"[{spec.id}] iteration error (isolated): {exc!r}")
                logs = []
            await store.save_state(conn, spec.state_key, state)
            for line in logs:
                log(f"[{spec.id}] {line}")
        if not market_open:
            log(f"[{symbol}] market closed (broker clock frozen); last tick {tick['exchange_ts']}")


async def main(once: bool = False) -> None:
    await db.init_pool()
    await db.apply_schema()
    states: dict[str, dict] = {}
    async with db.pool().connection() as conn:
        for spec in STRATEGIES:
            state = await store.load_state(conn, spec.state_key)
            await recover_position(conn, state, strategy=spec.id,
                                   contract_size=spec.contract_size)
            await store.save_state(conn, spec.state_key, state)
            states[spec.id] = state
    log("paper runner started: "
        + " ".join(f"{s.id}(state={s.state_key}, balance={states[s.id]['balance']:.2f})"
                   for s in STRATEGIES))

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop.set)
        except NotImplementedError:
            pass

    while not stop.is_set():
        try:
            async with db.pool().connection() as conn:
                await tick_once(conn, states)
        except Exception as exc:  # keep the runner alive no matter what
            log(f"error: {exc!r}")
        if once:
            break
        try:
            await asyncio.wait_for(stop.wait(), timeout=POLL_S)
        except asyncio.TimeoutError:
            pass
    async with db.pool().connection() as conn:
        for spec in STRATEGIES:
            await store.save_state(conn, spec.state_key, states[spec.id])
    log("paper runner stopped")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Fund2 paper runner (multi-strategy)")
    parser.add_argument("--once", action="store_true", help="run one iteration and exit")
    parser.add_argument("--status", action="store_true", help="print state and exit")
    args = parser.parse_args()

    if args.status:
        async def show_status() -> None:
            await db.init_pool()
            async with db.pool().connection() as conn:
                states = {s.id: await store.load_state(conn, s.state_key)
                          for s in STRATEGIES}
                rows = await store.recent_orders(conn, MODE, limit=10)
            print(json.dumps(states, indent=1, default=str))
            for row in rows:
                print(dict(row))

        asyncio.run(show_status())
    else:
        asyncio.run(main(once=args.once))
