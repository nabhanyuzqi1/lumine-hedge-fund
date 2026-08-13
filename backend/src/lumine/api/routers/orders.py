# Copyright (c) 2026 Lumine. All rights reserved.
"""Order lifecycle REST endpoints (B-05: DEMO_DATA switch)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException

from lumine.api.middleware.auth import AuthenticatedPrincipal, require_scope
from lumine.api.middleware.rate_limit import rate_limit_dependency
from lumine.api.schemas.api import (
    BulkStatusRequest,
    BulkStatusResult,
    CreateOrderRequest,
    ModifyOrderRequest,
    Order,
    OrderHistoryEntry,
)
from lumine.api.schemas.common import PaginatedList, Pagination
from lumine.data.repositories import OrderRepository
from lumine.data.session import get_sessionmaker
from lumine.shared.config import Settings, get_settings
from lumine.shared.errors import RecordNotFoundError

router = APIRouter(prefix="/orders", tags=["orders"])


def _to_schema(order: object) -> Order:
    """Map the DB Order model to the API Order schema."""
    from lumine.data.models import Order as OrderModel

    assert isinstance(order, OrderModel)
    return Order(
        order_id=order.order_id,
        portfolio_id=order.portfolio_id,
        symbol=order.symbol,
        side=order.side,  # type: ignore[arg-type]
        order_type=order.order_type,  # type: ignore[arg-type]
        volume=order.volume,
        price=order.price,
        status=order.status,  # type: ignore[arg-type]
        filled_volume=order.filled_volume,
        rejected_reason=order.rejected_reason,
        created_at=order.created_at,
        updated_at=order.updated_at,
    )


def _demo_order(
    *,
    order_id: UUID,
    portfolio_id: str = "default",
    symbol: str = "XAUUSD",
    side: str = "buy",
    order_type: str = "market",
    volume: Decimal = Decimal("1.50"),
    price: Decimal | None = None,
    status: str = "filled",
    filled_volume: Decimal = Decimal("1.50"),
    created_at: datetime | None = None,
    updated_at: datetime | None = None,
) -> Order:
    now = created_at or datetime.now(UTC)
    return Order(
        order_id=order_id,
        portfolio_id=portfolio_id,
        symbol=symbol,
        side=side,  # type: ignore[arg-type]
        order_type=order_type,  # type: ignore[arg-type]
        volume=volume,
        price=price,
        status=status,  # type: ignore[arg-type]
        filled_volume=filled_volume,
        created_at=now,
        updated_at=updated_at or now,
    )


@router.get("", response_model=PaginatedList[Order])
async def list_orders(
    settings: Annotated[Settings, Depends(get_settings)],
    _principal: Annotated[AuthenticatedPrincipal, require_scope("read:portfolio")],
    pagination: Annotated[Pagination, Depends()],
) -> PaginatedList[Order]:
    """List orders (DB-backed when DEMO_DATA=0)."""
    if not settings.demo_data:
        async with get_sessionmaker()() as session:
            repo = OrderRepository(session)
            items, total = await repo.list(limit=pagination.limit, offset=pagination.offset)
            return PaginatedList(
                items=[_to_schema(o) for o in items],
                total=total,
                limit=pagination.limit,
                offset=pagination.offset,
            )
    items = [_demo_order(order_id=uuid4())]
    return PaginatedList(
        items=items,
        total=len(items),
        limit=pagination.limit,
        offset=pagination.offset,
    )


@router.get("/{order_id}", response_model=Order)
async def get_order(
    order_id: UUID,
    settings: Annotated[Settings, Depends(get_settings)],
    _principal: Annotated[AuthenticatedPrincipal, require_scope("read:portfolio")],
) -> Order:
    """Return a single order (DB-backed when DEMO_DATA=0)."""
    if not settings.demo_data:
        async with get_sessionmaker()() as session:
            repo = OrderRepository(session)
            order = await repo.get(order_id)
            if order is None:
                raise RecordNotFoundError(f"order {order_id} not found")
            return _to_schema(order)
    return _demo_order(order_id=order_id)


@router.post(
    "",
    response_model=Order,
    status_code=201,
    dependencies=[Depends(rate_limit_dependency)],
)
async def create_order(
    request: CreateOrderRequest,
    settings: Annotated[Settings, Depends(get_settings)],
    _principal: Annotated[AuthenticatedPrincipal, require_scope("write:orders")],
) -> Order:
    """Submit a new order (persisted when DEMO_DATA=0)."""
    order_id = uuid4()
    if not settings.demo_data:
        async with get_sessionmaker()() as session:
            repo = OrderRepository(session)
            order = await repo.create(
                order_id=order_id,
                portfolio_id=request.portfolio_id,
                symbol=request.symbol,
                side=request.side,
                order_type=request.order_type,
                volume=request.volume,
                price=request.price,
            )
            return _to_schema(order)
    return _demo_order(
        order_id=order_id,
        portfolio_id=request.portfolio_id,
        symbol=request.symbol,
        side=request.side,
        order_type=request.order_type,
        volume=request.volume,
        price=request.price,
        status="pending",
        filled_volume=Decimal(0),
    )


@router.patch(
    "/{order_id}",
    response_model=Order,
    dependencies=[Depends(rate_limit_dependency)],
)
async def modify_order(
    order_id: UUID,
    request: ModifyOrderRequest,
    settings: Annotated[Settings, Depends(get_settings)],
    _principal: Annotated[AuthenticatedPrincipal, require_scope("write:orders")],
) -> Order:
    """Modify price/volume of a pending order (ModifyOrderDialog contract)."""
    if not settings.demo_data:
        async with get_sessionmaker()() as session:
            repo = OrderRepository(session)
            order = await repo.get(order_id)
            if order is None:
                raise RecordNotFoundError(f"order {order_id} not found")
            try:
                updated = await repo.modify(order_id, price=request.price, volume=request.volume)
            except ValueError as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc
            assert updated is not None
            return _to_schema(updated)
    return _demo_order(
        order_id=order_id,
        volume=request.volume if request.volume is not None else Decimal("1.50"),
        price=request.price if request.price is not None else Decimal("2435.80"),
        status="pending",
        filled_volume=Decimal(0),
    )


@router.get("/{order_id}/history", response_model=PaginatedList[OrderHistoryEntry])
async def order_history(
    order_id: UUID,
    _principal: Annotated[AuthenticatedPrincipal, require_scope("read:portfolio")],
    pagination: Annotated[Pagination, Depends()],
) -> PaginatedList[OrderHistoryEntry]:
    """Append-only state transitions for one order (B-06 order history).

    Demo path yields a deterministic lifecycle (submitted → pending →
    filled); the DB path reads ``order_state_transitions`` when storage
    wiring lands.
    """
    now = datetime.now(UTC)
    demo_transitions = [
        ("submitted", "pending", "execution_controller", "order submitted"),
        ("pending", "filled", "execution_controller", "fill confirmed"),
    ]
    items = [
        OrderHistoryEntry(
            order_id=order_id,
            previous_state=prev,
            new_state=next_state,
            actor_role=actor,
            reason=reason,
            decision_ts=now - timedelta(seconds=(len(demo_transitions) - i) * 60),
        )
        for i, (prev, next_state, actor, reason) in enumerate(demo_transitions)
    ]
    visible = items[pagination.offset : pagination.offset + pagination.limit]
    return PaginatedList(items=visible, total=len(items), limit=pagination.limit, offset=pagination.offset)


@router.post(
    "/bulk-status",
    response_model=BulkStatusResult,
    dependencies=[Depends(rate_limit_dependency)],
)
async def bulk_order_status(
    request: BulkStatusRequest,
    settings: Annotated[Settings, Depends(get_settings)],
    _principal: Annotated[AuthenticatedPrincipal, require_scope("read:portfolio")],
) -> BulkStatusResult:
    """Batch order status check (B-06)."""
    if not settings.demo_data:
        from lumine.data.repositories import OrderRepository
        from lumine.data.session import get_sessionmaker

        async with get_sessionmaker()() as session:
            repo = OrderRepository(session)
            statuses = await repo.bulk_status(request.order_ids)
            return BulkStatusResult(statuses=statuses, total=len(statuses))
    statuses = {str(order_id): "filled" for order_id in request.order_ids}
    return BulkStatusResult(statuses=statuses, total=len(statuses))


@router.delete(
    "/{order_id}",
    response_model=Order,
    dependencies=[Depends(rate_limit_dependency)],
)
async def cancel_order(
    order_id: UUID,
    settings: Annotated[Settings, Depends(get_settings)],
    _principal: Annotated[AuthenticatedPrincipal, require_scope("write:orders")],
) -> Order:
    """Cancel an open order (persisted when DEMO_DATA=0)."""
    if not settings.demo_data:
        async with get_sessionmaker()() as session:
            repo = OrderRepository(session)
            order = await repo.get(order_id)
            if order is None:
                raise RecordNotFoundError(f"order {order_id} not found")
            cancelled = await repo.update_status(order_id, status="cancelled")
            assert cancelled is not None
            return _to_schema(cancelled)
    return _demo_order(order_id=order_id, status="cancelled", filled_volume=Decimal(0))
