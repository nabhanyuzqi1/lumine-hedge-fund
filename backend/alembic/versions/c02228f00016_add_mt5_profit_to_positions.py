"""add mt5_profit to positions

Revision ID: c02228f00016
Revises: c02228f00015
Create Date: 2026-08-15 17:30:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c02228f00016'
down_revision: Union[str, None] = 'c02228f00015'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # B8: unrealized P&L REAL dari MT5 (broker menghitung dengan contract
    # spec & spread aktual) — disimpan tiap snapshot, API pakai nilai ini
    # bila ada (lebih akurat dari (current - avg_entry) * size).
    op.add_column(
        "positions",
        sa.Column("mt5_profit", sa.Numeric(20, 2), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("positions", "mt5_profit")
