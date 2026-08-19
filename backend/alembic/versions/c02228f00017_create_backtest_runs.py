"""backtest_runs table (18 Aug 2026) — master backtest 1 tahun.

Menyimpan hasil master backtest per profile: metrics + equity series +
learning digest. Dipakai learning loop (improve prompt AI).
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "c02228f00017"
down_revision = "c02228f00016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "backtest_runs",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("profile_id", sa.Text(), nullable=False),
        sa.Column("timeframe", sa.Text(), nullable=False),
        sa.Column("symbol", sa.Text(), nullable=False),
        sa.Column("bar_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("metrics_json", sa.JSON(), nullable=False),
        sa.Column("equity_json", sa.JSON(), nullable=False),
        sa.Column("learning_digest", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_backtest_runs_profile_created", "backtest_runs", ["profile_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_backtest_runs_profile_created", table_name="backtest_runs")
    op.drop_table("backtest_runs")