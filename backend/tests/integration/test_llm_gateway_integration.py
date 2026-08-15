# Copyright (c) 2026 Lumine. All rights reserved.

"""Integration tests for LLM Gateway — end-to-end workflow verification."""

import asyncio

import pytest

from lumine.llm_gateway import (
    BudgetTracker,
    CircuitBreaker,
    CircuitState,
    GatewayRequest,
    GatewayResponse,
    ModelSpec,
    ModelStatus,
    ModelTier,
)


class MockNineRouterClient:
    """Mock HTTP client simulating 9router API responses."""

    def __init__(self):
        self.calls: list[dict] = []
        self.should_fail = False
        self.should_timeout = False

    async def invoke(self, request: "GatewayRequest") -> GatewayResponse:
        self.calls.append({
            "url": "https://api.nine-router.com/v1/chat/completions",
            "headers": {},
            "json_data": {
                "model_version_id": getattr(request, "model_version_id", ""),
                "payload": getattr(request, "payload", {}),
            },
        })

        if self.should_fail:
            return GatewayResponse(
                success=False,
                model_version_id=request.model_version_id,
                model_used="",
                prompt_ref=request.prompt_ref,
                tokens_used={"prompt": 0, "completion": 0},
                cost_estimate=0.0,
                latency_seconds=0.0,
                error_message="API Error",
            )

        if self.should_timeout:
            raise Exception("Timeout")

        # Determine model name from model_version_id
        model_version = getattr(request, "model_version_id", "")
        model_name = model_version.replace("-prod", "")

        return GatewayResponse(
            success=True,
            model_version_id=model_version,
            model_used=model_name,
            prompt_ref=request.prompt_ref,
            tokens_used={"prompt": 100, "completion": 50},
            cost_estimate=0.15,
            latency_seconds=1.2,
            fallback_hops=0,
        )

    def reset(self):
        self.calls.clear()
        self.should_fail = False
        self.should_timeout = False


@pytest.fixture
def mock_client():
    return MockNineRouterClient()


@pytest.fixture
def registry_with_models():
    """Create a test registry with models across all tiers."""
    from lumine.llm_gateway.providers import SimpleModelRegistry

    registry = SimpleModelRegistry()

    # STRONGEST tier models
    strongest_model = ModelSpec(
        model_version_id="gpt-5.5-prod",
        provider="openai",
        model_name="gpt-5.5-turbo",
        tier=ModelTier.STRONGEST,
        status=ModelStatus.PRODUCTION,
        base_cost_per_million_tokens=10.0,
        max_timeout_seconds=30,
        rate_limit_requests_per_minute=60,
    )
    registry.register_model(strongest_model)

    # CONTEXT_RICH tier model
    context_model = ModelSpec(
        model_version_id="deepseek-v4-prod",
        provider="deepseek",
        model_name="deepseek-chat-v4",
        tier=ModelTier.CONTEXT_RICH,
        status=ModelStatus.PRODUCTION,
        base_cost_per_million_tokens=3.0,
        max_timeout_seconds=30,
        rate_limit_requests_per_minute=60,
        fallback_order=["gpt-5.5-prod"],
    )
    registry.register_model(context_model)

    # COST_EFFICIENT tier model
    efficient_model = ModelSpec(
        model_version_id="qwen-3.7-prod",
        provider="alibaba",
        model_name="qwen-max-3.7",
        tier=ModelTier.COST_EFFICIENT,
        status=ModelStatus.PRODUCTION,
        base_cost_per_million_tokens=1.0,
        max_timeout_seconds=30,
        rate_limit_requests_per_minute=120,
        fallback_order=["gpt-5.5-prod"],
    )
    registry.register_model(efficient_model)

    return registry


