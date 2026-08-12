# Copyright (c) 2026 Lumine. All rights reserved.
"""Add audit-hardening schema: hash-chain columns, audit_anchors, tca_records.

Sprint 7 (audit hardening) — ADR-0017 (hash-chained WORM-anchored audit
journal), ADR-0040 (TCA + execution quality).

Adds to the three chained tables (lineage_records, workflow_journal,
reasoning_traces):
  - ``prev_hash`` TEXT NOT NULL
  - ``self_hash`` TEXT NOT NULL
  - ``canonicalization_version`` SMALLINT NOT NULL DEFAULT 1
  (ADR-0017 D12-7; ``canonicalization_version`` pins the byte-exact
  canonical-JSON rules used to produce the hashes.)

Creates:
  - ``audit_anchors`` (append-only chain-head anchors; ADR-0017
    logical DDL — anchored_hash payload duplicated to the WORM sink).
  - ``tca_records`` (1:1 per fill; ADR-0040 — arrival-mid benchmark,
    slippage bps + cost, regime/broker/account slicing).

Also ships the D12-8 grant hardening (audit_writer role, REVOKEs).
Local dev/test DBs run as a superuser so the grants are documented
and validated by tests, not enforced locally; enforcement is a
Phase 11/VPS operator action.

Revision ID: 0007
Revises: 0006
Create Date: 2026-08-12
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CHAINED_TABLES = ("lineage_records", "workflow_journal", "reasoning_traces")


def _add_chain_columns(table: str) -> None:
    op.add_column(table, sa.Column("prev_hash", sa.Text(), nullable=False))
    op.add_column(table, sa.Column("self_hash", sa.Text(), nullable=False))
    op.add_column(
        table,
        sa.Column(
            "canonicalization_version",
            sa.SmallInteger(),
            nullable=False,
            server_default=sa.text("1"),
        ),
    )


def _remove_chain_columns(table: str) -> None:
    op.drop_column(table, "canonicalization_version")
    op.drop_column(table, "self_hash")
    op.drop_column(table, "prev_hash")


def upgrade() -> None:
    # ── 1. Hash-chain columns (ADR-0017 D12-7) ────────────────────────────
    for table in CHAINED_TABLES:
        _add_chain_columns(table)

    # ── 2. audit_anchors (ADR-0017) ───────────────────────────────────────
    op.create_table(
        "audit_anchors",
        sa.Column(
            "anchor_id", sa.UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column("table_name", sa.Text(), nullable=False),
        sa.Column("anchor_seq", sa.BigInteger(), nullable=False),
        sa.Column("anchored_hash", sa.Text(), nullable=False),
        sa.Column("anchored_row_id", sa.UUID(), nullable=False),
        sa.Column("row_count", sa.BigInteger(), nullable=False),
        sa.Column(
            "anchored_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("worm_object_key", sa.Text(), nullable=False),
        sa.Column("worm_backend", sa.Text(), nullable=False),
        sa.UniqueConstraint("table_name", "anchor_seq", name="uq_audit_anchors_table_seq"),
        sa.Index("ix_audit_anchors_table_ts", "table_name", "anchored_at"),
    )

    # ── 3. tca_records (ADR-0040) ─────────────────────────────────────────
    op.create_table(
        "tca_records",
        sa.Column(
            "tca_id", sa.UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column("fill_id", sa.UUID(), sa.ForeignKey("fills.fill_id"), nullable=False),
        sa.Column("benchmark_price", sa.Numeric(20, 5), nullable=False),
        sa.Column("slippage_bps", sa.Numeric(10, 4), nullable=False),
        sa.Column("slippage_cost_ccy", sa.Numeric(20, 4), nullable=False),
        sa.Column("decision_ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("regime_id", sa.Text(), nullable=False),
        sa.Column("broker_id", sa.Text(), nullable=False),
        sa.Column("account_id", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "benchmark_source", sa.Text(), nullable=False, server_default=sa.text("'arrival_mid'")
        ),
        sa.UniqueConstraint("fill_id", name="uq_tca_fill"),
        sa.Index("ix_tca_decision_ts", "decision_ts"),
        sa.Index("ix_tca_broker_ts", "broker_id", "decision_ts"),
    )

    # ── 4. D12-8 grant hardening (audit_writer role + REVOKEs) ────────────
    op.execute(
        """
        CREATE ROLE audit_writer NOLOGIN;
        GRANT INSERT ON lineage_records, workflow_journal, reasoning_traces, audit_anchors TO audit_writer;
        REVOKE UPDATE, DELETE ON lineage_records, workflow_journal, reasoning_traces, audit_anchors FROM audit_writer;
        REVOKE TRUNCATE ON lineage_records, workflow_journal, reasoning_traces, audit_anchors FROM audit_writer;
        """
    )


def downgrade() -> None:
    op.execute("DROP ROLE IF EXISTS audit_writer;")
    op.drop_table("tca_records")
    op.drop_table("audit_anchors")
    for table in CHAINED_TABLES:
        _remove_chain_columns(table)
