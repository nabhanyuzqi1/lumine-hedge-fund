# Copyright (c) 2026 Lumine. All rights reserved.
"""Create orders table (B-05 storage wiring).

The order domain previously lived entirely in demo data; this migration
adds the physical table so routers can persist orders when DEMO_DATA=0.
order_state_transitions.order_id (0001) was a bare UUID — now it gains a
real FK target.

Revision ID: 0011
Revises: 0009
Create Date: 2026-08-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "orders",
        sa.Column("order_id", sa.Uuid(), primary_key=True),
        sa.Column("portfolio_id", sa.Text(), nullable=False),
        sa.Column("symbol", sa.Text(), nullable=False),
        sa.Column("side", sa.Text(), nullable=False),
        sa.Column("order_type", sa.Text(), nullable=False),
        sa.Column("volume", sa.Numeric(20, 4), nullable=False),
        sa.Column("price", sa.Numeric(20, 5), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("filled_volume", sa.Numeric(20, 4), nullable=False, server_default="0"),
        sa.Column("rejected_reason", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Index("ix_orders_portfolio_status", "portfolio_id", "status"),
        sa.Index("ix_orders_symbol_created", "symbol", "created_at"),
    )


def downgrade() -> None:
    op.drop_table("orders")
