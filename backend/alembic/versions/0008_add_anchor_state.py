# Copyright (c) 2026 Lumine. All rights reserved.
"""Add anchor-cadence bookkeeping table (ADR-0017, sprint 7 J4).

Creates ``anchor_state`` — one row per chained table tracking the
anchor checkpoint (last anchor seq, last row count, last anchor ts).
Writers check the N-rows / M-minutes thresholds against this row
inside the per-table chain lock so concurrent writers cannot
double-anchor.

Revision ID: 0008
Revises: 0007
Create Date: 2026-08-12
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "anchor_state",
        sa.Column("table_name", sa.Text(), nullable=False, primary_key=True),
        sa.Column("last_anchor_seq", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("last_row_count", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("last_anchor_ts", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("anchor_state")