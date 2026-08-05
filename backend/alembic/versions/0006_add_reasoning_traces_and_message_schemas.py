# Copyright (c) 2026 Lumine. All rights reserved.
"""Add reasoning_traces and message_schema_versions tables.

reasoning_traces (Phase 7 D7-11): one row per LLM call, written
synchronously before the stage advances. Stores the full prompt sent,
raw response, parsed output, and SHA-256 hashes for reproducibility.
lineage_records.proposal.reasoning_trace_ids references these rows.

message_schema_versions (Phase 4 inter-agent-message-versioning.md):
registry of versioned message schemas (analyst_output, ic_output,
proposal, etc.). Each row: name, semver version, JSON-Schema draft-07,
compatibility, code_hash, status. Only `production` rows emitted at
runtime; retired rows stay pinned in lineage forever.

Revision ID: 0006
Revises: 0005
Create Date: 2026-08-03
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "reasoning_traces",
        sa.Column("trace_id", sa.UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("workflow_run_id", sa.Text(), nullable=False),
        sa.Column("stage_run_id", sa.Text(), nullable=False),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("model_version_id", sa.UUID(), sa.ForeignKey("model_versions.id"), nullable=False),
        sa.Column("prompt_version_id", sa.UUID(), sa.ForeignKey("prompt_versions.id"), nullable=True),
        sa.Column("prompt_sent", sa.Text(), nullable=False),
        sa.Column("response_raw", sa.Text(), nullable=False),
        sa.Column("parsed_output", sa.JSON(), nullable=True),
        sa.Column("prompt_hash", sa.Text(), nullable=False),
        sa.Column("response_hash", sa.Text(), nullable=False),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("lineage_id", sa.UUID(), sa.ForeignKey("lineage_records.lineage_id"), nullable=True),
        sa.Index("ix_reasoning_traces_workflow", "workflow_run_id", "ts"),
        sa.Index("ix_reasoning_traces_lineage", "lineage_id"),
        sa.Index("ix_reasoning_traces_role", "role", "ts"),
    )

    op.create_table(
        "message_schema_versions",
        sa.Column("id", sa.UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("version", sa.Text(), nullable=False),
        sa.Column("schema", sa.JSON(), nullable=False),
        sa.Column("compatibility", sa.Text(), nullable=False),
        sa.Column("code_hash", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("superseded_by", sa.UUID(), sa.ForeignKey("message_schema_versions.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("retired_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("name", "version", name="uq_message_schema_name_version"),
        sa.Index("ix_message_schema_status", "status"),
    )


def downgrade() -> None:
    op.drop_table("message_schema_versions")
    op.drop_table("reasoning_traces")
