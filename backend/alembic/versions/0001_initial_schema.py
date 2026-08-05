"""Initial schema — all Phase 3/5 tables.

Creates the full registry, decision, execution, market-data, and
operational tables per the physical ERD.

Revision ID: 0001
Revises: None
Create Date: 2026-08-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ENUM, JSONB, UUID

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ── Enum types ──────────────────────────────────────────────────────
    # Created explicitly here. PostgreSQL ENUM columns below reuse it
    # without emitting a second CREATE TYPE statement.
    _registry_status = ENUM(
        "sandbox", "staging", "production", "retired",
        name="registry_status",
        create_type=False,
    )
    op.execute("CREATE TYPE registry_status AS ENUM ('sandbox', 'staging', 'production', 'retired')")

    # ── Registry tables ──────────────────────────────────────────────────
    op.create_table(
        "model_versions",
        sa.Column("id", UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("version", sa.String(32), nullable=False),
        sa.Column("status", _registry_status, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("retired_at", sa.DateTime(timezone=True)),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("model_id", sa.Text(), nullable=False),
        sa.Column("tier", sa.Text(), nullable=False),
        sa.Column("context_window", sa.BigInteger(), nullable=False),
        sa.Column("config", JSONB(), nullable=False),
        sa.UniqueConstraint("version"),
        sa.Index("ix_model_versions_status", "status"),
    )

    op.create_table(
        "prompt_versions",
        sa.Column("id", UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("version", sa.String(32), nullable=False),
        sa.Column("status", _registry_status, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("retired_at", sa.DateTime(timezone=True)),
        sa.Column("sub_role", sa.Text(), nullable=False),
        sa.Column("prompt_hash", sa.Text(), nullable=False),
        sa.Column("prompt_ref", sa.Text(), nullable=False),
        sa.Column("variables", JSONB(), nullable=False),
        sa.Column("output_schema", JSONB(), nullable=False),
        sa.UniqueConstraint("version"),
    )

    op.create_table(
        "strategy_versions",
        sa.Column("id", UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("version", sa.String(32), nullable=False),
        sa.Column("status", _registry_status, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("retired_at", sa.DateTime(timezone=True)),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("book", sa.Text(), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("params", JSONB(), nullable=False),
        sa.Column("entry_rules", JSONB(), nullable=False),
        sa.Column("exit_rules", JSONB(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("parent_id", UUID(), sa.ForeignKey("strategy_versions.id")),
        sa.UniqueConstraint("version"),
    )

    op.create_table(
        "policy_versions",
        sa.Column("id", UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("version", sa.String(32), nullable=False),
        sa.Column("status", _registry_status, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("retired_at", sa.DateTime(timezone=True)),
        sa.Column("scope", sa.Text(), nullable=False),
        sa.Column("policy_hash", sa.Text(), nullable=False),
        sa.Column("policy", JSONB(), nullable=False),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("effective_to", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("version"),
    )

    # ── Decision table ───────────────────────────────────────────────────
    op.create_table(
        "lineage_records",
        sa.Column("lineage_id", UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("decision_ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("book", sa.Text(), nullable=False),
        sa.Column("strategy_id", UUID(), sa.ForeignKey("strategy_versions.id"), nullable=False),
        sa.Column("symbol", sa.Text(), nullable=False),
        sa.Column("side", sa.Text(), nullable=False),
        sa.Column("verdict", sa.Text(), nullable=False),
        sa.Column("size", sa.Numeric(20, 4)),
        sa.Column("fill_price", sa.Numeric(20, 5)),
        sa.Column("model_version_id", UUID(), sa.ForeignKey("model_versions.id"), nullable=False),
        sa.Column("prompt_version_id", UUID(), sa.ForeignKey("prompt_versions.id"), nullable=False),
        sa.Column("policy_version_id", UUID(), sa.ForeignKey("policy_versions.id"), nullable=False),
        sa.Column("strategy_version_id", UUID(), sa.ForeignKey("strategy_versions.id"), nullable=False),
        sa.Column("trigger", JSONB(), nullable=False),
        sa.Column("features", JSONB()),
        sa.Column("proposal", JSONB(), nullable=False),
        sa.Column("risk_context", JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Index("ix_lineage_decision_ts", "decision_ts"),
        sa.Index("ix_lineage_book_ts", "book", "decision_ts"),
        sa.Index("ix_lineage_strategy", "strategy_id"),
        sa.Index("ix_lineage_verdict", "verdict"),
    )

    # ── Execution tables ─────────────────────────────────────────────────
    op.create_table(
        "fills",
        sa.Column("fill_id", UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("lineage_id", UUID(), sa.ForeignKey("lineage_records.lineage_id"), nullable=False),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("symbol", sa.Text(), nullable=False),
        sa.Column("side", sa.Text(), nullable=False),
        sa.Column("size", sa.Numeric(20, 4), nullable=False),
        sa.Column("price", sa.Numeric(20, 5), nullable=False),
        sa.Column("commission", sa.Numeric(20, 4), nullable=False),
        sa.Column("slippage", sa.Numeric(20, 5), nullable=False),
        sa.Column("book", sa.Text(), nullable=False),
        sa.Column("strategy_id", UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Index("ix_fills_lineage", "lineage_id"),
        sa.Index("ix_fills_ts", "ts"),
    )

    op.create_table(
        "positions",
        sa.Column("position_id", UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("symbol", sa.Text(), nullable=False),
        sa.Column("book", sa.Text(), nullable=False),
        sa.Column("strategy_id", UUID(), nullable=False),
        sa.Column("side", sa.Text(), nullable=False),
        sa.Column("size", sa.Numeric(20, 4), nullable=False),
        sa.Column("avg_entry", sa.Numeric(20, 5), nullable=False),
        sa.Column("sl", sa.Numeric(20, 5)),
        sa.Column("tp", sa.Numeric(20, 5)),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("opened_lineage", UUID(), sa.ForeignKey("lineage_records.lineage_id"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("status", sa.Text(), nullable=False, server_default="open"),
        sa.Index(
            "ix_positions_open",
            "symbol", "book", "strategy_id",
            unique=True,
            postgresql_where=sa.text("status = 'open'"),
        ),
    )

    op.create_table(
        "processed_commands",
        sa.Column("lineage_id", UUID(), sa.ForeignKey("lineage_records.lineage_id"), primary_key=True),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("result", sa.Text(), nullable=False),
        sa.Column("replay_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_replay_at", sa.DateTime(timezone=True)),
    )

    # ── Order state transition audit ─────────────────────────────────────
    op.create_table(
        "order_state_transitions",
        sa.Column("transition_id", UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("order_id", UUID(), nullable=False),
        sa.Column("previous_state", sa.String(20), nullable=False),
        sa.Column("new_state", sa.String(20), nullable=False),
        sa.Column("actor_role", sa.String(50), nullable=False),
        sa.Column("actor_id", sa.String(100)),
        sa.Column("reason", sa.Text()),
        sa.Column("decision_ts", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("lineage_record_id", UUID(), sa.ForeignKey("lineage_records.lineage_id"), nullable=False),
        sa.Column("mt5_ticket", sa.BigInteger()),
        sa.Column("transition_metadata", JSONB()),
        sa.CheckConstraint("previous_state != new_state", name="ck_order_transitions_valid_transition"),
        sa.CheckConstraint(
            "new_state NOT IN ('REJECTED', 'CANCELLED', 'FAILED') OR reason IS NOT NULL",
            name="ck_order_transitions_reason_required",
        ),
        sa.Index("ix_order_transitions_order_id", "order_id"),
        sa.Index("ix_order_transitions_lineage", "lineage_record_id"),
        sa.Index("ix_order_transitions_decision_ts", "decision_ts"),
    )

    # ── Market data tables (partitioned parents) ─────────────────────────
    op.create_table(
        "ticks",
        sa.Column("ts", sa.DateTime(timezone=True), primary_key=True, nullable=False),
        sa.Column("symbol", sa.Text(), primary_key=True, nullable=False),
        sa.Column("bid", sa.Numeric(20, 5), nullable=False),
        sa.Column("ask", sa.Numeric(20, 5), nullable=False),
        sa.Column("last", sa.Numeric(20, 5), nullable=False),
        sa.Column("volume", sa.Numeric(20, 2), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Index("ix_ticks_symbol_ts", "symbol", "ts"),
        postgresql_partition_by="RANGE (ts)",
    )

    for tname in ("bars_1m", "bars_5m"):
        op.create_table(
            tname,
            sa.Column("ts", sa.DateTime(timezone=True), primary_key=True, nullable=False),
            sa.Column("symbol", sa.Text(), primary_key=True, nullable=False),
            sa.Column("open", sa.Numeric(20, 5), nullable=False),
            sa.Column("high", sa.Numeric(20, 5), nullable=False),
            sa.Column("low", sa.Numeric(20, 5), nullable=False),
            sa.Column("close", sa.Numeric(20, 5), nullable=False),
            sa.Column("volume", sa.Numeric(20, 2), nullable=False),
            sa.Column("source", sa.Text(), nullable=False),
            sa.Index(f"ix_{tname}_ts_brin", "ts", postgresql_using="brin"),
            sa.Index(f"ix_{tname}_symbol_ts", "symbol", "ts"),
            postgresql_partition_by="RANGE (ts)",
        )

    for tname in ("bars_1h", "bars_4h", "bars_1d"):
        op.create_table(
            tname,
            sa.Column("ts", sa.DateTime(timezone=True), primary_key=True, nullable=False),
            sa.Column("symbol", sa.Text(), nullable=False),
            sa.Column("open", sa.Numeric(20, 5), nullable=False),
            sa.Column("high", sa.Numeric(20, 5), nullable=False),
            sa.Column("low", sa.Numeric(20, 5), nullable=False),
            sa.Column("close", sa.Numeric(20, 5), nullable=False),
            sa.Column("volume", sa.Numeric(20, 2), nullable=False),
            sa.Column("source", sa.Text(), nullable=False),
            sa.Index(f"ix_{tname}_ts_brin", "ts", postgresql_using="brin"),
            sa.Index(f"ix_{tname}_symbol_ts", "symbol", "ts"),
        )

    # ── Operational tables ───────────────────────────────────────────────
    op.create_table(
        "llm_usage",
        sa.Column("id", UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("agent_role", sa.Text(), nullable=False),
        sa.Column("model_version_id", UUID(), sa.ForeignKey("model_versions.id"), nullable=False),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("model_id", sa.Text(), nullable=False),
        sa.Column("prompt_tokens", sa.BigInteger(), nullable=False),
        sa.Column("completion_tokens", sa.BigInteger(), nullable=False),
        sa.Column("cost_usd", sa.Numeric(12, 6), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("success", sa.Boolean(), nullable=False),
        sa.Column("error_message", sa.Text()),
        sa.Column("lineage_id", UUID(), sa.ForeignKey("lineage_records.lineage_id")),
        sa.Index("ix_llm_usage_ts", "ts"),
        sa.Index("ix_llm_usage_agent", "agent_role", "ts"),
        sa.Index("ix_llm_usage_lineage", "lineage_id"),
    )

    op.create_table(
        "workflow_journal",
        sa.Column("id", UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("workflow_id", sa.Text(), nullable=False),
        sa.Column("step_name", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("duration_ms", sa.Integer()),
        sa.Column("input_snapshot", JSONB()),
        sa.Column("output_snapshot", JSONB()),
        sa.Column("error_message", sa.Text()),
        sa.Column("lineage_id", UUID(), sa.ForeignKey("lineage_records.lineage_id")),
        sa.Index("ix_wf_journal_ts", "ts"),
        sa.Index("ix_wf_journal_workflow", "workflow_id", "ts"),
        sa.Index("ix_wf_journal_status", "status"),
        sa.Index("ix_wf_journal_lineage", "lineage_id"),
    )

    op.create_table(
        "security_events",
        sa.Column("id", UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("severity", sa.Text(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("actor", sa.Text()),
        sa.Column("detail", JSONB(), nullable=False),
        sa.Column("ip_address", sa.String(45)),
        sa.Index("ix_security_events_ts", "ts"),
        sa.Index("ix_security_events_type", "event_type", "ts"),
        sa.Index("ix_security_events_severity", "severity", "ts"),
    )


def downgrade() -> None:
    op.drop_table("security_events")
    op.drop_table("workflow_journal")
    op.drop_table("llm_usage")
    op.drop_table("bars_1d")
    op.drop_table("bars_4h")
    op.drop_table("bars_1h")
    op.drop_table("bars_5m")
    op.drop_table("bars_1m")
    op.drop_table("ticks")
    op.drop_table("order_state_transitions")
    op.drop_table("processed_commands")
    op.drop_table("positions")
    op.drop_table("fills")
    op.drop_table("lineage_records")
    op.drop_table("policy_versions")
    op.drop_table("strategy_versions")
    op.drop_table("prompt_versions")
    op.drop_table("model_versions")
    op.execute("DROP TYPE registry_status")