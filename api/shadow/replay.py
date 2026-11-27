"""Replay shadow E2E atas data live yang terekam (PRD 9.2 + 9.3).

Memutar ulang tick HFM + candle DB untuk window waktu lampau melalui jalur
produksi yang SAMA dengan runner live (run_iteration + supervisor sandbox +
regime classifier + risk gate + fill konservatif), lalu mencatat hasilnya ke
shadow_runs/shadow_signals dengan label replay terpisah. Dipakai untuk:

  - bukti E2E "sinyal tercatat" tanpa menunggu jendela sesi berikutnya;
  - evaluasi out-of-sample gerbang promosi (PRD 9.3) pada window mana pun
    yang sudah terekam.

Replay BUKAN mode live: `now` iterasi = waktu replay, bukan jam sekarang.
Tripwire OrderLedgerTripwire tetap aktif; shadow tetap tidak menyentuh
orders/bridge_commands/paper_orders.

Run:  .venv/bin/python -m shadow.replay --label lb-replay-d0 \
          --from 2026-11-23T06:55 --to 2026-11-23T12:05 [--step 60] [--module X]
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from app import db, regime
from paper import feed
from strategies.broker_time import broker_utc_offset_hours
from paper.runner import (LIQUIDITY_FRESH_S, TICK_WINDOW_MIN, db_timezone_offset_h,
                          log)
from strategies.broker_time import stored_to_utc
from shadow import store
from shadow.fill import FillModel, fill_model_from_settings
from shadow.loop import OrderLedgerTripwire
from shadow.runner import _decide, code_commit, run_iteration
from shadow.specs import ShadowSpec, load_specs, params_hash

DEFAULT_STEP_S = 60          # resolusi replay (live loop jalan tiap POLL_S=5)


def parse_utc(s: str) -> datetime:
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


async def load_candles_until(conn, *, symbol: str, db_tz_offset_h: int,
                             broker_offset_h: int, now: datetime,
                             timeframe: str, tf_seconds: int,
                             limit: int = 300) -> list[dict]:
    """load_candles dengan cutoff historis untuk replay.

    paper.runner.load_candles mengambil N candle terbaru GLOBAL lalu
    menyaring candle yang masih terbentuk; pada replay `now` berada di
    masa lampau sehingga SEMUA candle terbaru tersaring -> 0 candle ->
    strategi tak pernah sinyal. Versi ini menyaring di SQL berdasarkan
    `now` (true UTC) dengan konversi stored = true_utc - (db_tz - broker).
    """
    cutoff_stored = now - timedelta(
        hours=db_tz_offset_h - broker_offset_h)
    rows = await conn.execute(
        """
        SELECT ts, open, high, low, close FROM candles
        WHERE symbol = %s AND timeframe = %s AND ts <= %s
        ORDER BY ts DESC LIMIT %s
        """,
        (symbol, timeframe, cutoff_stored, limit),
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


def spec_from_settings(label: str, settings: dict, module: str | None = None) -> ShadowSpec:
    """Ambil spec dari settings `shadow_strategies` by label (fallback default)."""
    specs, errors = load_specs(settings)
    for err in errors:
        log(f"shadow spec invalid (skip): {err}")
    for spec in specs:
        if spec.label == label:
            return spec
    if module:  # spec ad-hoc berlabel (dipakai QA, bukan baseline)
        from shadow.specs import _module_strategy_meta, SYMBOL_CONTRACT, SYMBOL_DEFAULT_TF
        sid, ver = _module_strategy_meta(module)
        tf, tf_s = SYMBOL_DEFAULT_TF.get("XAUUSD", ("M5", 300))
        return ShadowSpec(label=label, strategy_id=sid, strategy_version=ver,
                          module=module, symbol="XAUUSD", timeframe=tf,
                          tf_seconds=tf_s, contract_size=SYMBOL_CONTRACT["XAUUSD"])
    raise SystemExit(f"label '{label}' tidak ada di settings shadow_strategies")


async def replay_window(conn, *, spec: ShadowSpec, start: datetime, end: datetime,
                        step_s: int = DEFAULT_STEP_S, settings: dict,
                        fm: FillModel | None = None) -> dict:
    """Putar ulang window [start, end) untuk satu spec; return ringkasan.

    Jalur persis tick_once (loop.py) dengan `now` = waktu replay; tripwire
    di-arm di sini dan diverifikasi di akhir.
    """
    fm = fm or FillModel()
    commit = code_commit()
    state = dict(store.DEFAULT_STATE)
    run_id = await store.ensure_run(
        conn, strategy_id=spec.strategy_id, strategy_version=spec.strategy_version,
        label=spec.label, symbol=spec.symbol, timeframe=spec.timeframe,
        params_hash=params_hash(spec.params), code_commit=commit,
        config={"replay": True,
                "replay_window_utc": [start.isoformat(), end.isoformat()],
                "replay_step_s": step_s,
                "module": spec.module, "params": spec.params,
                "slippage_usd_per_fill": fm.slippage,
                "commission_per_lot_round_usd": fm.commission_per_lot_round_usd})
    trip = OrderLedgerTripwire()
    await trip.arm(conn)

    regime_state: dict = {}
    steps = 0
    day_start = datetime(start.year, start.month, start.day, tzinfo=timezone.utc)
    t = start
    db_tz = await db_timezone_offset_h(conn)
    while t < end:
        ticks = await feed.read_ticks_async(TICK_WINDOW_MIN, t, symbol=spec.symbol)
        t += timedelta(seconds=step_s)
        if not ticks:
            continue
        now = t - timedelta(seconds=step_s)
        market_open = feed.is_market_open(ticks, now)
        tick = feed.latest(ticks)
        if tick is None:  # tak mungkin setelah read_ticks non-empty; jaga tipe
            continue
        fresh = market_open and (now - tick["ts_utc"]).total_seconds() <= LIQUIDITY_FRESH_S
        if state.get("broker_offset_h") is None:
            offset = feed.estimate_offset_hours(ticks)
            state["broker_offset_h"] = offset if offset is not None else \
                broker_utc_offset_hours(now)
        spread_median = feed.spread_median_15m(ticks, now)
        candles = await load_candles_until(
            conn, symbol=spec.symbol, db_tz_offset_h=db_tz,
            broker_offset_h=int(state["broker_offset_h"]), now=now,
            timeframe=spec.timeframe, tf_seconds=spec.tf_seconds)
        regime_result = None
        if str(settings.get("regime_detection_enabled", "on")).lower() != "off" and candles:
            try:
                regime_result = regime.classify(
                    symbol=spec.symbol, now=now, candles=candles,
                    liquidity={"ts": tick["ts_utc"].isoformat(),
                               "spread": tick["spread"],
                               "spread_median_15m": spread_median,
                               "fresh": fresh},
                    params=regime.default_params_for_symbol(spec.symbol),
                    state=regime_state.get("s"),
                    tick_rate=len(ticks) / max(TICK_WINDOW_MIN - 1, 1))
                regime_state["s"] = regime_result.state
            except Exception as exc:  # noqa: BLE001 - regime tak boleh jatuhkan
                log(f"[replay:{spec.label}] regime error (isolated): {exc!r}")
                regime_result = None
        steps += 1
        try:
            logs = await run_iteration(
                conn, state, spec=spec, run_id=run_id, settings=settings,
                params=None, tick=tick, candles=candles,
                spread_median=spread_median, now=now, allow_entry=fresh,
                regime_result=regime_result, code_commit_hash=commit, fill_model=fm)
        except Exception as exc:  # noqa: BLE001 - isolasi versi
            log(f"[replay:{spec.label}] iteration error (isolated): {exc!r}")
            logs = []
        for line in logs:
            log(f"[replay:{spec.label}] {line}")
        # Commit per langkah: transaksi pendek seperti loop live (pool commit
        # per iterasi) — jangan memegang AccessShare candles bermenit-menit
        # (insiden 24 Nov: transaksi replay satu memblokir CREATE PARTITION
        # candle-rollup dan seluruh pembaca candle).
        await conn.commit()
    await store.save_state(conn, spec.state_key, state)
    stats = await store.run_stats(conn, run_id, day_start)
    await store.update_run_metrics(conn, run_id, stats)
    tripwire_ok = await trip.verify(conn)
    await conn.execute(
        "UPDATE shadow_runs SET status = 'COMPLETED', completed_at = now(), "
        "note = %s WHERE run_id = %s",
        (f"E2E replay live data {start.isoformat()}..{end.isoformat()} "
         f"steps={steps} tripwire={'OK' if tripwire_ok else 'VIOLATED'}", run_id))
    await conn.commit()
    return {"run_id": str(run_id), "steps": steps, "stats": stats,
            "tripwire_ok": tripwire_ok, "sim_balance": state["sim_balance"],
            "code_commit": commit}


async def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="Replay shadow E2E atas data live terekam (PRD 9.2/9.3)")
    parser.add_argument("--label", required=True, help="label unik run replay")
    parser.add_argument("--from", dest="start", required=True, help="UTC ISO start")
    parser.add_argument("--to", dest="end", required=True, help="UTC ISO end")
    parser.add_argument("--step", type=int, default=DEFAULT_STEP_S)
    parser.add_argument("--module", default=None,
                        help="module strategi bila label bukan baseline settings")
    args = parser.parse_args()

    await db.init_pool()
    await db.apply_schema()
    settings = await db.get_settings()
    spec = spec_from_settings(args.label, settings, module=args.module)
    start, end = parse_utc(args.start), parse_utc(args.end)
    log(f"replay {spec.label} ({spec.strategy_id}) {start.isoformat()}..{end.isoformat()} "
        f"step={args.step}s MODE=SHADOW tanpa order")
    async with db.pool().connection() as conn:
        summary = await replay_window(
            conn, spec=spec, start=start, end=end, step_s=args.step,
            settings=settings, fm=fill_model_from_settings(settings))
    print(f"REPLAY {spec.label}: {summary}")
    return 0 if summary["tripwire_ok"] else 9


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
