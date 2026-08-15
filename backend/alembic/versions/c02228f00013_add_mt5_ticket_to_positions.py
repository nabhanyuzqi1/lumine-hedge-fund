"""add mt5_ticket to positions

Revision ID: c02228f00013
Revises: c02228eed4e7
Create Date: 2026-08-15 15:20:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c02228f00013'
down_revision: Union[str, None] = 'c02228eed4e7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Sync MT5 open positions → tabel positions (B1 fix). Kolom mt5_ticket
    # dipakai PositionSyncWorker upsert (ON CONFLICT mt5_ticket).
    op.add_column(
        "positions",
        sa.Column("mt5_ticket", sa.BigInteger(), nullable=True),
    )
    op.create_index(
        "ix_positions_mt5_ticket",
        "positions",
        ["mt5_ticket"],
        unique=True,
        postgresql_where=sa.text("mt5_ticket IS NOT NULL"),
    )
    # Posisi dari MT5 snapshot tidak punya lineage (source = broker, bukan
    # pipeline decision) — opened_lineage wajib nullable.
    op.alter_column("positions", "opened_lineage", nullable=True)


def downgrade() -> None:
    op.alter_column("positions", "opened_lineage", nullable=False)
    op.drop_index("ix_positions_mt5_ticket", table_name="positions")
    op.drop_column("positions", "mt5_ticket")
