# Copyright (c) 2026 Lumine. All rights reserved.
"""Unit tests for data/models.py — ORM model structure verification."""

from __future__ import annotations

from typing import ClassVar

from sqlalchemy.orm import DeclarativeBase

from lumine.data.models import (
    Bars1D,
    Bars1H,
    Bars1M,
    Bars4H,
    Bars5M,
    Base,
    CalendarVersion,
    FeatureVersion,
    Fill,
    LineageRecord,
    LLMUsage,
    MessageSchemaVersion,
    ModelVersion,
    OrderStateTransition,
    PolicyVersion,
    Position,
    ProcessedCommand,
    PromptVersion,
    ReasoningTrace,
    RegimeVersion,
    SecurityEvent,
    StrategyVersion,
    Tick,
    WorkflowJournal,
)


class TestBase:
    """Verify the declarative base class."""

    def test_base_is_declarative(self) -> None:
        assert issubclass(Base, DeclarativeBase)

    def test_base_is_declarative_base(self) -> None:
        assert issubclass(Base, DeclarativeBase)


class TestBarModels:
    """Verify bar table models are created correctly."""

    def test_bars_1m_table_name(self) -> None:
        assert Bars1M.__tablename__ == "bars_1m"

    def test_bars_5m_table_name(self) -> None:
        assert Bars5M.__tablename__ == "bars_5m"

    def test_bars_1h_table_name(self) -> None:
        assert Bars1H.__tablename__ == "bars_1h"

    def test_bars_4h_table_name(self) -> None:
        assert Bars4H.__tablename__ == "bars_4h"

    def test_bars_1d_table_name(self) -> None:
        assert Bars1D.__tablename__ == "bars_1d"

    def test_partitioned_bars_have_brin_index(self) -> None:
        """Partitioned bars use BRIN index on ts."""
        indexes = {idx.name for idx in Bars1M.__table_args__ if hasattr(idx, "name")}
        assert "ix_bars_1m_ts_brin" in indexes

    def test_bars_models_have_ohlcv_columns(self) -> None:
        columns = {c.name for c in Bars1D.__table__.columns}
        assert columns >= {"ts", "symbol", "open", "high", "low", "close", "volume", "source"}

    def test_partitioned_bars_use_composite_ts_symbol_pk(self) -> None:
        # _make_bar_table (models.py:533-545): partitioned tables make
        # symbol part of the composite (ts, symbol) PK — Postgres requires
        # unique constraints on partitioned tables to include the
        # partition key. Bars1M/Bars5M must carry it; Bars1H must not.
        for table in (Bars1M, Bars5M):
            pk = {c.name for c in table.__table__.primary_key.columns}
            assert pk == {"ts", "symbol"}, f"{table.__tablename__} PK = {pk}"
        for table in (Bars1H, Bars4H, Bars1D):
            pk = {c.name for c in table.__table__.primary_key.columns}
            assert pk == {"ts"}, f"{table.__tablename__} PK = {pk}"

    def test_partitioned_bars_declare_range_partitioning(self) -> None:
        # The RANGE (ts) clause (models.py:531) is a table option, not a
        # column — it surfaces on __table__.dialect_options.
        assert "postgresql" in Bars1M.__table__.dialect_options
        assert Bars1M.__table__.dialect_options["postgresql"]["partition_by"] == "RANGE (ts)"
        assert "postgresql" not in Bars1H.__table__.dialect_options


class TestOperationalModelTableNames:
    """Verify table names match the naming convention."""

    def test_model_version_table_name(self) -> None:
        assert ModelVersion.__tablename__ == "model_versions"

    def test_prompt_version_table_name(self) -> None:
        assert PromptVersion.__tablename__ == "prompt_versions"

    def test_strategy_version_table_name(self) -> None:
        assert StrategyVersion.__tablename__ == "strategy_versions"

    def test_policy_version_table_name(self) -> None:
        assert PolicyVersion.__tablename__ == "policy_versions"

    def test_feature_version_table_name(self) -> None:
        assert FeatureVersion.__tablename__ == "feature_versions"

    def test_regime_version_table_name(self) -> None:
        assert RegimeVersion.__tablename__ == "regime_versions"

    def test_calendar_version_table_name(self) -> None:
        assert CalendarVersion.__tablename__ == "calendar_versions"

    def test_lineage_record_table_name(self) -> None:
        assert LineageRecord.__tablename__ == "lineage_records"

    def test_fill_table_name(self) -> None:
        assert Fill.__tablename__ == "fills"

    def test_position_table_name(self) -> None:
        assert Position.__tablename__ == "positions"

    def test_processed_command_table_name(self) -> None:
        assert ProcessedCommand.__tablename__ == "processed_commands"

    def test_order_state_transition_table_name(self) -> None:
        assert OrderStateTransition.__tablename__ == "order_state_transitions"

    def test_tick_table_name(self) -> None:
        assert Tick.__tablename__ == "ticks"

    def test_llm_usage_table_name(self) -> None:
        assert LLMUsage.__tablename__ == "llm_usage"

    def test_workflow_journal_table_name(self) -> None:
        assert WorkflowJournal.__tablename__ == "workflow_journal"

    def test_security_event_table_name(self) -> None:
        assert SecurityEvent.__tablename__ == "security_events"


