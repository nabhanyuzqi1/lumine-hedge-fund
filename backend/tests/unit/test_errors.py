# Copyright (c) 2026 Lumine. All rights reserved.
"""Unit tests for shared/errors.py — exception hierarchy."""

from __future__ import annotations

import pytest

from lumine.shared.errors import (
    AgentTimeoutError,
    APIError,
    AuthError,
    ConfigError,
    DatabaseConnectionError,
    DataError,
    DebateError,
    DuplicateRecordError,
    ExecutionError,
    IdempotencyError,
    KillSwitchError,
    LLMBudgetExceededError,
    LLMError,
    LLMOutputValidationError,
    LLMTimeoutError,
    LLMUsageRecordError,
    LumineError,
    ModelUnavailableError,
    PipelineError,
    ProposalValidationError,
    RateLimitError,
    RecordNotFoundError,
    RiskRejectionError,
    SchemaValidationError,
    ScopeError,
    SizingError,
    TradingError,
    ValidationError,
    WorkflowHaltedError,
)


class TestLumineError:
    """Base exception — all Lumine errors inherit from this."""

    def test_is_exception(self) -> None:
        assert issubclass(LumineError, Exception)

    def test_can_be_raised_and_caught(self) -> None:
        with pytest.raises(LumineError):
            raise LumineError("test error")

    def test_message_is_preserved(self) -> None:
        msg = "something went wrong"
        with pytest.raises(LumineError, match=msg):
            raise LumineError(msg)


class TestExceptionInheritance:
    """Verify the inheritance chain for each exception branch."""

    # ── Data layer ────────────────────────────────────────────────────────

    def test_data_error_inherits_lumine_error(self) -> None:
        assert issubclass(DataError, LumineError)

    def test_database_connection_error_inherits_data_error(self) -> None:
        assert issubclass(DatabaseConnectionError, DataError)

    def test_record_not_found_inherits_data_error(self) -> None:
        assert issubclass(RecordNotFoundError, DataError)

    def test_duplicate_record_inherits_data_error(self) -> None:
        assert issubclass(DuplicateRecordError, DataError)

    # ── Validation ────────────────────────────────────────────────────────

    def test_validation_error_inherits_lumine_error(self) -> None:
        assert issubclass(ValidationError, LumineError)

    def test_schema_validation_inherits_validation_error(self) -> None:
        assert issubclass(SchemaValidationError, ValidationError)

    def test_proposal_validation_inherits_validation_error(self) -> None:
        assert issubclass(ProposalValidationError, ValidationError)

    # ── Trading ───────────────────────────────────────────────────────────

    def test_trading_error_inherits_lumine_error(self) -> None:
        assert issubclass(TradingError, LumineError)

    def test_risk_rejection_inherits_trading_error(self) -> None:
        assert issubclass(RiskRejectionError, TradingError)

    def test_execution_error_inherits_trading_error(self) -> None:
        assert issubclass(ExecutionError, TradingError)

    def test_idempotency_error_inherits_trading_error(self) -> None:
        assert issubclass(IdempotencyError, TradingError)

    def test_kill_switch_error_inherits_trading_error(self) -> None:
        assert issubclass(KillSwitchError, TradingError)

    def test_sizing_error_inherits_trading_error(self) -> None:
        assert issubclass(SizingError, TradingError)

    # ── LLM ───────────────────────────────────────────────────────────────

    def test_llm_error_inherits_lumine_error(self) -> None:
        assert issubclass(LLMError, LumineError)

    def test_llm_timeout_inherits_llm_error(self) -> None:
        assert issubclass(LLMTimeoutError, LLMError)

    def test_llm_budget_exceeded_inherits_llm_error(self) -> None:
        assert issubclass(LLMBudgetExceededError, LLMError)

    def test_model_unavailable_inherits_llm_error(self) -> None:
        assert issubclass(ModelUnavailableError, LLMError)

    def test_llm_output_validation_inherits_llm_error(self) -> None:
        assert issubclass(LLMOutputValidationError, LLMError)

    def test_llm_usage_record_inherits_llm_error(self) -> None:
        # errors.py:100-102 — usage-write failures must be catchable as
        # LLMError so gateway callers handle them uniformly with other
        # gateway errors (cost accounting must never crash the pipeline).
        assert issubclass(LLMUsageRecordError, LLMError)

    # ── AutoGen pipeline ──────────────────────────────────────────────────

    def test_pipeline_error_inherits_lumine_error(self) -> None:
        assert issubclass(PipelineError, LumineError)

    def test_workflow_halted_inherits_pipeline_error(self) -> None:
        assert issubclass(WorkflowHaltedError, PipelineError)

    def test_agent_timeout_inherits_pipeline_error(self) -> None:
        assert issubclass(AgentTimeoutError, PipelineError)

    def test_debate_error_inherits_pipeline_error(self) -> None:
        assert issubclass(DebateError, PipelineError)

    # ── API ───────────────────────────────────────────────────────────────

    def test_api_error_inherits_lumine_error(self) -> None:
        assert issubclass(APIError, LumineError)

    def test_auth_error_inherits_api_error(self) -> None:
        assert issubclass(AuthError, APIError)

    def test_rate_limit_error_inherits_api_error(self) -> None:
        assert issubclass(RateLimitError, APIError)

    def test_scope_error_inherits_api_error(self) -> None:
        assert issubclass(ScopeError, APIError)

    # ── Configuration ─────────────────────────────────────────────────────

    def test_config_error_inherits_lumine_error(self) -> None:
        assert issubclass(ConfigError, LumineError)


class TestExceptionCatchingAtGranularity:
    """Verify exceptions can be caught at the right granularity."""

    def test_data_error_catches_database_connection_error(self) -> None:
        with pytest.raises(DataError):
            raise DatabaseConnectionError("connection failed")

    def test_trading_error_catches_execution_error(self) -> None:
        with pytest.raises(TradingError):
            raise ExecutionError("fill failed")

    def test_llm_error_catches_timeout(self) -> None:
        with pytest.raises(LLMError):
            raise LLMTimeoutError("timeout")

    def test_lumine_error_catches_all(self) -> None:
        with pytest.raises(LumineError):
            raise KillSwitchError("system halted")
