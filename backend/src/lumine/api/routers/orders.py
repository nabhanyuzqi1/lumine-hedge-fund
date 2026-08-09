# Copyright (c) 2026 Lumine. All rights reserved.
"""Order lifecycle REST endpoints."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends

from lumine.api.middleware.auth import AuthenticatedPrincipal, require_scope
from lumine.api.middleware.rate_limit import rate_limit_dependency
from lumine.api.schemas.api import CreateOrderRequest, Order
from lumine.api.schemas.common import PaginatedList, Pagination

router = APIRouter(prefix="/orders", tags=["orders"])


@router.get("", response_model=PaginatedList[Order])
async def list_orders(
    _principal: Annotated[AuthenticatedPrincipal, require_scope("read:portfolio")],
    pagination: Annotated[Pagination, Depends()],
) -> PaginatedList[Order]:
    """List orders."""
    now = datetime.now(UTC)
    items: list[Order] = [
        Order(
            order_id=uuid4(),
            portfolio_id="default",
            symbol="XAUUSD",
            side="buy",
            order_type="market",
            volume=Decimal("1.50"),
            status="filled",
            filled_volume=Decimal("1.50"),
            created_at=now,
            updated_at=now,
        ),
    ]
    return PaginatedList(
        items=items,
        total=len(items),
        limit=pagination.limit,
        offset=pagination.offset,
    )


@router.get("/{order_id}", response_model=Order)
async def get_order(
    order_id: UUID,
    _principal: Annotated[AuthenticatedPrincipal, require_scope("read:portfolio")],
) -> Order:
    """Return a single order."""
    now = datetime.now(UTC)
    return Order(
        order_id=order_id,
        portfolio_id="default",
        symbol="XAUUSD",
        side="buy",
        order_type="market",
        volume=Decimal("1.50"),
        status="filled",
        filled_volume=Decimal("1.50"),
        created_at=now,
        updated_at=now,
    )


@router.post(
    "",
    response_model=Order,
    status_code=201,
    dependencies=[Depends(rate_limit_dependency)],
)
async def create_order(
    request: CreateOrderRequest,
    _principal: Annotated[AuthenticatedPrincipal, require_scope("write:orders")],
) -> Order:
    """Submit a new order."""
    now = datetime.now(UTC)
    return Order(
        order_id=uuid4(),
        portfolio_id=request.portfolio_id,
        symbol=request.symbol,
        side=request.side,
        order_type=request.order_type,
        volume=request.volume,
        price=request.price,
        status="pending",
        filled_volume=Decimal(0),
        created_at=now,
        updated_at=now,
    )


@router.delete(
    "/{order_id}",
    response_model=Order,
    dependencies=[Depends(rate_limit_dependency)],
)
async def cancel_order(
    order_id: UUID,
    _principal: Annotated[AuthenticatedPrincipal, require_scope("write:orders")],
) -> Order:
    """Cancel an open order."""
    now = datetime.now(UTC)
    return Order(
        order_id=order_id,
        portfolio_id="default",
        symbol="XAUUSD",
        side="buy",
        order_type="market",
        volume=Decimal("1.50"),
        status="cancelled",
        filled_volume=Decimal(0),
        created_at=now,
        updated_at=now,
    )
