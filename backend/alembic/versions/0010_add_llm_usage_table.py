# Copyright (c) 2026 Lumine. All rights reserved.

"""Add LLM usage tracking table per D6-7.

Revision ID: 0010
Revises: 0009
Create Date: 2026-08-13

Adds llm_usage table for cost accounting of all LLM calls via 9router gateway.
"""

from datetime import datetime
from typing import Optional

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = '0010'
down_revision = '0009'
branch_labels: Optional[str] = None
depends_on: Optional[str] = None


def upgrade() -> None:
    """Create llm_usage table for append-only cost tracking."""
    op.create_table(
        "llm_usage",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("model_version_id", sa.String(length=255), nullable=False),
        sa.Column("provider", sa.String(length=100), nullable=False),
        sa.Column("model_name", sa.String(length=100), nullable=False),
        sa.Column("timestamp", sa.DateTime(), nullable=False, default=datetime.utcnow),
        sa.Column("tokens_prompt", sa.Integer(), nullable=False, default=0),
        sa.Column("tokens_completion", sa.Integer(), nullable=False, default=0),
        sa.Column("cost_usd", sa.Float(), nullable=False, default=0.0),
        sa.Column("lineage_id", sa.String(length=255), nullable=True),
        sa.Column("role", sa.String(length=100), nullable=False, default="unknown"),
        sa.Column("fallback_hops", sa.Integer(), nullable=False, default=0),
        sa.Column("error", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_llm_usage"),
    )

    # Indexes for common query patterns
    op.create_index("ix_llm_usage_timestamp", "llm_usage", ["timestamp"])
    op.create_index("ix_llm_usage_lineage", "llm_usage", ["lineage_id"])
    op.create_index("ix_llm_usage_model", "llm_usage", ["model_version_id"])


def downgrade() -> None:
    """Remove llm_usage table."""
    op.drop_index("ix_llm_usage_model", table_name="llm_usage")
    op.drop_index("ix_llm_usage_lineage", table_name="llm_usage")
    op.drop_index("ix_llm_usage_timestamp", table_name="llm_usage")
    op.drop_table("llm_usage")
