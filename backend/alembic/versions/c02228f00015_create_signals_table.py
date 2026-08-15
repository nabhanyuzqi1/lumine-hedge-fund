"""create signals table

Revision ID: c02228f00015
Revises: c02228f00014
Create Date: 2026-08-15 17:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c02228f00015'
down_revision: Union[str, None] = 'c02228f00014'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # B5: analyst signals dari decision cycle LLM → dashboard
    # (AI committee confidence, analyst signals panel, decision card).
    op.create_table(
        "signals",
        sa.Column("signal_id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("run_id", sa.Text(), nullable=False),
        sa.Column("symbol", sa.Text(), nullable=False),
        sa.Column("analyst", sa.Text(), nullable=False),
        sa.Column("direction", sa.Text(), nullable=False),  # bullish/bearish/neutral
        sa.Column("confidence", sa.Numeric(5, 4), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_signals_symbol_generated", "signals", ["symbol", "generated_at"])
    op.create_index("ix_signals_run", "signals", ["run_id"])


def downgrade() -> None:
    op.drop_table("signals")
