# Copyright (c) 2026 Lumine. All rights reserved.
"""FastAPI application factory for the Lumine public REST API."""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from datetime import UTC, datetime
from decimal import Decimal
from functools import partial
from typing import Any
from uuid import uuid4

import redis.asyncio as redis  # async client — await redis.from_url() valid
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import Response
from starlette.exceptions import HTTPException as StarletteHTTPException

from lumine.api.middleware.envelope import (
    CommonEnvelopeMiddleware,
    http_exception_handler,
    lumine_exception_handler,
    validation_exception_handler,
)
from lumine.api.middleware.idempotency import IdempotencyMiddleware
from lumine.api.middleware.logging import RequestLoggingMiddleware
from lumine.api.routers import (
    admin,
    journal,
    lineage,
    market,
    orders,
    portfolio,
    rpc,
    streams,
    workflows,
)
from lumine.api.routers.auth import router as auth_router
from lumine.api.routers.auth import seed_bootstrap_users
from lumine.api.sse.publisher import SSEPublisher
from lumine.monitoring.metrics import default_registry
from lumine.rpc.worker import run_worker
from lumine.shared.config import Settings, get_settings
from lumine.shared.errors import LumineError
from lumine.trading.market_service import MarketService
from lumine.trading.mt5_bridge import MT5Bridge, ResultMessage
from lumine.trading.position_sync import PositionSyncWorker

_app_state: dict[str, object] = {}

# B4 live bars: builder in-memory — ticks EA → bar 1m berjalan (bucket per
# menit). Flush worker upsert ke bars_1m tiap 60s + agregasi 5m.
# Format: {symbol: {"ts": datetime, "open": f, "high": f, "low": f,
#                   "close": f, "volume": f}}
_bar_builder: dict[str, dict[str, Any]] = {}


async def _tick_worker() -> None:
    """Consume mt5:ticks (EA LPUSH via proxy) → MarketService.update_tick.

    TANPA worker ini MarketService._ticks selalu kosong → SSE
    /streams/market-data dapat stream_open tapi TIDAK PERNAH emit
    tick_update (get_quote → None) → chart frontend tidak update.
    """
    from lumine.shared.config import get_settings as _gs

    try:
        r = await redis.from_url(_gs().redis_url)
    except Exception:
        return
    market_service = _app_state.get("market_service")
    if market_service is None:
        return
    while True:
        try:
            item = await r.brpop("mt5:ticks", timeout=5)
            if not item:
                continue
            _, payload = item
            data = json.loads(payload)
            symbol = str(data["symbol"]).upper()
            bid = float(data["bid"])
            ask = float(data["ask"])
            await market_service.update_tick(
                symbol,
                bid,
                ask,
                volume=float(data.get("volume", 0.0)),
            )
            # B4: bangun bar 1m live dari tick (untuk flush ke bars_1m)
            _update_bar_builder(symbol, bid, ask, float(data.get("volume", 0.0)))
        except Exception:
            pass  # transient / malformed tick — skip


def _update_bar_builder(symbol: str, bid: float, ask: float, volume: float) -> None:
    """Update bar 1m berjalan (bucket per menit UTC)."""
    now = datetime.now(UTC)
    minute_ts = now.replace(second=0, microsecond=0)
    bar = _bar_builder.get(symbol)
    if bar is None or bar["ts"] != minute_ts:
        _bar_builder[symbol] = {
            "ts": minute_ts,
            "symbol": symbol,
            "open": bid,
            "high": max(bid, ask),
            "low": min(bid, ask),
            "close": bid,
            "volume": volume,
        }
    else:
        bar["high"] = max(bar["high"], bid, ask)
        bar["low"] = min(bar["low"], bid, ask)
        bar["close"] = bid
        bar["volume"] = bar.get("volume", 0.0) + volume


