# Copyright (c) 2026 Lumine. All rights reserved.
"""Market data, features, and signal endpoints."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select

from lumine.api.demo_data import INSTRUMENTS
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
    symbol: str = Query(default="XAUUSD"),
    timeframe: str = Query(default="5m", pattern="^(1m|5m|15m|1h|4h|1d)$"),
) -> PaginatedList[MarketBar]:
    """Return recent market bars untuk timeframe yang diminta.

    FIX 18 Aug 2026 (critical): SEBELUMNYA hardcoded Bars1H — abaikan
    symbol & timeframe → semua halaman dapat 1h walau pilih 5m/15m → chart
    tampil timeframe salah. Sekarang pilih tabel per timeframe
    (bars_1m/5m/15m/1h/4h/1d). Plus value di-cast float (Decimal →
    string JSON membuat frontend Number.isFinite() skip semua bar → chart
    kosong).
    """
    from lumine.data.models import Bars1D, Bars1H, Bars1M, Bars4H, Bars5M, Bars15M
    from lumine.data.session import get_sessionmaker

    table_by_tf: dict[str, Any] = {
        "1m": Bars1M,
        "5m": Bars5M,
        "15m": Bars15M,
        "1h": Bars1H,
        "4h": Bars4H,
        "1d": Bars1D,
    }
    model = table_by_tf.get(timeframe, Bars1H)
    try:
        async with get_sessionmaker()() as session:
            result = await session.execute(
                select(model)
                .where(model.symbol == symbol)
                .order_by(model.ts.desc())
                .limit(pagination.limit)
            )
            rows = result.scalars().all()
    except Exception:
        rows = []
    items = [
        MarketBar(
            symbol=row.symbol,
            timeframe=timeframe,
            timestamp=row.ts,
            open=float(row.open),
            high=float(row.high),
            low=float(row.low),
            close=float(row.close),
            volume=row.volume,
        )
        for row in rows
    ]
    return PaginatedList(
        items=items,
        total=len(items),
        limit=pagination.limit,
        offset=pagination.offset,
    )


@router.get("/signals/{symbol}", response_model=PaginatedList[Signal])
async def list_symbol_signals(
    symbol: str,
    _principal: Annotated[AuthenticatedPrincipal, require_scope("read:market")],
    pagination: Annotated[Pagination, Depends()],
) -> PaginatedList[Signal]:
    """Return recent analyst signals for one symbol (B-05/B5).

    ZERO-DEMO: sinyal real dari decision cycle LLM (tabel signals) —
    kosong hanya jika committee belum pernah menghasilkan sinyal.
    """
    from lumine.data.models import Signal as SignalRow
    from lumine.data.session import get_sessionmaker

    try:
        async with get_sessionmaker()() as session:
            result = await session.execute(
                select(SignalRow)
                .where(SignalRow.symbol == symbol.upper())
                .order_by(SignalRow.generated_at.desc())
                .limit(pagination.limit)
                .offset(pagination.offset)
            )
            rows = list(result.scalars().all())
            return PaginatedList(
                items=[
                    Signal(
                        signal_id=row.signal_id,
                        symbol=row.symbol,
                        analyst=row.analyst,
                        direction=row.direction,  # type: ignore[arg-type]
                        confidence=row.confidence,
                        rationale=row.rationale,
                        generated_at=row.generated_at,
                    )
                    for row in rows
                ],
                total=len(rows),
                limit=pagination.limit,
                offset=pagination.offset,
            )
    except Exception:
        return PaginatedList(items=[], total=0, limit=pagination.limit, offset=pagination.offset)


@router.get("/signals", response_model=PaginatedList[Signal])
async def list_signals(
    _principal: Annotated[AuthenticatedPrincipal, require_scope("read:market")],
    pagination: Annotated[Pagination, Depends()],
) -> PaginatedList[Signal]:
    """Return recent analyst signals (semua symbol; real dari tabel signals)."""
    from lumine.data.models import Signal as SignalRow
    from lumine.data.session import get_sessionmaker

    try:
        async with get_sessionmaker()() as session:
            result = await session.execute(
                select(SignalRow)
                .order_by(SignalRow.generated_at.desc())
                .limit(pagination.limit)
                .offset(pagination.offset)
            )
            rows = list(result.scalars().all())
            return PaginatedList(
                items=[
                    Signal(
                        signal_id=row.signal_id,
                        symbol=row.symbol,
                        analyst=row.analyst,
                        direction=row.direction,  # type: ignore[arg-type]
                        confidence=row.confidence,
                        rationale=row.rationale,
                        generated_at=row.generated_at,
                    )
                    for row in rows
                ],
                total=len(rows),
                limit=pagination.limit,
                offset=pagination.offset,
            )
    except Exception:
        return PaginatedList(items=[], total=0, limit=pagination.limit, offset=pagination.offset)


# ── Market cluster (frontend marketClient.ts contract) ───────────────────


@router.get("/quote/{symbol}", response_model=MarketQuote)
async def get_quote(
    symbol: str,
    _principal: Annotated[AuthenticatedPrincipal, require_scope("read:market")],
) -> MarketQuote:
    """Return the current bid/ask/last quote (live dari MarketService/Redis ticks).

    ZERO-DEMO: tanpa tick live (market libur / feed kosong) → 404,
    bukan harga sintetis.
    """
    from lumine.api.routers.streams import get_market_service

    market_service = get_market_service()
    tick = await market_service.get_quote(symbol) if market_service else None
    if tick is None:
        raise HTTPException(
            status_code=404, detail=f"no live quote for {symbol} (market closed or feed empty)"
        )
    return MarketQuote(
        symbol=symbol.upper(),
        bid=Decimal(str(tick.bid)),
        ask=Decimal(str(tick.ask)),
        mid=Decimal(str(round((tick.bid + tick.ask) / 2, 5))),
        last=Decimal(str(tick.bid)),
        spread=Decimal(str(round(tick.ask - tick.bid, 5))),
        volume_24h=Decimal(0),
        change_24h=Decimal(0),
        change_pct_24h=Decimal(0),
        timestamp=tick.timestamp,
    )


@router.get("/news")
async def get_news_headlines(
    _principal: Annotated[AuthenticatedPrincipal, require_scope("read:market")],
    limit: Annotated[int, Query(ge=1, le=50)] = 10,
) -> dict:
    """Berita XAUUSD/emas real (18 Aug 2026) — dari cache RSS _news_worker.

    Seed awal saat startup + update tiap 5 menit; headline baru di-push
    ke SSE channel `news-headlines` (WS /ws/market menerima event
    `news_update`). Gagal → fallback list (analyst tidak pernah kosong).
    """
    from lumine.trading.news_service import get_cached_headlines

    r = await _redis()
    items = await get_cached_headlines(r, limit=limit)
    return {"items": items, "count": len(items), "source": "rss-kitco-reuters"}


@router.get("/economic-calendar")
async def get_economic_calendar(
    _principal: Annotated[AuthenticatedPrincipal, require_scope("read:market")],
) -> dict:
    """Economic calendar (18 Aug 2026) — dari cache _eco_calendar_worker.

    Event 72 jam ke depan: NFP/CPI/FOMC dll + impact level. Dipakai
    halaman NewsRoom frontend + analyst prompt.
    """
    from lumine.trading.economic_calendar import get_cached_calendar

    r = await _redis()
    events = await get_cached_calendar(r)
    return {"items": events, "count": len(events), "source": "faireconomy-rss"}


@router.get("/dxy")
async def get_dxy(
    _principal: Annotated[AuthenticatedPrincipal, require_scope("read:market")],
) -> dict:
    """DXY (US Dollar Index) realtime (18 Aug 2026) — cache _dxy_worker.

    Variabel LLM (inverse correlation XAUUSD) + NewsRoom display.
    """
    from lumine.trading.dxy_service import get_cached_dxy

    r = await _redis()
    dxy = await get_cached_dxy(r)
    if not dxy:
        return {"price": None, "source": "unavailable"}
    return dxy


async def _redis():
    # FIX 18 Aug 2026: SEBELUMNYA redis.from_url() → client SYNC → await
    # r.get() TypeError → caught → [] (calendar/news kosong walau cache ada).
    from lumine.data.redis_client import get_redis

    return await get_redis()


@router.get("/quotes")
async def get_quotes(
    symbols: Annotated[list[str], Query(min_length=1, max_length=50)],
    _principal: Annotated[AuthenticatedPrincipal, require_scope("read:market")],
) -> dict[str, MarketQuote]:
    """Batch fetch quotes (live dari MarketService). Symbol tanpa tick di-skip."""
    from lumine.api.routers.streams import get_market_service

    market_service = get_market_service()
    result: dict[str, MarketQuote] = {}
    for s in symbols:
        tick = await market_service.get_quote(s) if market_service else None
        if tick is None:
            continue
        result[s.upper()] = MarketQuote(
            symbol=s.upper(),
            bid=Decimal(str(tick.bid)),
            ask=Decimal(str(tick.ask)),
            mid=Decimal(str(round((tick.bid + tick.ask) / 2, 5))),
            last=Decimal(str(tick.bid)),
            spread=Decimal(str(round(tick.ask - tick.bid, 5))),
            volume_24h=Decimal(0),
            change_24h=Decimal(0),
            change_pct_24h=Decimal(0),
            timestamp=tick.timestamp,
        )
    return result


@router.get("/ohlcv/{symbol}")
async def get_ohlcv(
    symbol: str,
    _principal: Annotated[AuthenticatedPrincipal, require_scope("read:market")],
    timeframe: Annotated[str, Query(pattern="^(1m|5m|15m|30m|1h|4h|1d|1w)$")] = "1h",
    limit: Annotated[int, Query(ge=1, le=10_000)] = 100,
    since: datetime | None = None,
) -> list[MarketBar]:
    """Return OHLCV bars for a symbol (DB-backed via bars_*; seed dari MT5).

    ZERO-DEMO: tabel kosong = return [] (bukan data fiktif random walk).
    """
    from lumine.data.models import Bars1D, Bars1H, Bars1M, Bars4H, Bars5M, Bars15M
    from lumine.data.session import get_sessionmaker

    # 15m tidak punya tabel sendiri → pakai bars_5m (bucket 15m adalah
    # superset 5m; chart frontend bucket sendiri). Fallback agregasi
    # ditangani seed worker.
    bar_models = {
        "1m": Bars1M,
        "5m": Bars5M,
        "15m": Bars15M,  # 18 Aug 2026: tabel real (sebelumnya agregasi 5m)
        "1h": Bars1H,
        "4h": Bars4H,
        "1d": Bars1D,
    }
    model = bar_models.get(timeframe)
    if model is None:
        return []
    try:
        async with get_sessionmaker()() as session:
            # 15m: agregasi BENAR 3 bar 5m per bucket 900s (sebelumnya cuma
            # bar 5m kelipatan 900s → candle 15m tampil "hancur" karena
            # cuma 5 menit data). Fix batch-2.
            if timeframe == "15m":
                from sqlalchemy import text as sa_text

                # PITFALL (17 Aug 2026): `:since IS NULL OR ts >= :since` di
                # SQL + asyncpg → DBAPIError saat since=None (can't compare
                # None). Handle since di Python: query penuh tanpa filter,
                # filter ts >= since di level Python.
                result = await session.execute(
                    sa_text(
                        """
                        SELECT
                          to_timestamp(floor(extract(epoch FROM ts) / 900) * 900) AT TIME ZONE 'UTC' AS ts,
                          symbol,
                          (array_agg(open ORDER BY ts))[1] AS open,
                          max(high) AS high,
                          min(low) AS low,
                          (array_agg(close ORDER BY ts))[array_length(array_agg(close ORDER BY ts), 1)] AS close,
                          sum(volume) AS volume
                        FROM bars_5m
                        WHERE symbol = :sym
                        GROUP BY 1, 2
                        ORDER BY 1 DESC
                        LIMIT :lim
                        """
                    ),
                    {"sym": symbol.upper(), "lim": max(limit, 1000)},
                )
                rows = result.all()
                if since is not None:
                    rows = [r for r in rows if r.ts >= since]
                rows = rows[:limit]
            else:
                stmt = select(model).order_by(model.ts.desc()).limit(limit)
                if since is not None:
                    stmt = stmt.where(model.ts >= since)
                result = await session.execute(stmt)
                rows = list(result.scalars().all())
    except Exception:
        return []
    rows.reverse()
    return [
        MarketBar(
            symbol=row.symbol,
            timeframe=timeframe,
            timestamp=row.ts,
            open=row.open,
            high=row.high,
            low=row.low,
            close=row.close,
            volume=row.volume,
        )
        for row in rows
    ]


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
    """Return rolling volatility (fraction) — dihitung dari bars_1h real.

    ZERO-DEMO: tanpa data bars → 0.0 (bukan formula sintetis).
    """
    from lumine.data.models import Bars1H
    from lumine.data.session import get_sessionmaker

    try:
        async with get_sessionmaker()() as session:
            result = await session.execute(
                select(Bars1H)
                .where(Bars1H.symbol == symbol.upper())
                .order_by(Bars1H.ts.desc())
                .limit(window + 1)
            )
            rows = list(result.scalars().all())
    except Exception:
        rows = []
    if len(rows) < 2:
        return VolatilityResponse(volatility=0.0)
    rows.reverse()
    closes = [float(r.close) for r in rows]
    returns = [(closes[i] / closes[i - 1] - 1.0) for i in range(1, len(closes))]
    mean = sum(returns) / len(returns)
    var = sum((r - mean) ** 2 for r in returns) / len(returns)
    vol = var**0.5
    return VolatilityResponse(volatility=round(max(0.0, vol), 4))


@router.get("/correlation")
async def get_correlation(
    _principal: Annotated[AuthenticatedPrincipal, require_scope("read:market")],
    symbols: Annotated[list[str] | None, Query()] = None,
    window: Annotated[int, Query(ge=1, le=365)] = 30,
) -> dict[str, dict[str, float]]:
    """Return a symmetric correlation matrix dari returns bars real.

    ZERO-DEMO: hanya symbol dengan data bars yang muncul; tanpa data →
    diagonal 1.0 untuk symbol yang diminta, sisanya di-skip.
    """
    from lumine.data.models import Bars1H
    from lumine.data.session import get_sessionmaker

    universe = [s.upper() for s in (symbols or ["XAUUSD"])]
    series: dict[str, list[float]] = {}
    try:
        async with get_sessionmaker()() as session:
            for sym in universe:
                result = await session.execute(
                    select(Bars1H)
                    .where(Bars1H.symbol == sym)
                    .order_by(Bars1H.ts.desc())
                    .limit(window + 1)
                )
                rows = list(result.scalars().all())
                if len(rows) >= 2:
                    rows.reverse()
                    closes = [float(r.close) for r in rows]
                    series[sym] = [closes[i] / closes[i - 1] - 1.0 for i in range(1, len(closes))]
    except Exception:
        series = {}
    # G4: ZERO-DEMO jujur — hanya symbol DENGAN data yang muncul di matrix
    # (sebelumnya symbol tanpa data diisi 0.0 → heatmap menyesatkan "no
    # correlation" padahal "no data"). Dengan 1 stream aktif (XAUUSD),
    # matrix = 1x1 → frontend render satu cell + label jelas.
    active = [s for s in universe if s in series]
    matrix: dict[str, dict[str, float]] = {}
    for a in active:
        row: dict[str, float] = {}
        for b in active:
            if a == b:
                row[b] = 1.0
                continue
            if b < a:
                row[b] = matrix[b][a]
                continue
            ra, rb = series[a], series[b]
            n = min(len(ra), len(rb))
            if n < 2:
                row[b] = 0.0
                continue
            ma, mb = sum(ra[:n]) / n, sum(rb[:n]) / n
            cov = sum((ra[i] - ma) * (rb[i] - mb) for i in range(n)) / n
            va = sum((x - ma) ** 2 for x in ra[:n]) / n
            vb = sum((x - mb) ** 2 for x in rb[:n]) / n
            denom = (va * vb) ** 0.5
            row[b] = round(cov / denom, 4) if denom else 0.0
        matrix[a] = row
    return matrix


@router.get("/spread/{symbol}", response_model=SpreadMetrics)
async def get_spread(
    symbol: str,
    _principal: Annotated[AuthenticatedPrincipal, require_scope("read:market")],
    period: Annotated[int, Query(ge=1, le=86_400)] = 60,
) -> SpreadMetrics:
    """Return spread statistics — live dari MarketService (bid/ask EA).

    ZERO-DEMO: tanpa tick live → 0 (bukan wiggle sintetis).
    """
    from lumine.api.routers.streams import get_market_service

    market_service = get_market_service()
    tick = await market_service.get_quote(symbol) if market_service else None
    if tick is None:
        return SpreadMetrics(
            avg_spread=Decimal(0),
            avg_pct_spread=Decimal(0),
            min_spread=Decimal(0),
            max_spread=Decimal(0),
        )
    spread = Decimal(str(round(tick.ask - tick.bid, 5)))
    mid = Decimal(str(tick.bid))
    pct = (spread / mid * 100).quantize(Decimal("0.0001")) if mid else Decimal(0)
    return SpreadMetrics(
        avg_spread=spread,
        avg_pct_spread=pct,
        min_spread=spread,
        max_spread=spread,
    )


@router.get("/session/{symbol}", response_model=SessionInfo)
async def get_session(
    symbol: str,
    _principal: Annotated[AuthenticatedPrincipal, require_scope("read:market")],
) -> SessionInfo:
    """Return current trading session state (real market calendar, ADR-0037)."""
    from lumine.api.routers.streams import _market_status

    if symbol.upper() not in INSTRUMENTS:
        raise HTTPException(status_code=404, detail=f"unknown symbol: {symbol}")
    status = _market_status()
    session_state = "off" if not status["open"] else "asian"
    return SessionInfo(
        current_session=session_state,
        next_session="asian",
        time_until_next=0,
        is_trading_open=status["open"],
    )


@router.get("/features/{symbol}", response_model=FeatureSet)
async def get_features(
    symbol: str,
    _principal: Annotated[AuthenticatedPrincipal, require_scope("read:market")],
) -> FeatureSet:
    """Return computed technical features — dihitung dari bars real.

    ZERO-DEMO: tanpa data bars → dict kosong (bukan fitur sintetis).
    """
    from lumine.data.models import Bars1H
    from lumine.data.session import get_sessionmaker

    features: dict[str, float] = {}
    try:
        async with get_sessionmaker()() as session:
            result = await session.execute(
                select(Bars1H)
                .where(Bars1H.symbol == symbol.upper())
                .order_by(Bars1H.ts.desc())
                .limit(30)
            )
            rows = list(result.scalars().all())
        if len(rows) >= 2:
            rows.reverse()
            closes = [float(r.close) for r in rows]
            last = closes[-1]
            sma20 = sum(closes[-20:]) / min(20, len(closes))
            returns = [closes[i] / closes[i - 1] - 1.0 for i in range(1, len(closes))]
            vol = (
                sum((r - sum(returns) / len(returns)) ** 2 for r in returns) / len(returns)
            ) ** 0.5
            features = {
                "last_price": round(last, 2),
                "sma20": round(sma20, 2),
                "volatility": round(vol, 4),
                "trend_slope": round((closes[-1] / closes[0] - 1.0) * 100, 4),
            }
    except Exception:
        features = {}
    return FeatureSet(
        symbol=symbol.upper(),
        features=features,
        computed_at=datetime.now(UTC),
    )
