"""Add feature/regime/calendar registry tables and expand lineage version pins.

Creates feature_versions, regime_versions, calendar_versions tables.
Expands lineage_records from 4 to 7 version pins:
- Replaces single model_version_id/prompt_version_id with per-agent JSONB maps
- Adds feature_version_id, regime_version_id, calendar_version_id FKs

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ENUM, JSONB, UUID

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # registry_status enum created in migration 0001; reuse without recreating.
    _registry_status = ENUM(
        "sandbox", "staging", "production", "retired",
        name="registry_status",
        create_type=False,
    )

    # ── Feature versions registry ─────────────────────────────────────────
    op.create_table(
        "feature_versions",
        sa.Column("id", UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("version", sa.String(32), nullable=False),
        sa.Column("status", _registry_status, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("retired_at", sa.DateTime(timezone=True)),
        sa.Column("params", JSONB(), nullable=False),
        sa.Column("code_hash", sa.Text(), nullable=False),
        sa.Column("warmup_required", sa.Integer(), nullable=False),
        sa.Column("superseded_by", UUID(), sa.ForeignKey("feature_versions.id")),
        sa.UniqueConstraint("name", "version"),
        sa.Index("ix_feature_versions_name", "name"),
    )

    # ── Regime versions registry ──────────────────────────────────────────
    op.create_table(
        "regime_versions",
        sa.Column("id", UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("version", sa.String(32), nullable=False),
        sa.Column(
            "status",
            _registry_status,
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("retired_at", sa.DateTime(timezone=True)),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("code_hash", sa.Text(), nullable=False),
        sa.Column("buckets", JSONB(), nullable=False),
        sa.Column("description", sa.Text()),
        sa.UniqueConstraint("version"),
    )

    # ── Calendar versions registry ────────────────────────────────────────
    op.create_table(
        "calendar_versions",
        sa.Column("id", UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("version", sa.String(32), nullable=False),
        sa.Column(
            "status",
            _registry_status,
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("retired_at", sa.DateTime(timezone=True)),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("holidays", JSONB(), nullable=False),
        sa.Column("sessions", JSONB(), nullable=False),
        sa.Column("economic_events", JSONB()),
        sa.UniqueConstraint("version"),
    )

    # ── Expand lineage_records version pins ───────────────────────────────
    # Replace single model/prompt FKs with per-agent JSONB maps
    op.add_column("lineage_records", sa.Column("model_version_ids", JSONB(), nullable=True))
    op.add_column("lineage_records", sa.Column("prompt_version_ids", JSONB(), nullable=True))

    # Add new scalar version pin FKs (nullable until registry tables are populated)
    op.add_column("lineage_records", sa.Column("feature_version_id", UUID(), nullable=True))
    op.add_column("lineage_records", sa.Column("regime_version_id", UUID(), nullable=True))
    op.add_column("lineage_records", sa.Column("calendar_version_id", UUID(), nullable=True))

    op.create_foreign_key(
        "fk_lineage_feature_version",
        "lineage_records", "feature_versions",
        ["feature_version_id"], ["id"],
    )
    op.create_foreign_key(
        "fk_lineage_regime_version",
        "lineage_records", "regime_versions",
        ["regime_version_id"], ["id"],
    )
    op.create_foreign_key(
        "fk_lineage_calendar_version",
        "lineage_records", "calendar_versions",
        ["calendar_version_id"], ["id"],
    )

    op.create_index("ix_lineage_feature_version", "lineage_records", ["feature_version_id"])

    # Drop old single-FK columns (data migration skipped — no production data yet)
    op.drop_constraint("lineage_records_model_version_id_fkey", "lineage_records", type_="foreignkey")
    op.drop_constraint("lineage_records_prompt_version_id_fkey", "lineage_records", type_="foreignkey")
    op.drop_column("lineage_records", "model_version_id")
    op.drop_column("lineage_records", "prompt_version_id")


def downgrade() -> None:
    # Restore old single-FK columns
    op.add_column("lineage_records", sa.Column("model_version_id", UUID(), nullable=True))
    op.add_column("lineage_records", sa.Column("prompt_version_id", UUID(), nullable=True))
    op.create_foreign_key(
        "lineage_records_model_version_id_fkey",
        "lineage_records", "model_versions",
        ["model_version_id"], ["id"],
    )
    op.create_foreign_key(
        "lineage_records_prompt_version_id_fkey",
        "lineage_records", "prompt_versions",
        ["prompt_version_id"], ["id"],
    )

    # Drop new columns
    op.drop_index("ix_lineage_feature_version", table_name="lineage_records")
    op.drop_constraint("fk_lineage_calendar_version", "lineage_records", type_="foreignkey")
    op.drop_constraint("fk_lineage_regime_version", "lineage_records", type_="foreignkey")
    op.drop_constraint("fk_lineage_feature_version", "lineage_records", type_="foreignkey")
    op.drop_column("lineage_records", "calendar_version_id")
    op.drop_column("lineage_records", "regime_version_id")
    op.drop_column("lineage_records", "feature_version_id")
    op.drop_column("lineage_records", "prompt_version_ids")
    op.drop_column("lineage_records", "model_version_ids")

    # Drop new registry tables
    op.drop_table("calendar_versions")
    op.drop_table("regime_versions")
    op.drop_table("feature_versions")