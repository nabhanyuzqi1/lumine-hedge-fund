# Copyright (c) 2026 Lumine. All rights reserved.
"""Custom exception hierarchy for Lumine.

All exceptions inherit from LumineError. Domain-specific exceptions
inherit from the appropriate sub-base. This allows middleware to catch
at the right granularity.
"""

from __future__ import annotations


class LumineError(Exception):
    """Base exception for all Lumine errors."""


# ── Data layer ────────────────────────────────────────────────────────────────


class DataError(LumineError):
    """Base for database and persistence errors."""


class DatabaseConnectionError(DataError):
    """Database or Redis connection failure."""


class RecordNotFoundError(DataError):
    """Expected record not found in database."""


class DuplicateRecordError(DataError):
    """Unique constraint violation."""


# ── Validation ────────────────────────────────────────────────────────────────


class ValidationError(LumineError):
    """Input or schema validation failure."""


class SchemaValidationError(ValidationError):
    """JSON Schema validation failure (agent outputs)."""


class ProposalValidationError(ValidationError):
    """Investment proposal does not conform to expected schema."""


# ── Trading ───────────────────────────────────────────────────────────────────


class TradingError(LumineError):
    """Base for trading and execution errors."""


class RiskRejectionError(TradingError):
    """Risk engine rejected the proposal — no order dispatched."""


class ExecutionError(TradingError):
    """Order dispatch or fill failure."""


class IdempotencyError(TradingError):
    """Duplicate command detected (D3-7, D8-9)."""


class KillSwitchError(TradingError):
    """Kill-switch active — all trading halted."""


class SizingError(TradingError):
    """Position sizing calculation failure."""


# ── LLM / Gateway ─────────────────────────────────────────────────────────────


class LLMError(LumineError):
    """Base for LLM and gateway errors."""


class LLMTimeoutError(LLMError):
    """LLM request timed out."""


class LLMBudgetExceededError(LLMError):
    """Daily LLM budget exceeded — circuit breaker triggered."""


class ModelUnavailableError(LLMError):
    """Requested LLM model not available in gateway."""


class LLMOutputValidationError(LLMError):
    """LLM output failed schema validation."""


class LLMUsageRecordError(LLMError):
    """Failed to persist an llm_usage row (D6-7 cost accounting)."""


# ── AutoGen pipeline ──────────────────────────────────────────────────────────


class PipelineError(LumineError):
    """Base for AutoGen pipeline errors."""


class WorkflowHaltedError(PipelineError):
    """Workflow halted — safe-state triggered."""


class AgentTimeoutError(PipelineError):
    """Agent did not respond within timeout."""


class DebateError(PipelineError):
    """Debate resolution failure."""


# ── API ───────────────────────────────────────────────────────────────────────


class APIError(LumineError):
    """Base for API and HTTP errors."""


class AuthError(APIError):
    """HMAC authentication failure."""


class RateLimitError(APIError):
    """Rate limit exceeded."""


class ScopeError(APIError):
    """Insufficient scope for requested operation."""


# ── Decision cycle / orchestration ───────────────────────────────────────────


class DecisionCycleError(LumineError):
    """Base for decision-cycle orchestration failures."""


class DeadlineExceededError(DecisionCycleError):
    """The decision cycle exceeded its soft deadline (D7-4, D3-12)."""


class SafeStateError(DecisionCycleError):
    """A stage failed into safe state; the pipeline stops, never guesses."""


# ── Configuration ─────────────────────────────────────────────────────────────


class ConfigError(LumineError):
    """Configuration error — missing or invalid env vars."""
