"""Entrypoint `python -m shadow.runner`: main loop + tripwire + CLI."""
from __future__ import annotations

import asyncio
import signal

from app import db
from paper.runner import POLL_S, log
from shadow import store
from shadow.fill import fill_model_from_settings
from shadow.loop import OrderLedgerTripwire, tick_once
from shadow.runner import code_commit, shadow_enabled
from shadow.specs import load_specs, params_hash


async def main(once: bool = False) -> int:
    await db.init_pool()
    await db.apply_schema()
    settings = await db.get_settings()
    if not shadow_enabled(settings):
        log("shadow runner: disabled by settings shadow_enabled; exit")
        return 0
    specs, errors = load_specs(settings)
    for err in errors:
        log(f"shadow spec invalid (skip): {err}")
    if not specs:
        log("shadow runner: no valid spec; exit")
        return 0
    commit = code_commit()
    fm = fill_model_from_settings(settings)
    trip = OrderLedgerTripwire(
        strategy_ids=[s.strategy_id for s in specs])

    states, run_ids = {}, {}
    async with db.pool().connection() as conn:
        await trip.arm(conn)  # tripwire: ledger order sebelum mulai
        for spec in specs:
            state = await store.load_state(conn, spec.state_key)
            states[spec.label] = state
            run_ids[spec.label] = await store.ensure_run(
                conn, strategy_id=spec.strategy_id,
                strategy_version=spec.strategy_version, label=spec.label,
                symbol=spec.symbol, timeframe=spec.timeframe,
                params_hash=params_hash(spec.params), code_commit=commit,
                config={"module": spec.module, "params": spec.params,
                        "slippage_usd_per_fill": fm.slippage,
                        "commission_per_lot_round_usd":
                            fm.commission_per_lot_round_usd})
    log("shadow runner started (MODE=SHADOW, TANPA order ke broker): "
        + " ".join(f"{s.label}(run={str(run_ids[s.label])[:8]}, "
                   f"hash={params_hash(s.params)})"
                   for s in specs) + f" code={commit}")

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop.set)
        except NotImplementedError:
            pass

    exit_code = 0
    while not stop.is_set():
        try:
            async with db.pool().connection() as conn:
                await tick_once(conn, states, specs, run_ids, settings, fm, commit)
                if not await trip.verify(conn):
                    exit_code = 9  # pelanggaran PRD 9.2: ledger order berubah
                    break
        except Exception as exc:  # noqa: BLE001 - runner tetap hidup
            log(f"shadow error: {exc!r}")
        if once:
            break
        try:
            await asyncio.wait_for(stop.wait(), timeout=POLL_S)
        except asyncio.TimeoutError:
            pass
    async with db.pool().connection() as conn:
        for spec in specs:
            await store.save_state(conn, spec.state_key, states[spec.label])
        ok = await trip.verify(conn)
    log(f"shadow runner stopped (tripwire {'OK' if ok else 'VIOLATED'})")
    return exit_code if not ok else exit_code


def cli() -> None:
    import argparse
    import json

    parser = argparse.ArgumentParser(
        description="Fund2 shadow runner (sinyal live TANPA order, PRD v2.2 §9)")
    parser.add_argument("--once", action="store_true",
                        help="run one iteration and exit")
    parser.add_argument("--status", action="store_true",
                        help="print shadow states + recent signals and exit")
    args = parser.parse_args()

    if args.status:
        async def show_status() -> None:
            await db.init_pool()
            settings = await db.get_settings()
            specs, _ = load_specs(settings)
            async with db.pool().connection() as conn:
                states = {s.label: await store.load_state(conn, s.state_key)
                          for s in specs}
                print(json.dumps(states, indent=1, default=str))
                for s in specs:
                    run = await conn.execute(
                        "SELECT run_id FROM shadow_runs WHERE strategy_id=%s AND "
                        "label=%s AND status='RUNNING' ORDER BY created_at DESC "
                        "LIMIT 1", (s.strategy_id, s.label))
                    row = await run.fetchone()
                    if row:
                        for r in await store.recent_signals(conn, row["run_id"], 10):
                            print(dict(r))

        asyncio.run(show_status())
    else:
        raise SystemExit(asyncio.run(main(once=args.once)))


if __name__ == "__main__":
    cli()