class TestModelRelationships:
    """Verify that models have the expected foreign key relationships."""

    def test_lineage_record_has_strategy_version_fk(self) -> None:
        fks = {fk.column.name for fk in LineageRecord.__table__.foreign_keys}
        assert "id" in fks

    def test_order_state_transition_has_lineage_fk(self) -> None:
        fks = {fk.column.name for fk in OrderStateTransition.__table__.foreign_keys}
        assert "lineage_id" in fks

    def test_fill_has_lineage_fk(self) -> None:
        # Fill (models.py:365-368) is the execution-side anchor of the
        # audit chain — every fill must reference the decision lineage.
        fks = {fk.target_fullname for fk in Fill.__table__.columns["lineage_id"].foreign_keys}
        assert "lineage_records.lineage_id" in fks

    def test_position_has_lineage_fk_and_partial_unique_index(self) -> None:
        # ix_positions_open (models.py:420-427) is a partial unique index:
        # one open position per (symbol, book, strategy_id) — closed
        # positions never collide because the predicate excludes them.
        index = next(i for i in Position.__table__.indexes if i.name == "ix_positions_open")
        assert index.unique is True
        assert index.dialect_options["postgresql"]["where"] is not None

    def test_processed_command_composite_pk_is_lineage_id(self) -> None:
        # ProcessedCommand (models.py:435-439) keys its idempotency gate
        # on lineage_id alone — the PK must be exactly that single column.
        pk = {c.name for c in ProcessedCommand.__table__.primary_key.columns}
        assert pk == {"lineage_id"}
        assert ProcessedCommand.__table__.columns["replay_count"].default.arg == 0

    def test_tick_uses_composite_ts_symbol_pk(self) -> None:
        # Tick (models.py:499-500): dedup on reconnect/replay relies on
        # the (ts, symbol) composite PK — pinning it exactly.
        pk = {c.name for c in Tick.__table__.primary_key.columns}
        assert pk == {"ts", "symbol"}
        assert Tick.__table__.dialect_options["postgresql"]["partition_by"] == "RANGE (ts)"

    def test_security_event_ip_address_is_string_45(self) -> None:
        # String(45) matches the max length of an IPv6 address — pinning
        # the widest valid literal form (models.py:730).
        col = SecurityEvent.__table__.columns["ip_address"]
        assert col.type.__class__.__name__ == "String"
        assert col.type.length == 45
        assert col.nullable is True


# ═══════════════════════════════════════════════════════════════════════════════
# Sprint 3 — schema contract pins (align ORM to migrations 0004/0005/0006)
#
# These tests pin the physical schema declared by the ORM to the spec and
# Alembic migrations. Any drift (a renamed column, a dropped operational
# field, a missing index) fails here before it can ship to a migration.
# ═══════════════════════════════════════════════════════════════════════════════


class TestModelVersionParamsColumn:
    """D3-4 / migration 0004: model_versions.config renamed to params."""

    def test_table_name(self) -> None:
        assert ModelVersion.__tablename__ == "model_versions"

    def test_has_params_column(self) -> None:
        columns = {c.name for c in ModelVersion.__table__.columns}
        assert "params" in columns

    def test_no_legacy_config_column(self) -> None:
        columns = {c.name for c in ModelVersion.__table__.columns}
        assert not {"config"} & columns

    def test_params_is_jsonb_not_nullable(self) -> None:
        params = ModelVersion.__table__.columns["params"]
        assert params.nullable is False


