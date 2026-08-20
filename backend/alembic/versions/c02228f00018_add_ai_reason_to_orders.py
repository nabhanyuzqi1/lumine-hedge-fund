"""add ai_reason to orders

Revision ID: c02228f00018
Revises: c02228f00017
Create Date: 2026-08-20 02:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c02228f00018'
down_revision: Union[str, None] = 'c02228f00017'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # A5 (19 Aug 2026): alasan keputusan LLM per order (buy/sell/TP/action,
    # entry area, analyst alignment, profile, model) — JSON string. Detail
    # order wajib menampilkan mengapa AI mengambil keputusan ini (user req).
    op.add_column(
        "orders",
        sa.Column("ai_reason", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("orders", "ai_reason")