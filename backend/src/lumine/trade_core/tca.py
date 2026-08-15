# Copyright (c) 2026 Lumine. All rights reserved.
"""Arrival-price transaction cost analysis for fills (ADR-0040)."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import TYPE_CHECKING, Any, cast

from sqlalchemy import select

from lumine.data.models import Fill, TcaRecord, Tick

if TYPE_CHECKING:
    from datetime import datetime

    from sqlalchemy.ext.asyncio import AsyncSession


_BPS = Decimal(10000)
_MONEY_QUANTUM = Decimal("0.0001")


@dataclass(frozen=True)
class Benchmark:
    """Point-in-time benchmark selected for a fill."""

    price: Decimal
    ts: datetime
    source: str


@dataclass(frozen=True)
class TcaCalculation:
    """Deterministic per-fill TCA values."""

    slippage: Decimal
    slippage_bps: Decimal
    slippage_cost_ccy: Decimal
    benchmark_source: str = "arrival_mid"


def _mid(tick: Any) -> Decimal:
    """Return a validated bid/ask midpoint from a market-data row."""
    bid = cast("Decimal", tick.bid)
    ask = cast("Decimal", tick.ask)
    if bid <= 0 or ask <= 0 or ask < bid:
        msg = "benchmark tick has invalid bid/ask"
        raise ValueError(msg)
    return (bid + ask) / 2


def calculate_tca(
    *,
    side: str,
    fill_price: Decimal,
    benchmark_price: Decimal,
    size: Decimal,
    pip_value: Decimal,
    pip_size: Decimal | None = None,
    benchmark_source: str = "arrival_mid",
) -> TcaCalculation:
    """Calculate side-aware slippage in price, bps, and account currency.

    ``pip_size`` is accepted for broker metadata compatibility. ADR-0040's
    cost contract is price slippage times size times pip value; it does not
    convert the price difference a second time through ``pip_size``.
    """
    normalized_side = side.upper()
    if normalized_side not in {"BUY", "SELL"}:
        msg = "side must be BUY or SELL"
        raise ValueError(msg)
    if benchmark_price <= 0:
        msg = "benchmark price must be positive"
        raise ValueError(msg)
    if fill_price <= 0:
        msg = "fill price must be positive"
        raise ValueError(msg)
    if size < 0 or pip_value < 0:
        msg = "size and pip_value must be non-negative"
        raise ValueError(msg)
    if pip_size is not None and pip_size <= 0:
        msg = "pip_size must be positive"
        raise ValueError(msg)

    slippage = (
        fill_price - benchmark_price if normalized_side == "BUY" else benchmark_price - fill_price
    )
    slippage_bps = (slippage / benchmark_price * _BPS).quantize(
        Decimal("0.0001"), rounding=ROUND_HALF_UP
    )
    cost = (slippage * size * pip_value).quantize(_MONEY_QUANTUM, rounding=ROUND_HALF_UP)
    return TcaCalculation(
        slippage=slippage,
        slippage_bps=slippage_bps,
        slippage_cost_ccy=cost,
        benchmark_source=benchmark_source,
    )


def _calendar_closed(calendar: Any, symbol: str, ts: datetime) -> bool:
    """Call an injected calendar without imposing a concrete calendar type."""
    return calendar is not None and calendar.is_closed(symbol, ts)


def _next_open(calendar: Any, symbol: str, ts: datetime) -> datetime | None:
    """Resolve the next session open from an injected calendar."""
    return None if calendar is None else calendar.next_session_open(symbol, ts)


async def resolve_benchmark(
    session: AsyncSession,
    symbol: str,
    decision_ts: datetime,
    *,
    calendar: Any = None,
) -> Benchmark:
    """Resolve arrival mid, clamping closed-market decisions to next open.

    The database is authoritative for ticks. A missing benchmark is a hard
    failure; callers must not write a TCA record with a stale or guessed price.
    """
    if _calendar_closed(calendar, symbol, decision_ts):
        open_ts = _next_open(calendar, symbol, decision_ts)
        if open_ts is None:
            msg = "benchmark unavailable: next session open is undefined"
            raise ValueError(msg)
        statement = (
            select(Tick)
            .where(Tick.symbol == symbol, Tick.ts >= open_ts)
            .order_by(Tick.ts.asc())
            .limit(1)
        )
        result = await session.execute(statement)
        tick = result.scalar_one_or_none()
        if tick is None:
            msg = "benchmark unavailable: next session open tick is missing"
            raise ValueError(msg)
        return Benchmark(price=_mid(tick), ts=tick.ts, source="session_open")

    statement = (
        select(Tick)
        .where(Tick.symbol == symbol, Tick.ts <= decision_ts)
        .order_by(Tick.ts.desc())
        .limit(1)
    )
    result = await session.execute(statement)
    tick = result.scalar_one_or_none()
    if tick is None:
        msg = "benchmark unavailable: arrival tick is missing"
        raise ValueError(msg)
    return Benchmark(price=_mid(tick), ts=tick.ts, source="arrival_mid")


async def persist_tca(
    session: AsyncSession,
    fill: Fill,
    *,
    decision_ts: datetime,
    regime_id: str,
    broker_id: str,
    account_id: str,
    pip_value: Decimal,
    pip_size: Decimal | None = None,
    calendar: Any = None,
) -> TcaRecord:
    """Compute and stage a TCA row in the caller-owned fill transaction."""
    benchmark = await resolve_benchmark(session, fill.symbol, decision_ts, calendar=calendar)
    calculation = calculate_tca(
        side=fill.side,
        fill_price=fill.price,
        benchmark_price=benchmark.price,
        size=fill.size,
        pip_value=pip_value,
        pip_size=pip_size,
        benchmark_source=benchmark.source,
    )
    record = TcaRecord(
        fill_id=fill.fill_id,
        benchmark_price=benchmark.price,
        slippage_bps=calculation.slippage_bps,
        slippage_cost_ccy=calculation.slippage_cost_ccy,
        decision_ts=decision_ts,
        regime_id=regime_id,
        broker_id=broker_id,
        account_id=account_id,
        benchmark_source=benchmark.source,
    )
    session.add(record)
    return record


__all__ = ["Benchmark", "TcaCalculation", "calculate_tca", "persist_tca", "resolve_benchmark"]