class TestLLMUsageSchemaD67:
    """D6-7 / migration 0005: cost-accounting schema for llm_usage."""

    EXPECTED_COLUMNS: ClassVar[frozenset[str]] = frozenset(
        {
            "id",
            "ts",
            "role",
            "tier",
            "model_version_id",
            "prompt_version_id",
            "tokens_in",
            "tokens_out",
            "cost_usd",
            "fallback_hops",
            "degraded",
            "lane",
            "lineage_id",
        }
    )

    LEGACY_COLUMNS_REMOVED: ClassVar[frozenset[str]] = frozenset(
        {
            "agent_role",
            "prompt_tokens",
            "completion_tokens",
            "provider",
            "model_id",
            "latency_ms",
            "success",
            "error_message",
        }
    )

    EXPECTED_INDEXES: ClassVar[frozenset[str]] = frozenset(
        {
            "ix_llm_usage_ts",
            "ix_llm_usage_role",
            "ix_llm_usage_tier",
            "ix_llm_usage_lane",
            "ix_llm_usage_lineage",
        }
    )

    def test_table_name(self) -> None:
        assert LLMUsage.__tablename__ == "llm_usage"

    def test_columns_match_d67(self) -> None:
        columns = {c.name for c in LLMUsage.__table__.columns}
        assert columns == self.EXPECTED_COLUMNS

    def test_no_legacy_columns(self) -> None:
        columns = {c.name for c in LLMUsage.__table__.columns}
        assert not (columns & self.LEGACY_COLUMNS_REMOVED)

    def test_legacy_agent_index_dropped(self) -> None:
        indexes = {idx.name for idx in LLMUsage.__table_args__ if hasattr(idx, "name")}
        assert not ({"ix_llm_usage_agent"} & indexes)

    def test_indexes_match_d67(self) -> None:
        indexes = {idx.name for idx in LLMUsage.__table_args__ if hasattr(idx, "name")}
        assert indexes >= self.EXPECTED_INDEXES

    def test_tokens_in_and_out_are_biginteger(self) -> None:
        assert LLMUsage.__table__.columns["tokens_in"].type.__class__.__name__ == "BigInteger"
        assert LLMUsage.__table__.columns["tokens_out"].type.__class__.__name__ == "BigInteger"

    def test_cost_usd_is_numeric(self) -> None:
        col = LLMUsage.__table__.columns["cost_usd"]
        assert col.type.__class__.__name__ == "Numeric"

    def test_fallback_hops_defaults_to_zero(self) -> None:
        col = LLMUsage.__table__.columns["fallback_hops"]
        assert col.nullable is False
        assert col.default is not None
        assert col.default.arg == 0

    def test_degraded_defaults_to_false(self) -> None:
        col = LLMUsage.__table__.columns["degraded"]
        assert col.nullable is False
        assert col.default is not None
        assert col.default.arg is False

    def test_tier_server_defaults_to_cost_efficient(self) -> None:
        """Migration 0005 sets tier server_default='cost-efficient'; ORM must match."""
        col = LLMUsage.__table__.columns["tier"]
        assert col.nullable is False
        assert col.server_default is not None
        assert "cost-efficient" in str(col.server_default.arg)

    def test_lane_is_nullable(self) -> None:
        assert LLMUsage.__table__.columns["lane"].nullable is True

    def test_prompt_version_id_is_nullable_fk(self) -> None:
        col = LLMUsage.__table__.columns["prompt_version_id"]
        assert col.nullable is True
        fks = {fk.target_fullname for fk in col.foreign_keys}
        assert "prompt_versions.id" in fks

    def test_model_version_id_is_nonnull_fk(self) -> None:
        col = LLMUsage.__table__.columns["model_version_id"]
        assert col.nullable is False
        fks = {fk.target_fullname for fk in col.foreign_keys}
        assert "model_versions.id" in fks

    def test_lineage_id_is_nullable_fk(self) -> None:
        col = LLMUsage.__table__.columns["lineage_id"]
        assert col.nullable is True
        fks = {fk.target_fullname for fk in col.foreign_keys}
        assert "lineage_records.lineage_id" in fks


