"""Event loop daemon alerts tidak boleh dibekukan baca tick (t_1b2d66ab).

Reproduksi produksi 26 Nov 2026: `paper_check_once` / `candle_check_once`
memanggil `feed.read_ticks` SINKRON di event loop. Selama loop beku, semua
watcher lain yang antre di `psycopg_pool.getconn()` (deadline = monotonic() +
timeout) melempar `PoolTimeout` walau Postgres sehat; `collect_metrics()`
menerjemahkannya jadi `db.available=False` -> SEV-2 `db_unavailable` ->
auto-halt STOP_NEW_ORDERS. Watchdog `STALE (>300s)` juga membunuh daemon
(exit 70) sehingga notifikasi alert mati total.

Test di sini merah pada kode sebelum fix dan hijau sesudahnya:
  1. `paper_check_once` meng-offload probe pasar ke thread (loop tetap jalan),
  2. `feed.read_ticks_async` meng-offload pembacaan tick,
  3. pool `min_size=1, max_size=1` dengan 5 task akuisisi tidak menghasilkan
     `PoolTimeout` saat probe pasar lambat berjalan.
"""
from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone

import pytest
from psycopg_pool import AsyncConnectionPool, PoolTimeout

from app import alerts, config
from paper import feed

SLOW_PROBE_S = 3.0      # > pool timeout: sebelum fix ini memblokir seluruh loop
POOL_TIMEOUT_S = 1.0    # produksi 10 s; diperkecil supaya test cepat & tegas
WAITERS = 5
ACQUIRE_PER_WAITER = 3


class _LoopTicker:
    """Hitung iterasi event loop selama satu operasi (bukti loop tidak beku)."""

    def __init__(self, interval_s: float = 0.02) -> None:
        self.interval_s = interval_s
        self.count = 0
        self._task: asyncio.Task | None = None

    async def _run(self) -> None:
        while True:
            self.count += 1
            await asyncio.sleep(self.interval_s)

    def start(self) -> None:
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await self._task
            self._task = None


async def test_paper_check_once_does_not_block_event_loop(client, monkeypatch):
    """Probe pasar lambat (simulasi read_ticks lama) tidak boleh membekukan loop."""
    calls = {"n": 0}

    def slow_market_open() -> bool:
        calls["n"] += 1
        time.sleep(SLOW_PROBE_S)  # read_ticks 2,8 s pasca-insiden; 3 s > tegas
        return False

    monkeypatch.setattr(alerts, "paper_market_open", slow_market_open)
    monkeypatch.setattr(alerts, "runner_service_status", lambda: "active")

    ticker = _LoopTicker()
    ticker.start()
    try:
        t0 = time.perf_counter()
        state, text = await asyncio.wait_for(
            alerts.paper_check_once({"healthy": None}), timeout=SLOW_PROBE_S + 15
        )
        elapsed = time.perf_counter() - t0
    finally:
        await ticker.stop()

    assert calls["n"] == 1, "paper_check_once wajib memakai paper_market_open"
    assert state["healthy"] is True and text is None  # observasi pertama = baseline
    assert elapsed >= SLOW_PROBE_S * 0.9  # probe memang lambat
    # Loop harus tetap berputar selama probe: 3 s / 20 ms = 150 iterasi.
    assert ticker.count >= 30, f"event loop beku: hanya {ticker.count} iterasi"


async def test_read_ticks_async_offloads_blocking_read(monkeypatch):
    """`read_ticks_async` menjalankan read_ticks (monkeypatch-able) di thread."""
    seen: list[dict] = []

    def slow_read_ticks(minutes, now, symbol=None):
        seen.append({"minutes": minutes, "symbol": symbol})
        time.sleep(0.8)
        return [{"symbol": symbol}]

    monkeypatch.setattr(feed, "read_ticks", slow_read_ticks)

    ticker = _LoopTicker()
    ticker.start()
    try:
        ticks = await asyncio.wait_for(
            feed.read_ticks_async(16, datetime.now(timezone.utc), symbol="XAUUSD"),
            timeout=10,
        )
    finally:
        await ticker.stop()

    assert ticks == [{"symbol": "XAUUSD"}]
    assert seen == [{"minutes": 16, "symbol": "XAUUSD"}]
    assert ticker.count >= 10, f"event loop beku: hanya {ticker.count} iterasi"


