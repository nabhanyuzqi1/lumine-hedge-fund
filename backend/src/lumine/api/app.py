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
            await market_service.update_tick(
                str(data["symbol"]).upper(),
                float(data["bid"]),
                float(data["ask"]),
                volume=float(data.get("volume", 0.0)),
            )
        except Exception:
            pass  # transient / malformed tick — skip


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
    from lumine.data.models import Bars1D, Bars1H, Bars1M
    from lumine.data.session import get_sessionmaker
    from lumine.shared.config import get_settings as _gs

    bar_models = {"1m": Bars1M, "5m": None, "1h": Bars1H, "4h": None, "1d": Bars1D}
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
                    session.add_all(rows)
                    await session.commit()
                    print(
                        f"[SEED] {data.get('symbol')} {data.get('timeframe')} +{len(rows)} bars",
                        flush=True,
                    )
        except Exception:
            pass  # duplicate PK / transient — skip, tetap jalan


@asynccontextmanager
async def _lifespan(_app: FastAPI) -> AsyncIterator[None]:
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

    # Initialize PositionSyncWorker if database pool available
    pool = getattr(settings, "database_url", None)
    if pool:
        worker = await PositionSyncWorker.from_pool(pool, market_service, interval_seconds=5.0)
        _app_state["position_sync_worker"] = worker
        await worker.start()

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