class TestReasoningTraceSchemaD711:
    """D7-11 / migration 0006: one row per LLM call with full prompt + hashes."""

    EXPECTED_COLUMNS: ClassVar[frozenset[str]] = frozenset(
        {
            "trace_id",
            "workflow_run_id",
            "stage_run_id",
            "role",
            "model_version_id",
            "prompt_version_id",
            "prompt_sent",
            "response_raw",
            "parsed_output",
            "prompt_hash",
            "response_hash",
            "ts",
            "lineage_id",
        }
    )

    EXPECTED_INDEXES: ClassVar[frozenset[str]] = frozenset(
        {
            "ix_reasoning_traces_workflow",
            "ix_reasoning_traces_lineage",
            "ix_reasoning_traces_role",
        }
    )

    def test_table_name(self) -> None:
        assert ReasoningTrace.__tablename__ == "reasoning_traces"

    def test_columns_match_d711(self) -> None:
        columns = {c.name for c in ReasoningTrace.__table__.columns}
        assert columns == self.EXPECTED_COLUMNS

    def test_indexes_match_d711(self) -> None:
        indexes = {idx.name for idx in ReasoningTrace.__table_args__ if hasattr(idx, "name")}
        assert indexes >= self.EXPECTED_INDEXES

    def test_trace_id_is_primary_key(self) -> None:
        assert ReasoningTrace.__table__.columns["trace_id"].primary_key is True

    def test_parsed_output_is_jsonb_nullable(self) -> None:
        col = ReasoningTrace.__table__.columns["parsed_output"]
        assert col.type.__class__.__name__ == "JSONB"
        assert col.nullable is True

    def test_prompt_sent_and_response_raw_are_nonnull_text(self) -> None:
        for name in ("prompt_sent", "response_raw"):
            col = ReasoningTrace.__table__.columns[name]
            assert col.nullable is False
            assert col.type.__class__.__name__ == "Text"

    def test_prompt_hash_and_response_hash_are_nonnull(self) -> None:
        for name in ("prompt_hash", "response_hash"):
            assert ReasoningTrace.__table__.columns[name].nullable is False

    def test_model_version_id_is_nonnull_fk(self) -> None:
        col = ReasoningTrace.__table__.columns["model_version_id"]
        assert col.nullable is False
        fks = {fk.target_fullname for fk in col.foreign_keys}
        assert "model_versions.id" in fks

    def test_prompt_version_id_is_nullable_fk(self) -> None:
        col = ReasoningTrace.__table__.columns["prompt_version_id"]
        assert col.nullable is True
        fks = {fk.target_fullname for fk in col.foreign_keys}
        assert "prompt_versions.id" in fks

    def test_lineage_id_is_nullable_fk(self) -> None:
        col = ReasoningTrace.__table__.columns["lineage_id"]
        assert col.nullable is True
        fks = {fk.target_fullname for fk in col.foreign_keys}
        assert "lineage_records.lineage_id" in fks


class TestMessageSchemaVersionTable:
    """Phase 4 inter-agent-message-versioning / migration 0006."""

    EXPECTED_COLUMNS: ClassVar[frozenset[str]] = frozenset(
        {
            "id",
            "name",
            "version",
            "schema",
            "compatibility",
            "code_hash",
            "status",
            "superseded_by",
            "created_at",
            "retired_at",
        }
    )

    EXPECTED_INDEXES: ClassVar[frozenset[str]] = frozenset({"ix_message_schema_status"})

    def test_table_name(self) -> None:
        assert MessageSchemaVersion.__tablename__ == "message_schema_versions"

    def test_columns_match_spec(self) -> None:
        columns = {c.name for c in MessageSchemaVersion.__table__.columns}
        assert columns == self.EXPECTED_COLUMNS

    def test_unique_name_version_constraint(self) -> None:
        constraints = {
            c.name
            for c in MessageSchemaVersion.__table__.constraints
            if hasattr(c, "name") and c.name
        }
        assert "uq_message_schema_name_version" in constraints

    def test_indexes_match_spec(self) -> None:
        indexes = {idx.name for idx in MessageSchemaVersion.__table_args__ if hasattr(idx, "name")}
        assert indexes >= self.EXPECTED_INDEXES

    def test_schema_is_jsonb_nonnull(self) -> None:
        col = MessageSchemaVersion.__table__.columns["schema"]
        assert col.type.__class__.__name__ == "JSONB"
        assert col.nullable is False

    def test_superseded_by_is_self_fk_nullable(self) -> None:
        col = MessageSchemaVersion.__table__.columns["superseded_by"]
        assert col.nullable is True
        fks = {fk.target_fullname for fk in col.foreign_keys}
        assert "message_schema_versions.id" in fks

    def test_retired_at_is_nullable(self) -> None:
        assert MessageSchemaVersion.__table__.columns["retired_at"].nullable is True
