"""Job rollup candle server-side: rantai M1->M5->M15/H1->H4->D1.

Kartu candle pipeline: rantai bertingkat (bukan hanya M1->M5) supaya H4/D1
tidak lagi bergantung seed EA CopyRates yang bisa berhenti. Sumber setiap
langkah hanya bar volume > 0, hasil ditulis source='rollup', dan bar native
EA (source='ea') tidak pernah ditimpa.


Dijalankan sebagai systemd user service fund2-candle-rollup, atau manual:
  .venv/bin/python -m app.candle_rollup            # daemon, siklus tiap 60 dtk
  .venv/bin/python -m app.candle_rollup --once     # auto-heal/backfill sekali jalan
  .venv/bin/python -m app.candle_rollup --once --since 2026-11-20T17:00

Sengaja proses TERPISAH dari fund2-api (pola yang sama dengan
fund2-alerts): perbaikan feed M5 bisa live tanpa me-restart API, dan
API yang restart kemudian tetap aman karena rollup berbasis upsert
idempotent (dua penulis menghasilkan baris yang sama).

Sumber data dibaca dari tabel candles (bar M1 tick, kunci true UTC),
bukan dari memori pipeline, jadi job ini bisa jalan di proses mana pun.
Kunci ts M5 hasil rollup mengikuti konvensi candle fund2 (jam broker
dirender di timezone sesi DB, sama dengan seed EA) supaya series M5
meneruskan history seed EA dan dibaca benar oleh paper runner maupun
engine backtest.
"""
from __future__ import annotations

import asyncio
import sys
from datetime import datetime, timezone

from . import db
from .ingest import rollup_cycle, rollup_m1_to_m5

CYCLE_S = 60.0


def log(message: str) -> None:
    print(f"[{datetime.now(timezone.utc).isoformat(timespec='seconds')}] {message}",
          flush=True)


async def once(since: datetime | None, until: datetime | None) -> int:
    """Sekali jalan: auto-heal (since None) atau window eksplisit."""
    await db.init_pool()
    try:
        async with db.pool().connection() as conn:
            if since is None:
                return await rollup_cycle(conn)
            return await rollup_m1_to_m5(conn, since=since, until=until)
    finally:
        await db.close_pool()


async def daemon() -> None:
    await db.init_pool()
    try:
        log(f"candle-rollup daemon aktif (siklus {CYCLE_S:.0f}s)")
        while True:
            try:
                async with db.pool().connection() as conn:
                    n = await rollup_cycle(conn)
                if n:
                    log(f"rollup rantai M1->M5->M15/H1->H4->D1: {n} bar baru")
            except Exception as exc:  # loop harus hidup
                log(f"rollup error (retry {CYCLE_S:.0f}s): {exc!r}")
            await asyncio.sleep(CYCLE_S)
    finally:
        await db.close_pool()


def _parse_arg(name: str) -> datetime | None:
    if name not in sys.argv:
        return None
    i = sys.argv.index(name)
    if i + 1 >= len(sys.argv):
        raise SystemExit(f"{name} butuh nilai ISO, mis. 2026-11-20T17:00")
    return datetime.fromisoformat(sys.argv[i + 1]).replace(tzinfo=timezone.utc)


def main() -> None:
    if "--once" in sys.argv:
        n = asyncio.run(once(_parse_arg("--since"), _parse_arg("--until")))
        print(f"[rollup] selesai: {n} bar ditulis (rantai M1->M5->M15/H1->H4->D1)",
              flush=True)
    else:
        asyncio.run(daemon())


if __name__ == "__main__":
    main()
