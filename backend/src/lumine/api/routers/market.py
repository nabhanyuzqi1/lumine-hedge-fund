# Copyright (c) 2026 Lumine. All rights reserved.
"""Market data, features, and signal endpoints."""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query

from lumine.api.demo_data import (
    INSTRUMENTS,
    TIMEFRAME_SECONDS,
    features_for,
    mid_price,
    quote_for,
    round_price,
    session_at,
    spread_units,
)
from lumine.api.middleware.auth import AuthenticatedPrincipal, require_scope
from lumine.api.schemas.api import (
    FeatureSet,
    MarketBar,
    MarketQuote,
    SessionInfo,
    Signal,
    SpreadMetrics,
    SymbolConfig,
    VolatilityResponse,
)
from lumine.api.schemas.common import PaginatedList, Pagination

router = APIRouter(prefix="/market", tags=["market"])


@router.get("/bars", response_model=PaginatedList[MarketBar])
async def list_bars(
    _principal: Annotated[AuthenticatedPrincipal, require_scope("read:market")],
    pagination: Annotated[Pagination, Depends()],
) -> PaginatedList[MarketBar]:
    """Return recent market bars."""
    now = datetime.now(UTC)
    items: list[MarketBar] = [
        MarketBar(
            symbol="XAUUSD",
            timeframe="H1",
            timestamp=now,
            open=Decimal("2420.00"),
            high=Decimal("2430.50"),
            low=Decimal("2418.00"),
            close=Decimal("2435.80"),
            volume=1200,
        ),
    ]
    return PaginatedList(
        items=items,
        total=len(items),
        limit=pagination.limit,
        offset=pagination.offset,
    )


@router.get("/signals", response_model=PaginatedList[Signal])
async def list_signals(
    _principal: Annotated[AuthenticatedPrincipal, require_scope("read:market")],
    pagination: Annotated[Pagination, Depends()],
) -> PaginatedList[Signal]:
    """Return recent analyst signals."""
    now = datetime.now(UTC)
    items: list[Signal] = [
        Signal(
            signal_id=uuid4(),
            symbol="XAUUSD",
            analyst="technical_analyst",
            direction="bullish",
            confidence=0.78,
            rationale="breakout above resistance",
            generated_at=now,
        ),
    ]
    return PaginatedList(
        items=items,
        total=len(items),
        limit=pagination.limit,
        offset=pagination.offset,
    )


# ── Market cluster (frontend marketClient.ts contract) ───────────────────


@router.get("/quote/{symbol}", response_model=MarketQuote)
async def get_quote(
    symbol: str,
    _principal: Annotated[AuthenticatedPrincipal, require_scope("read:market")],
) -> MarketQuote:
    """Return the current bid/ask/last quote for a symbol."""
    return MarketQuote(**quote_for(symbol))


@router.get("/quotes")
async def get_quotes(
    symbols: Annotated[list[str], Query(min_length=1, max_length=50)],
    _principal: Annotated[AuthenticatedPrincipal, require_scope("read:market")],
) -> dict[str, MarketQuote]:
    """Batch fetch quotes for multiple symbols (map of symbol → quote)."""
    return {s.upper(): MarketQuote(**quote_for(s)) for s in symbols}


@router.get("/ohlcv/{symbol}")
async def get_ohlcv(
    symbol: str,
    _principal: Annotated[AuthenticatedPrincipal, require_scope("read:market")],
    timeframe: Annotated[str, Query(pattern="^(1m|5m|15m|30m|1h|4h|1d|1w)$")] = "1h",
    limit: Annotated[int, Query(ge=1, le=10_000)] = 100,
    since: datetime | None = None,
) -> list[MarketBar]:
    """Return OHLCV bars for a symbol (deterministic demo random walk)."""
    step = TIMEFRAME_SECONDS[timeframe]
    now = datetime.now(UTC)
    end = now if since is None else min(now, since + timedelta(seconds=step * limit))

    seed = sum(ord(c) for c in symbol.upper())
    bars: list[MarketBar] = []
    ts = end - timedelta(seconds=step * limit)
    prev_close = mid_price(symbol, ts) * (1 - 0.001)
    for i in range(limit):
        ts = ts + timedelta(seconds=step)
        drift = math.sin(seed + i * 0.35) * 0.0012 + (seed % 5) * 0.0001
        open_ = prev_close
        close = round_price(open_ * (1 + drift), symbol)
        high = round_price(max(open_, close) * (1 + 0.0004), symbol)
        low = round_price(min(open_, close) * (1 - 0.0004), symbol)
        volume = 200 + int((seed * 97 + i * 131) % 8_000)
        bars.append(
            MarketBar(
                symbol=symbol.upper(),
                timeframe=timeframe,
                timestamp=ts,
                open=Decimal(str(open_)),
                high=Decimal(str(high)),
                low=Decimal(str(low)),
                close=Decimal(str(close)),
                volume=volume,
            )
        )
        prev_close = close
    return bars


