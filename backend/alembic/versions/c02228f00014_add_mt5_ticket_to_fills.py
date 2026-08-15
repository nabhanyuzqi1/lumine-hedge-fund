"""add mt5_ticket to fills

Revision ID: c02228f00014
Revises: c02228f00013
Create Date: 2026-08-15 16:15:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c02228f00014'
down_revision: Union[str, None] = 'c02228f00013'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # B1: deal MT5 → fills. Dedupe by ticket (snapshot deals dikirim tiap
    # 30s — tanpa kolom ini, deal sama ter-insert berulang).
    op.add_column(
        "fills",
        sa.Column("mt5_ticket", sa.BigInteger(), nullable=True),
    )
    op.create_index(
        "ix_fills_mt5_ticket",
        "fills",
        ["mt5_ticket"],
        unique=True,
        postgresql_where=sa.text("mt5_ticket IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_fills_mt5_ticket", table_name="fills")
    op.drop_column("fills", "mt5_ticket")