async def test_no_pool_timeout_when_market_probe_is_slow(client, monkeypatch):
    """Pool min_size=1: 5 task akuisisi + probe pasar lambat -> tanpa PoolTimeout.

    Sebelum fix, probe pasar sinkron membekukan loop > POOL_TIMEOUT_S sehingga
    semua waiter melempar `PoolTimeout` walau Postgres sehat dan idle.
    """
    monkeypatch.setattr(alerts, "paper_market_open", lambda: (time.sleep(SLOW_PROBE_S), False)[1])
    monkeypatch.setattr(alerts, "runner_service_status", lambda: "active")

    pool = AsyncConnectionPool(
        config.DATABASE_URL, min_size=1, max_size=1,
        timeout=POOL_TIMEOUT_S, open=False,
    )
    await pool.open()
    finished = {"n": 0}
    errors: list[str] = []

    async def waiter() -> None:
        try:
            for _ in range(ACQUIRE_PER_WAITER):
                async with pool.connection() as conn:
                    await conn.execute("SELECT 1")
                finished["n"] += 1
                await asyncio.sleep(0.01)
        except PoolTimeout as exc:  # noqa: PERF203 — kegagalan = data test
            errors.append(f"PoolTimeout: {exc}")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{type(exc).__name__}: {exc}")

    try:
        # Tahan satu-satunya koneksi supaya kelima waiter PASTI antre (bukan
        # kebetulan belum mulai) sebelum probe pasar dijalankan.
        held = await pool.getconn()
        waiters = [asyncio.create_task(waiter()) for _ in range(WAITERS)]
        await asyncio.sleep(0.05)
        assert finished["n"] == 0, "waiter tidak boleh dapat koneksi selagi ditahan"

        probe = asyncio.create_task(alerts.paper_check_once({"healthy": None}))
        await asyncio.sleep(0.05)
        # Post-fix: loop masih hidup -> koneksi dilepas sekarang dan waiter
        # lanjut. Pre-fix: loop beku di dalam probe, pelepasan ini baru jalan
        # setelah > POOL_TIMEOUT_S, jadi waiter melempar PoolTimeout.
        await pool.putconn(held)
        await asyncio.wait_for(probe, timeout=SLOW_PROBE_S + 15)
        await asyncio.wait_for(asyncio.gather(*waiters), timeout=30)
    finally:
        await pool.close()

    assert not errors, errors
    assert finished["n"] == WAITERS * ACQUIRE_PER_WAITER


async def test_candle_check_once_does_not_block_event_loop(client, monkeypatch):
    """Jalur candle_check_once juga memakai probe pasar yang di-offload."""
    def slow_market_open() -> bool:
        time.sleep(SLOW_PROBE_S)
        return False

    monkeypatch.setattr(alerts, "paper_market_open", slow_market_open)

    ticker = _LoopTicker()
    ticker.start()
    try:
        state, _text = await asyncio.wait_for(
            alerts.candle_check_once({"healthy": None}), timeout=SLOW_PROBE_S + 15
        )
    finally:
        await ticker.stop()

    assert state["healthy"] is True  # market tutup -> tidak stale
    assert ticker.count >= 30, f"event loop beku: hanya {ticker.count} iterasi"


# ------------------------------------------------------- diagnosa daemon beku

def test_sigusr1_dump_callable_with_loop_handler_signature(capfd):
    """SIGUSR1 harus benar-benar dump stack untuk KEDUA gaya pemanggilan.

    `loop.add_signal_handler(SIGUSR1, _dump_stacks)` memanggil callback tanpa
    argumen; handler signal klasik mengirim (signum, frame). Versi lama
    mewajibkan dua argumen -> TypeError -> SIGUSR1 tidak pernah menghasilkan
    stack dump tepat saat dipakai mendiagnosa freeze (t_1b2d66ab).
    """
    alerts._dump_stacks()            # gaya add_signal_handler
    alerts._dump_stacks(10, None)    # gaya handler signal klasik
    err = capfd.readouterr().err
    assert err.count("Current thread") >= 2, err[:400]
