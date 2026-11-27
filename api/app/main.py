"""Fund2 API entrypoint. Serves API + SSE + frontend build (SPA) on one port."""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import auth, auto_sl, config, db, ingest, kill_switch, llm_risk
from .bridge import router as bridge_router
from .degradation_routes import router as degradation_router
from .fib_routes import router as fib_router
from .llm_agent import router as llm_agent_router
from .llm_introspection import router as llm_introspection_router
from .metrics import router as metrics_router
from .research_routes import router as research_router
from .risk_config_routes import router as risk_config_router
from .routes import router as api_router
from .selfimprove_routes import router as selfimprove_router
from .shadow_routes import router as shadow_router
from .telegram_bot import telegram_loop
from .versioning_routes import router as versioning_router
from .worker import worker_loop


async def _bootstrap_admin() -> None:
    async with db.pool().connection() as conn:
        cur = await conn.execute("SELECT COUNT(*) AS n FROM users")
        row = await cur.fetchone()
        if row["n"] == 0 and config.ADMIN_PASSWORD:
            await auth.create_user(conn, config.ADMIN_USER, config.ADMIN_PASSWORD)
            print(f"[boot] created admin user '{config.ADMIN_USER}'", flush=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.init_pool()
    # Reboot host: Postgres di unit lain bisa butuh beberapa detik (crash
    # recovery) sebelum menerima query. Tanpa tunggu, boot API gagal di
    # apply_schema dan dashboard melaporkan DB DOWN (insiden 26 Nov 2026).
    await db.wait_ready(logger=db.log)
    await db.apply_schema()
    await db.seed_defaults()
    await _bootstrap_admin()

    # init kill-switch state dari DB (default inactive)
    state = await db.get_settings()
    kill_switch.init_ea_seen(state)
    # t_4d524475: selaraskan mirror legacy 'halted' dengan state kill-switch
    # saat boot (state setengah-halt dari halt lama tidak boleh memblokir).
    try:
        if await kill_switch.sync_legacy_halted(state):
            print("[boot] mirror legacy 'halted' diselaraskan dengan state kill-switch",
                  flush=True)
    except Exception as exc:  # noqa: BLE001 - boot tidak boleh gagal karena mirror
        print(f"[boot] gagal menyelaraskan mirror 'halted': {exc}", flush=True)
    stop = asyncio.Event()
    worker = asyncio.create_task(worker_loop(stop), name="fund2-worker")
    monitor = asyncio.create_task(kill_switch.monitor_loop(stop), name="kill-switch-monitor")
    llm_monitor = asyncio.create_task(llm_risk.monitor_loop(stop), name="llm-risk-monitor")
    # RISK-B: BE + trailing stop deterministik di bridge layer (flag OFF default)
    auto_sl_task = asyncio.create_task(auto_sl.monitor_loop(stop), name="auto-sl-monitor")
    tg = asyncio.create_task(telegram_loop(stop), name="telegram-bot")
    # Ingest pipeline (PRD 5.1): ring buffer tick -> parquet 60 dtk;
    # liquidity_samples + candle -> Postgres di background.
    ingest.reset_pipeline()
    ingest_task = asyncio.create_task(ingest.get_pipeline().run(stop), name="tick-ingest")
    yield
    stop.set()
    for task in (worker, monitor, llm_monitor, tg, ingest_task, auto_sl_task):
        task.cancel()
    for task in (worker, monitor, llm_monitor, tg, ingest_task, auto_sl_task):
        try:
            await task
        except asyncio.CancelledError:
            pass
    await db.close_pool()


app = FastAPI(title="Fund2 API", version="0.1.0", lifespan=lifespan)

# Local dev only (Vite on 5173); production is same-origin behind Caddy.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)
app.include_router(selfimprove_router)
app.include_router(bridge_router)
app.include_router(llm_agent_router)
app.include_router(llm_introspection_router)
app.include_router(metrics_router)
app.include_router(shadow_router)
app.include_router(degradation_router)
app.include_router(fib_router)
app.include_router(versioning_router)
app.include_router(research_router)
app.include_router(risk_config_router)

# SPA: serve the frontend build if it exists (mount last so API routes win first).
if (config.FRONTEND_DIST / "index.html").exists():
    if (config.FRONTEND_DIST / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=config.FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa(full_path: str):
        candidate = config.FRONTEND_DIST / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        # index.html selalu revalidate: build baru harus langsung terlihat
        # (nama file aset di-hash, jadi cache lama tidak pernah setengah-update).
        return FileResponse(
            config.FRONTEND_DIST / "index.html",
            headers={"Cache-Control": "no-cache"},
        )
else:

    @app.get("/", include_in_schema=False)
    async def root():
        return {"service": "fund2-api", "docs": "/docs"}
