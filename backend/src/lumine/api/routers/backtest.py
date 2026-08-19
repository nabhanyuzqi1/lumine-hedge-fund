# Copyright (c) 2026 Lumine. All rights reserved.
"""Backtest REST endpoints (B-01, upgraded 17 Aug 2026)."""

from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Query

from lumine.api.middleware.auth import AuthenticatedPrincipal, require_scope
from lumine.backtest.engine import BacktestResult, run_backtest_from_rows
from lumine.data.models import Bars1H, Bars1M, Bars4H, Bars5M, Bars15M
from lumine.data.session import get_sessionmaker

router = APIRouter(prefix="/backtest", tags=["backtest"])

_TF_MODEL = {
    "1m": Bars1M,
    "5m": Bars5M,
    "15m": Bars15M,  # 18 Aug 2026: tabel real (sebelumnya agregasi 5m)
    "1h": Bars1H,
    "4h": Bars4H,
}


@router.get("/run")
async def run_backtest_endpoint(
    _principal: Annotated[AuthenticatedPrincipal, require_scope("read:portfolio")],
    symbol: str = Query("XAUUSD"),
    timeframe: str = Query("1h", pattern="^(1m|5m|15m|1h|4h)$"),
    limit: int = Query(400, ge=50, le=5_000),
    stop_pct: Decimal = Query(Decimal("0.02"), ge=0.001, le=0.2),
) -> BacktestResult:
    """Run backtest on REAL bars from PostgreSQL (bars_* seeded via MT5 EA).

    Backtest beta (17 Aug 2026): data nyata dari DB, bukan demo/deterministik.
    15m dari tabel bars_15m (18 Aug 2026). Baris diambil oldest-first.
    """
    from sqlalchemy import text

    model = _TF_MODEL.get(timeframe)
    table = model.__tablename__ if model is not None else None
    rows: list[dict] = []
    if table is not None:
        try:
            async with get_sessionmaker()() as session:
                # Whitelist tabel eksplisit (tanpa f-string → tidak ada
                # S608): pilih nama tabel dari dict konstanta _TF_MODEL,
                # lalu query dengan interpolasi yang sudah dikunci.
                table_map = {
                    "1m": "bars_1m",
                    "5m": "bars_5m",
                    "15m": "bars_15m",  # 18 Aug 2026: tabel real
                    "1h": "bars_1h",
                    "4h": "bars_4h",
                }
                tbl = table_map[timeframe]  # KeyError tidak mungkin — Query pattern sudah membatasi
                # nosec B608 — tabel dari whitelist dict konstanta.
                stmt = (
                    "SELECT ts, open, high, low, close, volume "  # nosec B608
                    "FROM " + tbl + " WHERE symbol = :sym "
                    "ORDER BY ts ASC LIMIT :lim"
                )
                result = await session.execute(
                    text(stmt),
                    {"sym": symbol.upper(), "lim": limit},
                )
                for r in result.all():
                    rows.append(
                        {
                            "ts": r.ts,
                            "open": Decimal(str(r.open)),
                            "high": Decimal(str(r.high)),
                            "low": Decimal(str(r.low)),
                            "close": Decimal(str(r.close)),
                            "volume": Decimal(str(r.volume)),
                        }
                    )
        except Exception as exc:
            import logging

            logging.getLogger(__name__).error("backtest DB query failed", exc_info=exc)
            rows = []  # DB error → result kosong (tidak crash)
    return run_backtest_from_rows(rows, symbol, timeframe, stop_pct=stop_pct)


@router.get("/master")
async def run_master_backtest_endpoint(
    _principal: Annotated[AuthenticatedPrincipal, require_scope("read:portfolio")],
    symbol: str = Query("XAUUSD"),
    timeframe: str = Query("1h", pattern="^(1m|5m|15m|1h|4h|1d)$"),
    profile_id: str = Query("scalping_1m"),
    persist: bool = Query(default=True),
) -> dict:
    """Master backtest 1 tahun (18 Aug 2026) — sesuai profile dipilih.

    Ambil data candle 1 tahun (DB bars_*) → jalankan engine → simpan hasil
    (backtest_runs) → learning digest dipakai improve prompt AI (loop).
    """
    from lumine.backtest.master import run_master_backtest
    from lumine.data.session import get_sessionmaker

    try:
        async with get_sessionmaker()() as session:
            return await run_master_backtest(
                session,
                symbol=symbol.upper(),
                timeframe=timeframe,
                profile_id=profile_id,
                persist=bool(persist),
            )
    except Exception as exc:
        import logging

        logging.getLogger(__name__).error("master backtest failed", exc_info=exc)
        return {"error": str(exc)[:200], "profile_id": profile_id}


@router.get("/runs")
async def list_backtest_runs_endpoint(
    _principal: Annotated[AuthenticatedPrincipal, require_scope("read:portfolio")],
    profile_id: str | None = Query(default=None),
    limit: int = Query(10, ge=1, le=50),
) -> list[dict]:
    """List hasil master backtest tersimpan (learning history)."""
    from lumine.backtest.master import get_latest_runs
    from lumine.data.session import get_sessionmaker

    try:
        async with get_sessionmaker()() as session:
            return await get_latest_runs(session, profile_id, limit)
    except Exception as exc:
        import logging

        logging.getLogger(__name__).error("list backtest runs failed", exc_info=exc)
        return []
