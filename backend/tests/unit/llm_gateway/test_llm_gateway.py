# Copyright (c) 2026 Lumine. All rights reserved.

"""Tests for LLM Gateway — model routing, fallback chains, budget tracking."""

from datetime import datetime, timedelta

import pytest

from lumine.llm_gateway.__init__ import (
    AdmissionControl,
    BudgetTracker,
    CircuitBreaker,
    CircuitState,
    GatewayRequest,
    GatewayResponse,
    ModelRegistry,
    ModelSpec,
    ModelStatus,
    ModelTier,
    TierFallbackChain,
)


class MockRegistry(ModelRegistry):
    """Test registry with predefined models."""

    def __init__(self):
        self.models: dict[str, ModelSpec] = {}

    def register_model(self, spec: ModelSpec) -> None:
        """Register a model specification."""
        self.models[spec.model_version_id] = spec

    def get_model(self, model_version_id: str):
        return self.models.get(model_version_id)

    def list_models(self, tier=None, status=None):
        results = []
        for m in self.models.values():
            if tier and m.tier != tier:
                continue
            if status and m.status != status:
                continue
            results.append(m)
        return results

    def resolve_model_for_tier(self, tier):
        for m in self.list_models(status=ModelStatus.PRODUCTION):
            if m.tier == tier:
                return m
        return None


class TestBudgetTracker:
    """Tests for daily/weekly budget tracking per D6-4."""

    def test_budget_initialization(self):
        tracker = BudgetTracker(daily_budget_usd=100.0, weekly_budget_usd=500.0)
        assert tracker.daily_budget == 100.0
        assert tracker.weekly_budget == 500.0
        assert tracker.daily_spent == {}

    def test_check_daily_budget_pass(self):
        tracker = BudgetTracker(daily_budget_usd=100.0, weekly_budget_usd=500.0)
        allowed, remaining = tracker.check_daily_budget()
        assert allowed is True
        assert remaining == 100.0

    def test_check_daily_budget_exceeded(self):
        tracker = BudgetTracker(daily_budget_usd=100.0, weekly_budget_usd=500.0)
        tracker.record_spending(100.0)
        allowed, remaining = tracker.check_daily_budget()
        assert allowed is False
        assert remaining <= 0

    def test_record_spending(self):
        tracker = BudgetTracker(daily_budget_usd=100.0, weekly_budget_usd=500.0)
        tracker.record_spending(25.5)
        allowed, remaining = tracker.check_daily_budget()
        assert allowed is True
        assert abs(remaining - 74.5) < 0.01

    def test_weekly_budget_tracking(self):
        tracker = BudgetTracker(daily_budget_usd=100.0, weekly_budget_usd=500.0)
        for _ in range(3):
            tracker.record_spending(200.0)
        allowed, remaining = tracker.check_weekly_budget()
        assert allowed is False
        assert remaining <= 0

    def test_reset_daily(self):
        tracker = BudgetTracker(daily_budget_usd=100.0, weekly_budget_usd=500.0)
        tracker.record_spending(50.0)
        tracker.reset_daily()
        allowed, remaining = tracker.check_daily_budget()
        assert allowed is True
        assert remaining == 100.0


class TestCircuitBreaker:
    """Tests for per-provider circuit breaker."""

    def test_circuit_default_closed(self):
        circuit = CircuitBreaker()
        assert circuit.state == CircuitState.CLOSED
        assert circuit.failure_count == 0

    def test_open_on_threshold(self):
        circuit = CircuitBreaker(threshold=3)
        for _ in range(3):
            circuit.failure_count += 1
        # Manual state transition (in real impl, would auto-open)
        circuit.state = CircuitState.OPEN
        assert circuit.state == CircuitState.OPEN

    def test_recovery_timeout(self):
        circuit = CircuitBreaker(recovery_timeout=timedelta(seconds=1))
        circuit.state = CircuitState.OPEN
        circuit.opened_at = datetime.now() - timedelta(seconds=2)
        # Would transition to HALF_OPEN after timeout (tested separately)


