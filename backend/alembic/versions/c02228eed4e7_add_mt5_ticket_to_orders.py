"""add mt5_ticket to orders

Revision ID: c02228eed4e7
Revises: 0012
Create Date: 2026-08-15 01:42:34.809776
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c02228eed4e7'
down_revision: Union[str, None] = '0012'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Model Order.mt5_ticket (models.py:511) tidak pernah di-migrasi ke tabel
    # orders — drift model vs DB. Kolom dipakai on_order_fill → sync ticket MT5.
    op.add_column(
        "orders",
        sa.Column("mt5_ticket", sa.BigInteger(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("orders", "mt5_ticket")