async def _bar_flush_worker() -> None:
    """B4: flush bar 1m selesai → bars_1m; agregasi 5m dari bars_1m.

    Tiap 60s: bar yang umurnya >90s dianggap selesai → upsert bars_1m
    (ON CONFLICT (ts, symbol) DO UPDATE) + bangun bars_5m agregat dari
    bars_1m (ON CONFLICT DO NOTHING — bar 5m yang sudah ada tidak diubah).
    """
    from sqlalchemy import func, select
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    from lumine.data.models import Bars1M, Bars5M
    from lumine.data.session import get_sessionmaker

    while True:
        await asyncio.sleep(60)
        try:
            now = datetime.now(UTC)
            ready = [
                bar
                for bar in _bar_builder.values()
                if (now - bar["ts"]).total_seconds() > 90
            ]
            if not ready:
                continue
            async with get_sessionmaker()() as session:
                for bar in ready:
                    stmt = (
                        select(Bars1M)
                        .where(Bars1M.ts == bar["ts"], Bars1M.symbol == bar["symbol"])
                    )
                    existing = (await session.execute(stmt)).scalar_one_or_none()
                    if existing is None:
                        session.add(
                            Bars1M(
                                ts=bar["ts"],
                                symbol=bar["symbol"],
                                open=Decimal(str(bar["open"])),
                                high=Decimal(str(bar["high"])),
                                low=Decimal(str(bar["low"])),
                                close=Decimal(str(bar["close"])),
                                volume=Decimal(str(bar.get("volume", 0))),
                                source="mt5-live",
                            )
                        )
                    else:
                        existing.high = max(existing.high, Decimal(str(bar["high"])))
                        existing.low = min(existing.low, Decimal(str(bar["low"])))
                        existing.close = Decimal(str(bar["close"]))
                        existing.volume = existing.volume + Decimal(str(bar.get("volume", 0)))
                        session.add(existing)
                    _bar_builder.pop(bar["symbol"], None)

                # Agregasi 5m dari bars_1m (5 bar per bucket; DO NOTHING —
                # hanya bar 5m baru yang di-insert)
                five_min_bucket = now.replace(
                    minute=(now.minute // 5) * 5, second=0, microsecond=0
                )
                agg_rows = (
                    await session.execute(
                        select(
                            func.date_trunc("hour", Bars1M.ts) + func.interval("5 min") * func.floor(
                                func.extract("minute", Bars1M.ts) / 5
                            ),
                            Bars1M.symbol,
                            func.min(Bars1M.open),
                            func.max(Bars1M.high),
                            func.min(Bars1M.low),
                            func.max(Bars1M.close),
                            func.sum(Bars1M.volume),
                        )
                        .where(Bars1M.ts >= five_min_bucket - func.interval("1 hour"))
                        .group_by(
                            func.date_trunc("hour", Bars1M.ts)
                            + func.interval("5 min")
                            * func.floor(func.extract("minute", Bars1M.ts) / 5),
                            Bars1M.symbol,
                        )
                    )
                ).all()
                if agg_rows:
                    five_rows = []
                    for ts5, symbol, o, h, lo, c, v in agg_rows:
                        five_rows.append(
                            {
                                "ts": ts5,
                                "symbol": symbol,
                                "open": o,
                                "high": h,
                                "low": lo,
                                "close": c,
                                "volume": v,
                                "source": "mt5-live",
                            }
                        )
                    stmt = pg_insert(Bars5M.__table__).values(five_rows)
                    stmt = stmt.on_conflict_do_nothing(
                        index_elements=["ts", "symbol"]
                    )
                    await session.execute(stmt)
                await session.commit()
                if ready:
                    print(f"[BARS] flushed {len(ready)} bar 1m live", flush=True)
        except Exception:
            pass  # transient — skip cycle


async def _handle_order_fill(result: ResultMessage, sse_publisher: object) -> None:
    """MT5 result → SSE order-fill + sync status ke DB (FILLED/REJECTED)."""
    await sse_publisher.publish_order_fill(
        order_id=result.order_id,
        status=result.status,
        fill_price=result.fill_price or 0.0,
        fill_volume=result.fill_volume or 0.0,
        mt5_ticket=result.ticket,
    )
    try:
        from lumine.data.repositories import OrderRepository
        from lumine.data.session import get_sessionmaker

        async with get_sessionmaker()() as session:
            repo = OrderRepository(session)
            if result.status == "FILLED":
                await repo.update_status(
                    result.order_id,
                    status="filled",
                    filled_volume=Decimal(str(result.fill_volume or 0)),
                    mt5_ticket=result.ticket,
                    fill_price=Decimal(str(result.fill_price or 0)),
                )
            elif result.status == "REJECTED":
                await repo.update_status(
                    result.order_id,
                    status="rejected",
                    rejected_reason=result.error or "rejected by MT5",
                )
    except Exception:  # pragma: no cover — DB transient
        pass


async def _seed_worker() -> None:
    """Seed history worker: consume mt5:seed_bars (EA CopyRates)
    → insert ke tabel bars_* (B-08 fondasi: TCA backfill butuh history).
    """
    from lumine.data.models import Bars1D, Bars1H, Bars1M, Bars4H, Bars5M
    from lumine.data.session import get_sessionmaker
    from lumine.shared.config import get_settings as _gs

    bar_models = {"1m": Bars1M, "5m": Bars5M, "1h": Bars1H, "4h": Bars4H, "1d": Bars1D}
    try:
        r = await redis.from_url(_gs().redis_url)
    except Exception:
        return
    while True:
        try:
            item = await r.brpop("mt5:seed_bars", timeout=5)
            if not item:
                continue
            _, payload = item
            data = json.loads(payload)
            model = bar_models.get(data.get("timeframe", ""))
            if model is None:
                continue
            async with get_sessionmaker()() as session:
                rows = [
                    model(
                        ts=datetime.fromtimestamp(int(b["ts"]), UTC),
                        symbol=str(data["symbol"]).upper(),
                        open=Decimal(str(b["open"])),
                        high=Decimal(str(b["high"])),
                        low=Decimal(str(b["low"])),
                        close=Decimal(str(b["close"])),
                        volume=Decimal(str(b["volume"])),
                        source="mt5",
                    )
                    for b in data.get("bars", [])
                ]
                if rows:
                    from sqlalchemy.dialects.postgresql import insert as pg_insert

                    table = model.__table__
                    stmt = pg_insert(table).values(
                        [
                            {
                                "ts": r.ts,
                                "symbol": r.symbol,
                                "open": r.open,
                                "high": r.high,
                                "low": r.low,
                                "close": r.close,
                                "volume": r.volume,
                                "source": "mt5",
                            }
                            for r in rows
                        ]
                    )
                    stmt = stmt.on_conflict_do_nothing(
                        index_elements=[c.name for c in table.primary_key.columns]
                    )
                    await session.execute(stmt)
                    await session.commit()
                    print(
                        f"[SEED] {data.get('symbol')} {data.get('timeframe')} +{len(rows)} bars",
                        flush=True,
                    )
        except Exception:
            pass  # duplicate PK / transient — skip, tetap jalan


async def _decision_scheduler() -> None:
    """G2: auto-run decision cycle tiap 5 menit saat market open.

    Committee feed & signals hidup TANPA manual trigger. Market libur
    (weekend gap) → skip. Lock Redis (nx, 240s) mencegah tumpang tindih
    kalau cycle sebelumnya masih jalan atau user trigger manual.
    """
    from lumine.api.routers.streams import _market_status
    from lumine.data.redis_client import get_redis
    from lumine.rpc.queue import enqueue_command

    while True:
        try:
            status = _market_status()
            if status["open"]:
                r = await get_redis()
                lock = await r.set("lumine:decision_cycle_lock", "1", nx=True, ex=240)
                if lock:
                    await enqueue_command("run_decision_cycle", {"reason": "scheduler"})
                    print("decision_scheduler: cycle triggered", flush=True)
        except Exception as exc:  # scheduler tidak boleh mati
            print(f"decision_scheduler error: {type(exc).__name__}: {str(exc)[:200]}", flush=True)
        await asyncio.sleep(300)


async def _deals_worker() -> None:
    """B1: consume mt5:deals (history deals EA snapshot) → sinkronisasi orders.

    Setiap deal MT5 di-upsert ke tabel orders (status filled, dedupe by
    mt5_ticket). Ini memberi backend visibility penuh atas trade journal
    MT5 (deal history) — tidak hanya order yang lewat command bridge.
    Fill ledger (fills) tidak disentuh: row fills butuh lineage_records
    hash-chain (pipeline decision); deal MT5 bukan decision pipeline.
    """
    from lumine.data.models import Order
    from lumine.data.session import get_sessionmaker
    from lumine.shared.config import get_settings as _gs

    try:
        r = await redis.from_url(_gs().redis_url)
    except Exception:
        return
    while True:
        try:
            item = await r.brpop("mt5:deals", timeout=5)
            if not item:
                continue
            _, payload = item
            data = json.loads(payload)
            deals = data.get("deals", [])
            if not deals:
                continue
            async with get_sessionmaker()() as session:
                from sqlalchemy import select

                inserted = 0
                for d in deals:
                    try:
                        ticket = int(d["ticket"])
                    except (KeyError, TypeError, ValueError):
                        continue
                    existing = (
                        await session.execute(
                            select(Order).where(Order.mt5_ticket == ticket)
                        )
                    ).scalar_one_or_none()
                    if existing is not None:
                        continue
                    ts = datetime.fromtimestamp(int(d.get("time", 0)), UTC)
                    side = "sell" if int(d.get("type", 0)) == 1 else "buy"
                    session.add(
                        Order(
                            order_id=uuid4(),
                            portfolio_id="default",
                            symbol=str(d.get("symbol", "XAUUSD")).upper(),
                            side=side,
                            order_type="market",
                            volume=Decimal(str(d.get("volume", 0))),
                            price=Decimal(str(d.get("price", 0))),
                            status="filled",
                            filled_volume=Decimal(str(d.get("volume", 0))),
                            mt5_ticket=ticket,
                            created_at=ts,
                            updated_at=ts,
                        )
                    )
                    inserted += 1
                await session.commit()
                if inserted:
                    print(f"[DEALS] +{inserted} orders (filled) dari snapshot MT5", flush=True)
        except Exception:
            pass  # transient — skip, tetap jalan


@asynccontextmanager
async def _lifespan(_app: FastAPI) -> AsyncIterator[None]:  # noqa: C901, PLR0915 — infra init
    """Application lifespan: initialize trading infrastructure."""
    settings = get_settings()
    # Seed bootstrap users (superadmin/admin/trader) idempotently. Best
    # effort: never blocks startup when the DB is briefly unavailable.
    await seed_bootstrap_users(settings)

    # Initialize MarketService for tick caching
    market_service = MarketService()
    _app_state["market_service"] = market_service

    # Initialize SSEPublisher
    sse_publisher = SSEPublisher(market_service)
    _app_state["sse_publisher"] = sse_publisher

    # Start SSE heartbeat
    await sse_publisher.start_heartbeat()

    # Initialize MT5Bridge if Redis configured
    if settings.redis_url:
        mt5_bridge = await MT5Bridge.from_url(settings.redis_url)
        _app_state["mt5_bridge"] = mt5_bridge

        # Wire MT5Bridge results to SSEPublisher + DB sync
        mt5_bridge.on_result(partial(_handle_order_fill, sse_publisher=sse_publisher))  # type: ignore[arg-type]
        await mt5_bridge.start()

        _app_state["seed_worker"] = asyncio.create_task(_seed_worker())
        _app_state["tick_worker"] = asyncio.create_task(_tick_worker())
        # B4: bar 1m/5m live dari ticks (flush tiap 60s)
        _app_state["bar_flush_worker"] = asyncio.create_task(_bar_flush_worker())

    # Initialize PositionSyncWorker if database pool available
    pool = getattr(settings, "database_url", None)
    if pool:
        # B1: PositionSyncWorker sekarang consume mt5:positions (snapshot EA)
        # → upsert tabel positions. Interval 10s (match EA snapshot cadence).
        worker = await PositionSyncWorker.from_pool(pool, market_service, interval_seconds=10.0)
        _app_state["position_sync_worker"] = worker
        await worker.start()

    # B1: consume mt5:deals (history deals EA) → sinkronisasi fills/journal.
    if settings.redis_url:
        deals_task = asyncio.create_task(_deals_worker())
        _app_state["deals_worker_task"] = deals_task

    # G2: decision cycle scheduler — auto-run tiap 5 menit saat market open.
    if settings.redis_url:
        sched_task = asyncio.create_task(_decision_scheduler())
        _app_state["decision_scheduler_task"] = sched_task

    # RPC worker (B-04): consume the rpc:commands stream.
    if settings.redis_url:
        rpc_task = asyncio.create_task(run_worker(sse_publisher, settings))
        _app_state["rpc_worker_task"] = rpc_task

    yield

    # Cleanup on shutdown
    await sse_publisher.stop_heartbeat()
    bridge = _app_state.get("mt5_bridge")
    if bridge:
        await bridge.stop()  # type: ignore[union-attr]
    worker = _app_state.get("position_sync_worker")
    if worker:
        await worker.stop()  # type: ignore[union-attr]
    rpc_task = _app_state.get("rpc_worker_task")
    if rpc_task:
        rpc_task.cancel()  # type: ignore[union-attr]
        with suppress(asyncio.CancelledError):
            await rpc_task  # type: ignore[union-attr]
    deals_task = _app_state.get("deals_worker_task")
    if deals_task:
        deals_task.cancel()  # type: ignore[union-attr]
        with suppress(asyncio.CancelledError):
            await deals_task  # type: ignore[union-attr]
    bar_task = _app_state.get("bar_flush_worker")
    if bar_task:
        bar_task.cancel()  # type: ignore[union-attr]
        with suppress(asyncio.CancelledError):
            await bar_task  # type: ignore[union-attr]
    sched_task = _app_state.get("decision_scheduler_task")
    if sched_task:
        sched_task.cancel()  # type: ignore[union-attr]
        with suppress(asyncio.CancelledError):
            await sched_task  # type: ignore[union-attr]


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build and configure the FastAPI application."""
    app = FastAPI(
        title="Lumine API",
        description="Institutional AI-native quantitative hedge fund API",
        version="0.1.0",
        lifespan=_lifespan,
    )

    app.add_middleware(CommonEnvelopeMiddleware)
    # Added last → outermost: idempotency sees the already-enveloped
    # response (error-contract.md:178-189).
    app.add_middleware(IdempotencyMiddleware)
    # Added last → outermost: request logging observes every response,
    # including idempotent replays, and echoes trace_id as X-Request-ID.
    app.add_middleware(RequestLoggingMiddleware)

    if settings is not None:
        app.dependency_overrides[get_settings] = lambda: settings

    app.add_exception_handler(LumineError, lumine_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    # Register under the base class: routing and rate-limit middleware raise
    # starlette.exceptions.HTTPException, which an MRO lookup would not match
    # against a handler keyed to the fastapi subclass.
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)

    # Phase 9 rest-api.md: URL-prefix versioning — every domain router is
    # mounted under /api/v1. /health stays at the root (infra probe).
    for router in (
        portfolio.router,
        orders.router,
        workflows.router,
        lineage.router,
        market.router,
        journal.router,
        streams.router,
        admin.router,
        rpc.router,
    ):
        app.include_router(router, prefix="/api/v1")

    # First-party session auth (replaces Authelia/Keycloak). Mounted at
    # /api/auth (outside /api/v1) so Caddy forward_auth can target
    # /api/auth/verify and the SPA can call /api/auth/me without HMAC.
    app.include_router(auth_router, prefix="/api")

    @app.get("/health", include_in_schema=False)
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/metrics", include_in_schema=False)
    async def metrics() -> Response:
        """Prometheus text exposition (B-02). Scrape via loopback/caddy ACL."""
        registry = default_registry
        registry.set_gauge("lumine_process_uptime_seconds", time.monotonic())
        return Response(
            content=registry.render_prometheus(), media_type="text/plain; version=0.0.4"
        )

    return app