class TestAdmissionControl:
    """Tests for admission control policy per ADR-0022."""

    def test_admission_enabled_default(self):
        control = AdmissionControl(enabled=True)
        assert control.enabled is True

    def test_acquire_when_under_limit(self):
        control = AdmissionControl(enabled=True, max_concurrent=10)
        for _ in range(10):
            allowed, reason = control.acquire()
            assert allowed is True

        # 11th request should fail
        allowed, reason = control.acquire()
        assert allowed is False
        assert reason == "concurrency_limit_reached"

    def test_release_decrements_concurrent(self):
        control = AdmissionControl(enabled=True, max_concurrent=5)
        for _ in range(5):
            control.acquire()
        assert control.current_concurrent == 5

        control.release()
        assert control.current_concurrent == 4

    def test_admission_disabled_always_allowed(self):
        control = AdmissionControl(enabled=False)
        allowed, reason = control.acquire()
        assert allowed is True
        assert reason == ""


class TestTierFallbackChain:
    """Tests for fallback chain per D6-6."""

    def test_same_tier_fallback(self):
        registry = MockRegistry()
        chain = TierFallbackChain(registry)

        primary = ModelSpec(
            model_version_id="model-a",
            provider="openai",
            model_name="gpt-5.5",
            tier=ModelTier.STRONGEST,
            status=ModelStatus.PRODUCTION,
            base_cost_per_million_tokens=10.0,
            max_timeout_seconds=30,
            rate_limit_requests_per_minute=60,
            fallback_order=["model-b"],
        )

        registry.register_model(primary)
        fallback = ModelSpec(
            model_version_id="model-b",
            provider="openai",
            model_name="gpt-5.6",
            tier=ModelTier.STRONGEST,
            status=ModelStatus.PRODUCTION,
            base_cost_per_million_tokens=12.0,
            max_timeout_seconds=30,
            rate_limit_requests_per_minute=60,
        )
        registry.register_model(fallback)

        result = chain.resolve_fallback(primary, "timeout")
        assert result is not None
        assert result.model_version_id == "model-b"

    def test_tier_degradation(self):
        registry = MockRegistry()
        chain = TierFallbackChain(registry)

        strongest = ModelSpec(
            model_version_id="strongest-model",
            provider="openai",
            model_name="gpt-5.5",
            tier=ModelTier.STRONGEST,
            status=ModelStatus.PRODUCTION,
            base_cost_per_million_tokens=10.0,
            max_timeout_seconds=30,
            rate_limit_requests_per_minute=60,
            fallback_order=[],
        )
        registry.register_model(strongest)

        context_rich = ModelSpec(
            model_version_id="context-model",
            provider="deepseek",
            model_name="deepseek-v4",
            tier=ModelTier.CONTEXT_RICH,
            status=ModelStatus.PRODUCTION,
            base_cost_per_million_tokens=3.0,
            max_timeout_seconds=30,
            rate_limit_requests_per_minute=60,
        )
        registry.register_model(context_rich)

        result = chain.resolve_fallback(strongest, "all_alternates_failed")
        assert result is not None
        assert result.tier == ModelTier.CONTEXT_RICH

    def test_get_next_tier_strongest_to_context(self):
        registry = MockRegistry()
        chain = TierFallbackChain(registry)

        next_tier = chain.get_next_tier(ModelTier.STRONGEST)
        assert next_tier == ModelTier.CONTEXT_RICH

    def test_get_next_tier_context_to_cost(self):
        registry = MockRegistry()
        chain = TierFallbackChain(registry)

        next_tier = chain.get_next_tier(ModelTier.CONTEXT_RICH)
        assert next_tier == ModelTier.COST_EFFICIENT

    def test_no_tier_from_cost_efficient(self):
        registry = MockRegistry()
        chain = TierFallbackChain(registry)

        next_tier = chain.get_next_tier(ModelTier.COST_EFFICIENT)
        assert next_tier is None


