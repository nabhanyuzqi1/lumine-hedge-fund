"""Backtest scheduler (19 Aug 2026 — P0 learning loop).

Menjalankan master backtest secara TERJADWAL untuk profil aktif, sehingga
learning digest (pola historis) selalu fresh dan di-inject ke analyst prompt
per cycle — menutup loop:

    research -> backtest -> learning digest -> analyst prompt -> decision -> outcome
        ^                                                                    |
        +------------------------------ (ulang terus) ----------------------+

Jangan ubah strategi production otomatis: hasil disimpan ke backtest_runs
(observe), digest di-inject (learn), perbaikan prompt/strategi tetap lewat
proposal manual (validate -> approve -> deploy).
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

logger = logging.getLogger("lumine.backtest.scheduler")

# Default 6 jam; env BACKTEST_SCHEDULE_SECONDS bisa override (test pakai kecil).
DEFAULT_INTERVAL_SECONDS = 6 * 3600


async def run_backtest_scheduler(
    *,
    get_sessionmaker: Any,
    get_redis: Any,
    interval_seconds: int | None = None,
) -> None:
    """Lifespan task: jalankan master backtest berkala untuk profil aktif."""
    from lumine.backtest.master import run_master_backtest

    interval = interval_seconds or DEFAULT_INTERVAL_SECONDS

    while True:
        try:
            r = await get_redis()
            # 1. Profil aktif (hot-swap via Redis, tanpa restart)
            from lumine.trading.profiles import get_active_profile

            profile = await get_active_profile(r)
            profile_id = profile.get("id", "scalping_1m")
            timeframe = profile.get("timeframe", "1h")

            # 2. Jalankan backtest 1 tahun + persist
            async with get_sessionmaker()() as session:
                result = await run_master_backtest(
                    session,
                    profile_id=profile_id,
                    timeframe=timeframe,
                    persist=True,
                )

            m = result["metrics"]
            logger.info(
                "[BACKTEST-SCHED] %s (%s) done: return=%.2f%% dd=%.2f%% trades=%d win=%.1f%%",
                profile_id,
                timeframe,
                m["total_return_pct"],
                m["max_drawdown_pct"],
                m["trade_count"],
                m["win_rate_pct"],
            )
        except Exception:  # nosec B110 — scheduler tidak boleh mati
            logger.exception("backtest scheduler error")

        await asyncio.sleep(interval)