@router.get("/symbol/{symbol}", response_model=SymbolConfig)
async def get_symbol_config(
    symbol: str,
    _principal: Annotated[AuthenticatedPrincipal, require_scope("read:market")],
) -> SymbolConfig:
    """Return instrument specification for a symbol."""
    entry = INSTRUMENTS.get(symbol.upper())
    if entry is None:
        raise HTTPException(status_code=404, detail=f"unknown symbol: {symbol}")
    _base, decimals, description, base_asset, quote_currency = entry
    tick = 10**-decimals
    return SymbolConfig(
        symbol=symbol.upper(),
        description=description,
        base_asset=base_asset,
        quote_currency=quote_currency,
        tick_size=Decimal(str(tick)),
        lot_size=Decimal("1.00"),
        min_lot_size=Decimal("0.01"),
        max_lot_size=Decimal("100.00"),
        is_active=True,
    )


@router.get("/symbols", response_model=list[SymbolConfig])
async def list_symbols(
    _principal: Annotated[AuthenticatedPrincipal, require_scope("read:market")],
    asset_class: str | None = None,
    exchange: str | None = None,
    *,
    include_inactive: bool = False,
) -> list[SymbolConfig]:
    """List all active instruments (optionally including inactive ones)."""
    symbols: list[SymbolConfig] = []
    for symbol, (_base, decimals, description, base_asset, quote_currency) in INSTRUMENTS.items():
        if asset_class is not None and asset_class.lower() not in description.lower():
            continue
        if exchange is not None and exchange.upper() not in (quote_currency, base_asset):
            continue
        is_active = True
        if not include_inactive and not is_active:
            continue
        symbols.append(
            SymbolConfig(
                symbol=symbol,
                description=description,
                base_asset=base_asset,
                quote_currency=quote_currency,
                tick_size=Decimal(str(10**-decimals)),
                lot_size=Decimal("1.00"),
                min_lot_size=Decimal("0.01"),
                max_lot_size=Decimal("100.00"),
                is_active=is_active,
            )
        )
    return symbols


@router.get("/volatility/{symbol}", response_model=VolatilityResponse)
async def get_volatility(
    symbol: str,
    _principal: Annotated[AuthenticatedPrincipal, require_scope("read:market")],
    window: Annotated[int, Query(ge=1, le=365)] = 14,
) -> VolatilityResponse:
    """Return rolling volatility (fraction) for a symbol."""
    seed = sum(ord(c) for c in symbol.upper())
    volatility = 0.06 + (seed % 13) / 100.0 + math.sin(window) * 0.01
    return VolatilityResponse(volatility=round(max(0.01, volatility), 4))


@router.get("/correlation")
async def get_correlation(
    _principal: Annotated[AuthenticatedPrincipal, require_scope("read:market")],
    symbols: Annotated[list[str] | None, Query()] = None,
    window: Annotated[int, Query(ge=1, le=365)] = 30,
) -> dict[str, dict[str, float]]:
    """Return a symmetric correlation matrix for the requested symbols."""
    universe = [s.upper() for s in (symbols or list(INSTRUMENTS))]
    matrix: dict[str, dict[str, float]] = {}
    for i, a in enumerate(universe):
        row: dict[str, float] = {}
        for j, b in enumerate(universe):
            if i == j:
                row[b] = 1.0
            elif j < i:
                row[b] = matrix[b][a]
            else:
                raw = math.sin(
                    (sum(ord(c) for c in a) + sum(ord(c) for c in b)) / 40.0
                    + window / 30.0 * 0.1
                )
                row[b] = round(max(-0.85, min(0.95, raw)), 4)
        matrix[a] = row
    return matrix


@router.get("/spread/{symbol}", response_model=SpreadMetrics)
async def get_spread(
    symbol: str,
    _principal: Annotated[AuthenticatedPrincipal, require_scope("read:market")],
    period: Annotated[int, Query(ge=1, le=86_400)] = 60,
) -> SpreadMetrics:
    """Return spread statistics for a symbol over a period."""
    spread = spread_units(symbol)
    mid = mid_price(symbol)
    wiggle = 1 + 0.2 * math.sin(period / 17.0)
    return SpreadMetrics(
        avg_spread=Decimal(str(round(spread * wiggle, 4))),
        avg_pct_spread=Decimal(str(round(spread / mid * 100, 4))),
        min_spread=Decimal(str(round(spread * 0.8, 4))),
        max_spread=Decimal(str(round(spread * 1.2, 4))),
    )


@router.get("/session/{symbol}", response_model=SessionInfo)
async def get_session(
    symbol: str,
    _principal: Annotated[AuthenticatedPrincipal, require_scope("read:market")],
) -> SessionInfo:
    """Return current trading session state for a symbol."""
    if symbol.upper() not in INSTRUMENTS:
        raise HTTPException(status_code=404, detail=f"unknown symbol: {symbol}")
    return SessionInfo(**session_at())


@router.get("/features/{symbol}", response_model=FeatureSet)
async def get_features(
    symbol: str,
    _principal: Annotated[AuthenticatedPrincipal, require_scope("read:market")],
) -> FeatureSet:
    """Return computed technical features for a symbol (FeaturePanel contract)."""
    return FeatureSet(
        symbol=symbol.upper(),
        features=features_for(symbol),
        computed_at=datetime.now(UTC),
    )