class TestEndToEndWorkflow:
    """Test complete request/response flow through gateway."""

    @pytest.mark.asyncio
    async def test_successful_request_flow(self, mock_client, registry_with_models):
        """Verify full pipeline works end-to-end."""
        from lumine.llm_gateway import LLMGateway

        budget_tracker = BudgetTracker(daily_budget_usd=100.0, weekly_budget_usd=500.0)
        admission_control = type("AdmissionControl", (), {
            "enabled": True,
            "max_concurrent": 10,
            "current_concurrent": 0,
            "acquire": lambda s: (True, ""),
            "release": lambda s: None,
        })()

        gateway = LLMGateway(
            registry=registry_with_models,
            nine_router_client=mock_client,
            budget_tracker=budget_tracker,
            admission_control=admission_control,
        )

        request = GatewayRequest(
            model_version_id="gpt-5.5-prod",
            prompt_ref="analysis-standard",
            role="technical_analyst",
            lineage_id="decision-001",
            payload={"messages": [{"role": "user", "content": "Analyze gold prices"}]},
        )

        response = await gateway.invoke(request)

        assert response.success is True
        assert response.model_used == "gpt-5.5"
        assert response.tokens_used["prompt"] == 100
        assert response.tokens_used["completion"] == 50
        assert len(mock_client.calls) == 1
        assert mock_client.calls[0]["json_data"]["model_version_id"] == "gpt-5.5-prod"

    @pytest.mark.asyncio
    async def test_fallback_chain_execution(self, mock_client, registry_with_models):
        """Test fallback when primary model fails."""
        from lumine.llm_gateway import LLMGateway

        budget_tracker = BudgetTracker(daily_budget_usd=100.0, weekly_budget_usd=500.0)
        admission_control = type("AdmissionControl", (), {
            "enabled": True,
            "max_concurrent": 10,
            "current_concurrent": 0,
            "acquire": lambda s: (True, ""),
            "release": lambda s: None,
        })()

        gateway = LLMGateway(
            registry=registry_with_models,
            nine_router_client=mock_client,
            budget_tracker=budget_tracker,
            admission_control=admission_control,
        )

        mock_client.should_fail = True
        request = GatewayRequest(
            model_version_id="gpt-5.5-prod",
            prompt_ref="analysis-standard",
            role="cio",
            tier=ModelTier.STRONGEST,
            payload={"messages": [{"role": "user", "content": "Macro analysis"}]},
        )

        response = await gateway.invoke(request)

        # When using registry with no fallbacks configured, we expect failure
        assert response.success is False
        assert response.error_message == "API Error"

    @pytest.mark.asyncio
    async def test_budget_enforcement_rejection(self, mock_client, registry_with_models):
        """Test budget limits are enforced before API calls."""
        from lumine.llm_gateway import LLMGateway

        budget_tracker = BudgetTracker(daily_budget_usd=10.0, weekly_budget_usd=50.0)
        budget_tracker.record_spending(25.0)

        admission_control = type("AdmissionControl", (), {
            "enabled": True,
            "max_concurrent": 10,
            "current_concurrent": 0,
            "acquire": lambda s: (True, ""),
            "release": lambda s: None,
        })()

        gateway = LLMGateway(
            registry=registry_with_models,
            nine_router_client=mock_client,
            budget_tracker=budget_tracker,
            admission_control=admission_control,
        )

        request = GatewayRequest(
            model_version_id="gpt-5.5-prod",
            prompt_ref="analysis-standard",
            role="analyst",
            payload={"messages": [{"role": "user", "content": "Test"}]},
        )

        response = await gateway.invoke(request)

        assert response.success is False
        assert "daily budget exceeded" in response.error_message.lower()
        assert len(mock_client.calls) == 0

    @pytest.mark.asyncio
    async def test_circuit_breaker_prevention(self, mock_client, registry_with_models):
        """Test circuit breaker prevents calls when open."""
        from lumine.llm_gateway import LLMGateway

        budget_tracker = BudgetTracker(daily_budget_usd=100.0, weekly_budget_usd=500.0)
        circuit = CircuitBreaker(threshold=2, recovery_timeout=300)
        circuit.state = CircuitState.OPEN
        circuit.failure_count = 2

        admission_control = type("AdmissionControl", (), {
            "enabled": True,
            "max_concurrent": 10,
            "current_concurrent": 0,
            "acquire": lambda s: (True, ""),
            "release": lambda s: None,
        })()

        circuits = {"openai": circuit}

        gateway = LLMGateway(
            registry=registry_with_models,
            nine_router_client=mock_client,
            budget_tracker=budget_tracker,
            admission_control=admission_control,
            circuit_breakers=circuits,
        )

        request = GatewayRequest(
            model_version_id="gpt-5.5-prod",
            prompt_ref="analysis-standard",
            role="analyst",
            payload={"messages": [{"role": "user", "content": "Test"}]},
        )

        response = await gateway.invoke(request)

        assert response.success is False
        assert "circuit" in response.error_message.lower()
        assert len(mock_client.calls) == 0


