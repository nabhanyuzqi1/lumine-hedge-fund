# Copyright (c) 2026 Lumine. All rights reserved.
"""Add TCA records and execution quality tables (ADR-0040, sprint 7 J1-J3).

Creates `tca_records` — one row per fill with slippage in price, bps, and
account currency. Also adds missing brokers, accounts, and journal_hash_chain
columns that were deferred from earlier migrations.

Revision ID: 0009
Revises: 0008
Create Date: 2026-08-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Add brokers table (multi-broker support, ADR-0024)
    op.create_table(
        "brokers",
        sa.Column("broker_id", sa.Text(), nullable=False, primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("config", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    # Add accounts table
    op.create_table(
        "accounts",
        sa.Column("account_id", sa.Text(), nullable=False, primary_key=True),
        sa.Column("broker_id", sa.Text(), nullable=False),
        sa.Column("account_number", sa.Text(), nullable=False),
        sa.Column("currency", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("config", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    
    # Add broker account foreign key
    op.create_foreign_key(
        "accounts_broker_id_fkey",
        "accounts",
        "brokers",
        ["broker_id"],
        ["broker_id"],
        ondelete="CASCADE",
    )

    # NOTE: tca_records is created by 0007_add_audit_hardening (ADR-0040,
    # schema matches data/models.py: tca_id UUID PK, fill_id UUID FK).
    # This migration only adds brokers/accounts FKs + query indexes to it.

    # Add foreign keys for TCA (broker/account slices; fill_id FK already
    # exists from 0007's inline ForeignKey)
    op.create_foreign_key(
        "tca_records_broker_id_fkey",
        "tca_records",
        "brokers",
        ["broker_id"],
        ["broker_id"],
        ondelete="RESTRICT",
    )
    
    op.create_foreign_key(
        "tca_records_account_id_fkey",
        "tca_records",
        "accounts",
        ["account_id"],
        ["account_id"],
        ondelete="RESTRICT",
    )

    # Create indexes for common queries
    op.create_index(
        "idx_tca_records_decision_ts",
        "tca_records",
        ["decision_ts"],
    )
    
    op.create_index(
        "idx_tca_records_regime_id",
        "tca_records",
        ["regime_id"],
    )
    
    op.create_index(
        "idx_tca_records_broker_id",
        "tca_records",
        ["broker_id"],
    )

    # Add journal_hash_chain column to workflow_journal if not exists
    try:
        op.add_column("workflow_journal", sa.Column("hash_chain_anchor", sa.Text(), nullable=True))
    except Exception:
        pass  # Column may already exist


def downgrade() -> None:
    op.drop_constraint("journal_hash_anchor_fkey", "workflow_journal", type_="foreignkey")
    op.drop_column("workflow_journal", "hash_chain_anchor")

    op.drop_index("idx_tca_records_broker_id", "tca_records")
    op.drop_index("idx_tca_records_regime_id", "tca_records")
    op.drop_index("idx_tca_records_decision_ts", "tca_records")

    op.drop_constraint("tca_records_account_id_fkey", "tca_records", type_="foreignkey")
    op.drop_constraint("tca_records_broker_id_fkey", "tca_records", type_="foreignkey")

    op.drop_table("accounts")
    op.drop_table("brokers")
