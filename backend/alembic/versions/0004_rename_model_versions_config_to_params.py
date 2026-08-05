# Copyright (c) 2026 Lumine. All rights reserved.
"""Rename model_versions.config -> params (align to Phase 6 model-registry.md).

Phase 6 `model-registry.md` line 17 declares the column `params`
(temperature, max_tokens, etc. — part of model identity). Migration 0001
created it as `config`. This rename reconciles the physical schema to the
spec so the LLM gateway can resolve model parameters by the documented
name. Decision D3-4 (Sprint 3 plan).

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-03
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "model_versions",
        "config",
        new_column_name="params",
        existing_type=sa.JSON(),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "model_versions",
        "params",
        new_column_name="config",
        existing_type=sa.JSON(),
        existing_nullable=False,
    )