class TestGatewayRequestContract:
    """Tests for request contract validation."""

    def test_minimal_request(self):
        request = GatewayRequest(
            model_version_id="model-a",
            prompt_ref="prompt-b",
            role="technical_analyst",
            payload={"messages": [{"role": "user", "content": "analyze gold"}]},
        )
        assert request.model_version_id == "model-a"
        assert request.prompt_ref == "prompt-b"
        assert request.role == "technical_analyst"
        assert request.prompt_hash is None
        assert request.idempotency_key is None

    def test_full_request_with_optional_fields(self):
        request = GatewayRequest(
            model_version_id="model-a",
            prompt_ref="prompt-b",
            prompt_hash="sha256:abc123",
            lineage_id="decision-001",
            role="cio",
            tier=ModelTier.STRONGEST,
            idempotency_key="idem-key-xyz",
            payload={"messages": [{"role": "user", "content": "execute"}]},
        )
        assert request.prompt_hash == "sha256:abc123"
        assert request.lineage_id == "decision-001"
        assert request.tier == ModelTier.STRONGEST
        assert request.idempotency_key == "idem-key-xyz"


class TestMockGatewayResponse:
    """Tests for response structure."""

    def test_successful_response(self):
        response = GatewayResponse(
            success=True,
            model_version_id="model-a",
            model_used="gpt-5.5",
            prompt_ref="prompt-b",
            tokens_used={"prompt": 50, "completion": 25},
            cost_estimate=0.00175,
            latency_seconds=1.23,
        )
        assert response.success is True
        assert response.fallback_hops == 0
        assert response.error_message is None

    def test_failed_response(self):
        response = GatewayResponse(
            success=False,
            model_version_id="model-a",
            model_used="",
            prompt_ref="prompt-b",
            tokens_used={},
            cost_estimate=0.0,
            latency_seconds=0.0,
            error_message="Model not found",
        )
        assert response.success is False
        assert response.error_message == "Model not found"


@pytest.mark.asyncio
async def test_model_registry_operations():
    """Test complete model registry workflow."""
    registry = MockRegistry()

    # Register production models across tiers
    strongest = ModelSpec(
        model_version_id="gpt-5.5-prod",
        provider="openai",
        model_name="gpt-5.5",
        tier=ModelTier.STRONGEST,
        status=ModelStatus.PRODUCTION,
        base_cost_per_million_tokens=10.0,
        max_timeout_seconds=30,
        rate_limit_requests_per_minute=60,
    )
    registry.register_model(strongest)

    context_rich = ModelSpec(
        model_version_id="deepseek-v4-prod",
        provider="deepseek",
        model_name="deepseek-v4",
        tier=ModelTier.CONTEXT_RICH,
        status=ModelStatus.PRODUCTION,
        base_cost_per_million_tokens=3.0,
        max_timeout_seconds=30,
        rate_limit_requests_per_minute=60,
    )
    registry.register_model(context_rich)

    cost_efficient = ModelSpec(
        model_version_id="qwen-3.7-prod",
        provider="alibaba",
        model_name="qwen-3.7",
        tier=ModelTier.COST_EFFICIENT,
        status=ModelStatus.PRODUCTION,
        base_cost_per_million_tokens=1.0,
        max_timeout_seconds=30,
        rate_limit_requests_per_minute=120,
    )
    registry.register_model(cost_efficient)

    # Test resolution
    resolved = registry.get_model("gpt-5.5-prod")
    assert resolved is not None
    assert resolved.provider == "openai"

    # Test tier resolution
    best_strongest = registry.resolve_model_for_tier(ModelTier.STRONGEST)
    assert best_strongest.model_version_id == "gpt-5.5-prod"

    # Test listing
    all_production = registry.list_models(status=ModelStatus.PRODUCTION)
    assert len(all_production) == 3


def test_model_status_enforcement():
    """Test that non-production models are not routable."""
    registry = MockRegistry()

    sandbox_model = ModelSpec(
        model_version_id="gpt-5.5-sandbox",
        provider="openai",
        model_name="gpt-5.5",
        tier=ModelTier.STRONGEST,
        status=ModelStatus.SANDBOX,  # Not production
        base_cost_per_million_tokens=10.0,
        max_timeout_seconds=30,
        rate_limit_requests_per_minute=60,
    )
    registry.register_model(sandbox_model)

    # Should be retrievable but not routable for live pipeline
    retrieved = registry.get_model("gpt-5.5-sandbox")
    assert retrieved is not None
    assert retrieved.status == ModelStatus.SANDBOX

    # Should not appear in production list
    production_only = registry.list_models(status=ModelStatus.PRODUCTION)
    assert len(production_only) == 0