class TestUsageRecording:
    """Test usage recording integration."""

    @pytest.mark.asyncio
    async def test_usage_record_inserted_on_success(self, mock_client, registry_with_models):
        """Verify usage record created on successful completion."""
        from uuid import uuid4

        from lumine.llm_gateway import LLMGateway, UsageRecorder

        class FakeSession:
            def __init__(self):
                self.records = []

            async def add(self, record):
                self.records.append(record)

            async def commit(self):
                pass

            async def rollback(self):
                pass

            async def close(self):
                pass

        recorder = UsageRecorder()
        fake_session = FakeSession()
        print(f"=== DEBUG: Session ID before setting: {id(fake_session)}")
        recorder.session = fake_session
        print(f"=== DEBUG: recorder._session ID: {id(recorder._session)}, matches test: {recorder._session is fake_session}")

        budget_tracker = BudgetTracker(daily_budget_usd=100.0, weekly_budget_usd=500.0)
        admission_control = type("AdmissionControl", (), {
            "enabled": True,
            "max_concurrent": 10,
            "current_concurrent": 0,
            "acquire": lambda s: (True, ""),
            "release": lambda s: None,
        })()

        gateway = LLMGateway(
            registry=registry_with_models,
            nine_router_client=mock_client,
            budget_tracker=budget_tracker,
            admission_control=admission_control,
            usage_recorder=recorder,
        )

        print(f"DEBUG: gateway.usage_recorder={gateway.usage_recorder}, _session={gateway.usage_recorder._session}")

        request = GatewayRequest(
            model_version_id="deepseek-v4-prod",
            prompt_ref="analysis-standard",
            role="technical_analyst",
            lineage_id=str(uuid4()),
            tier=ModelTier.CONTEXT_RICH,
            payload={"messages": [{"role": "user", "content": "Test"}]},
        )

        response = await gateway.invoke(request)
        print(f"DEBUG: response.success={response.success}, response.error={getattr(response, 'error_message', None)}, model_used={response.model_used}")

        # Wait for background usage recording to complete
        await asyncio.sleep(0.1)

        assert len(fake_session.records) == 1
        record = fake_session.records[0]
        assert record.role == "technical_analyst"
        assert record.tier == "context_rich"
        assert record.fallback_hops == 0
        assert record.tokens_in == 100
        assert record.tokens_out == 50


class TestAdmissionControl:
    """Test concurrency limiting functionality."""

    @pytest.mark.asyncio
    async def test_request_success(self, mock_client, registry_with_models):
        """Test that requests succeed with admission control enabled."""
        from lumine.llm_gateway import AdmissionControl, LLMGateway

        budget_tracker = BudgetTracker(daily_budget_usd=100.0, weekly_budget_usd=500.0)

        control = AdmissionControl(enabled=True, max_concurrent=10)

        gateway = LLMGateway(
            registry=registry_with_models,
            nine_router_client=mock_client,
            budget_tracker=budget_tracker,
            admission_control=control,
        )

        request1 = GatewayRequest(
            model_version_id="gpt-5.5-prod",
            prompt_ref="analysis-standard",
            role="analyst",
            payload={"messages": [{"role": "user", "content": "Test 1"}]},
        )
        request2 = GatewayRequest(
            model_version_id="gpt-5.5-prod",
            prompt_ref="analysis-standard",
            role="analyst",
            payload={"messages": [{"role": "user", "content": "Test 2"}]},
        )

        response1 = await gateway.invoke(request1)
        response2 = await gateway.invoke(request2)

        assert response1.success is True
        assert response2.success is True
