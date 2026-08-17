# Copyright (c) 2026 Lumine. All rights reserved.
"""Backtest REST endpoints (B-01, upgraded 17 Aug 2026)."""

from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Query

from lumine.api.middleware.auth import AuthenticatedPrincipal, require_scope
from lumine.backtest.engine import BacktestResult, run_backtest_from_rows
from lumine.data.models import Bars1H, Bars1M, Bars4H, Bars5M
from lumine.data.session import get_sessionmaker

router = APIRouter(prefix="/backtest", tags=["backtest"])

_TF_MODEL = {
    "1m": Bars1M,
    "5m": Bars5M,
    "15m": Bars5M,  # agregasi 3 bar 5m per 15m
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
    15m diagregasi dari bars_5m (bucket 900s). Baris diambil oldest-first.
    """
    from sqlalchemy import text

    model = _TF_MODEL.get(timeframe)
    table = model.__tablename__ if model is not None else None
    rows: list[dict] = []
    if table is not None:
        try:
            async with get_sessionmaker()() as session:
                # 15m: agregasi bucket 900s dari bars_5m.
                if timeframe == "15m":
                    result = await session.execute(
                        text(
                            """
                            SELECT
                              to_timestamp(floor(extract(epoch FROM ts) / 900) * 900) AT TIME ZONE 'UTC' AS ts,
                              (array_agg(open ORDER BY ts))[1] AS open,
                              max(high) AS high,
                              min(low) AS low,
                              (array_agg(close ORDER BY ts))[array_length(array_agg(close ORDER BY ts), 1)] AS close,
                              sum(volume) AS volume
                            FROM bars_5m
                            WHERE symbol = :sym
                            GROUP BY 1
                            ORDER BY 1 ASC
                            LIMIT :lim
                            """
                        ),
                        {"sym": symbol.upper(), "lim": limit},
                    )
                else:
                    # Whitelist tabel eksplisit (tanpa f-string → tidak ada
                    # S608): pilih nama tabel dari dict konstanta _TF_MODEL,
                    # lalu query dengan interpolasi yang sudah dikunci.
                    table_map = {"1m": "bars_1m", "5m": "bars_5m", "1h": "bars_1h", "4h": "bars_4h"}
                    tbl = table_map[timeframe]  # KeyError tidak mungkin — Query pattern sudah membatasi
                    # nosec B608: `tbl` dari whitelist dict konstanta, bukan input user.
                    stmt = (  # nosec B608
                        "SELECT ts, open, high, low, close, volume "
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
        except Exception:
            rows = []  # DB error → result kosong (tidak crash)
    return run_backtest_from_rows(rows, symbol, timeframe, stop_pct=stop_pct)
