# Copyright (c) 2026 Lumine. All rights reserved.
"""Align llm_usage schema to Phase 6 D6-7 (cost-control.md).

The existing llm_usage table (0001) was operational: latency_ms, success,
error_message, provider, model_id, agent_role, prompt/completion_tokens.
Phase 6 D6-7 fixes the canonical cost-accounting schema:
  role, tier, model_version_id, prompt_version_id, tokens_in, tokens_out,
  cost_usd, fallback_hops, degraded, lineage_id, lane.

Reconciliation (user-approved 2026-08-03: align to spec D6-7):
- rename agent_role -> role, prompt_tokens -> tokens_in,
  completion_tokens -> tokens_out
- add tier, prompt_version_id (nullable FK), fallback_hops, degraded, lane
- drop provider, model_id (redundant: resolvable via model_version_id FK),
  latency_ms, success, error_message (operational concerns belong in
  reasoning_traces / workflow_journal, not the cost-accounting table)
- replace ix_llm_usage_agent(role, ts) and add (tier, ts), (lane, ts)

Revision ID: 0005
Revises: 0004
Create Date: 2026-08-03
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ── Drop operational columns not in D6-7 ───────────────────────────
    op.drop_index("ix_llm_usage_agent", table_name="llm_usage")
    op.drop_column("llm_usage", "error_message")
    op.drop_column("llm_usage", "success")
    op.drop_column("llm_usage", "latency_ms")
    op.drop_column("llm_usage", "model_id")
    op.drop_column("llm_usage", "provider")

    # ── Rename to spec names ───────────────────────────────────────────
    op.alter_column(
        "llm_usage",
        "agent_role",
        new_column_name="role",
        existing_type=sa.Text(),
        existing_nullable=False,
    )
    op.alter_column(
        "llm_usage",
        "prompt_tokens",
        new_column_name="tokens_in",
        existing_type=sa.BigInteger(),
        existing_nullable=False,
    )
    op.alter_column(
        "llm_usage",
        "completion_tokens",
        new_column_name="tokens_out",
        existing_type=sa.BigInteger(),
        existing_nullable=False,
    )

    # ── Add D6-7 cost-routing columns ──────────────────────────────────
    op.add_column("llm_usage", sa.Column("tier", sa.Text(), nullable=False, server_default="cost-efficient"))
    op.add_column(
        "llm_usage",
        sa.Column("prompt_version_id", sa.UUID(), sa.ForeignKey("prompt_versions.id"), nullable=True),
    )
    op.add_column("llm_usage", sa.Column("fallback_hops", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("llm_usage", sa.Column("degraded", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.add_column("llm_usage", sa.Column("lane", sa.Text(), nullable=True))

    # ── Indexes per D6-7: (ts) already exists; add (role,ts), (tier,ts), (lane,ts)
    op.create_index("ix_llm_usage_role", "llm_usage", ["role", "ts"])
    op.create_index("ix_llm_usage_tier", "llm_usage", ["tier", "ts"])
    op.create_index("ix_llm_usage_lane", "llm_usage", ["lane", "ts"])


def downgrade() -> None:
    op.drop_index("ix_llm_usage_lane", table_name="llm_usage")
    op.drop_index("ix_llm_usage_tier", table_name="llm_usage")
    op.drop_index("ix_llm_usage_role", table_name="llm_usage")
    op.drop_column("llm_usage", "lane")
    op.drop_column("llm_usage", "degraded")
    op.drop_column("llm_usage", "fallback_hops")
    op.drop_column("llm_usage", "prompt_version_id")
    op.drop_column("llm_usage", "tier")
    op.alter_column(
        "llm_usage",
        "tokens_out",
        new_column_name="completion_tokens",
        existing_type=sa.BigInteger(),
        existing_nullable=False,
    )
    op.alter_column(
        "llm_usage",
        "tokens_in",
        new_column_name="prompt_tokens",
        existing_type=sa.BigInteger(),
        existing_nullable=False,
    )
    op.alter_column(
        "llm_usage",
        "role",
        new_column_name="agent_role",
        existing_type=sa.Text(),
        existing_nullable=False,
    )
    op.add_column("llm_usage", sa.Column("provider", sa.Text(), nullable=False, server_default=""))
    op.add_column("llm_usage", sa.Column("model_id", sa.Text(), nullable=False, server_default=""))
    op.add_column("llm_usage", sa.Column("latency_ms", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("llm_usage", sa.Column("success", sa.Boolean(), nullable=False, server_default=sa.text("true")))
    op.add_column("llm_usage", sa.Column("error_message", sa.Text(), nullable=True))
    op.create_index("ix_llm_usage_agent", "llm_usage", ["agent_role", "ts"])
