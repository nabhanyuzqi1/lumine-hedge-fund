# Copyright (c) 2026 Lumine. All rights reserved.
"""Unit tests for the four analyst agents (D4-2/D4-3).

Each agent is exercised through the real prompt registry and output
schema, with a scripted FakeGateway producing raw model text. We assert:
- the rendered prompt reached the gateway with the right role/tier,
- a schema-valid response parses cleanly,
- invalid JSON / schema violations trigger exactly one retry,
- gateways that keep failing raise SchemaValidationError (safe state).
"""

from __future__ import annotations

import json
import uuid
from typing import TYPE_CHECKING

import pytest

from lumine.autogen_pipeline.agents import (
    run_macro_analyst,
    run_news_analyst,
    run_smc_analyst,
    run_technical_analyst,
)
from lumine.autogen_pipeline.agents._base import run_analyst
from lumine.llm_gateway.types import ModelTier
from lumine.shared.errors import SchemaValidationError
from tests.unit.fakes import FakeGateway, analyst_json, make_registry

if TYPE_CHECKING:
    from lumine.autogen_pipeline._base import StageResult
    from lumine.llm_gateway.types import RouterRequest

_ID = uuid.uuid4()
_LINEAGE = uuid.uuid4()

_COMMON = {
    "symbol": "XAUUSD",
    "decision_ts": "2026-08-05T00:00:00Z",
}


def _vars(role: str) -> dict[str, object]:
    """Domain variables required by the prompt for ``role`` (registry.yaml)."""
    match role:
        case "technical_analyst":
            return {
                **_COMMON,
                "atr_14": 15.0,
                "ema_20": 2730.0,
                "ema_50": 2725.0,
                "rsi_14": 58.0,
                "ohlc": "[2734.5, 2736.1, 2728.0, 2732.4]",
                "swing_structure": "HH/HL since 2026-08-01",
            }
        case "macro_analyst":
            return {
                **_COMMON,
                "us_10y": 4.25,
                "us_2y": 4.10,
                "dxy": 103.5,
                "real_yields": 2.1,
                "fed_stance": "neutral",
                "risk_regime": "risk-on",
            }
        case "news_analyst":
            return {
                **_COMMON,
                "headlines": '["Fed holds rates", "Gold demand rises"]',
                "sentiment_score": 0.4,
                "relevance_score": 0.8,
                "scheduled_events": '["CPI 08:30 UTC"]',
            }
        case "smc_analyst":
            return {
                **_COMMON,
                "order_blocks": '[{"level": 2720, "type": "bullish"}]',
                "liquidity_pools": '["2730-2740"]',
                "liquidity_sweep": "none",
                "fair_value_gaps": '[{"level": 2732}]',
                "market_structure": "bullish",
            }
    return dict(_COMMON)


async def _run(gateway: FakeGateway, role: str, variables: dict[str, object]) -> StageResult:
    """Dispatch to the correct analyst by role."""
    kwargs = {
        "gateway": gateway,
        "registry": make_registry(),
        "lineage_id": _LINEAGE,
        "workflow_run_id": "wf-test",
        "stage_run_id": f"stage-{role}",
        "model_version_id": _ID,
        "idempotency_key": f"{_LINEAGE}:{role}",
        "variables": variables,
    }
    match role:
        case "technical_analyst":
            return await run_technical_analyst(**kwargs)
        case "macro_analyst":
            return await run_macro_analyst(**kwargs)
        case "news_analyst":
            return await run_news_analyst(**kwargs)
        case "smc_analyst":
            return await run_smc_analyst(**kwargs)
    pytest.fail(f"unexpected role {role}")


class TestAnalystStages:
    @pytest.mark.parametrize(
        "role",
        ["technical_analyst", "macro_analyst", "news_analyst", "smc_analyst"],
    )
    async def test_valid_output_parses_and_requests_proper_tier(self, role: str) -> None:
        gateway = FakeGateway(handler=lambda _req: analyst_json(sub_role=role))
        result = await _run(gateway, role, _vars(role))

        assert result.parsed["bias"] == "bullish"
        assert result.parsed["confidence"] == 0.72
        assert not result.degraded

        req = gateway.calls[0]
        assert req.role == role
        assert req.lineage_id == _LINEAGE
        assert len(req.messages) == 1
        # The rendered prompt must not contain an unresolved placeholder.
        assert "{{" not in req.messages[0].content

    @pytest.mark.parametrize(
        ("role", "expected_tier"),
        [
            ("technical_analyst", ModelTier.COST_EFFICIENT),
            ("macro_analyst", ModelTier.CONTEXT_RICH),
            ("news_analyst", ModelTier.COST_EFFICIENT),
            ("smc_analyst", ModelTier.CONTEXT_RICH),
        ],
    )
    async def test_tier_matches_registry_hint(self, role: str, expected_tier: ModelTier) -> None:
        gateway = FakeGateway(handler=lambda _req: analyst_json(sub_role=role))
        await _run(gateway, role, _vars(role))
        assert gateway.calls[0].tier == expected_tier

    async def test_invalid_json_retries_once_then_raises(self) -> None:
        # Always return garbage — the "fix your JSON" retry is attempted
        # once, then the stage fails into safe state.
        gateway = FakeGateway(handler=lambda _req: "not json at all")
        with pytest.raises(SchemaValidationError):
            await _run(gateway, "technical_analyst", _vars("technical_analyst"))
        assert len(gateway.calls) == 2
        assert gateway.calls[1].idempotency_key.endswith("-retry")

    async def test_schema_violation_retries_then_raises(self) -> None:
        # Valid JSON but wrong shape (missing required 'bias').
        gateway = FakeGateway(
            handler=lambda _req: json.dumps({"sub_role": "technical_analyst", "argument": "x"})
        )
        with pytest.raises(SchemaValidationError):
            await _run(gateway, "technical_analyst", _vars("technical_analyst"))
        assert len(gateway.calls) == 2

    async def test_second_attempt_can_recover(self) -> None:
        # First call invalid, retry fixes it.
        call_count = 0

        def handler(_req: RouterRequest) -> str:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return "not json"
            return analyst_json()

        gateway = FakeGateway(handler=handler)
        result = await _run(gateway, "technical_analyst", _vars("technical_analyst"))
        assert result.parsed["bias"] == "bullish"
        assert len(gateway.calls) == 2


class TestSharedRunner:
    async def test_run_analyst_builds_context(self) -> None:
        gateway = FakeGateway(handler=lambda _req: analyst_json(sub_role="technical_analyst"))
        await run_analyst(
            "technical_analyst",
            gateway=gateway,
            registry=make_registry(),
            lineage_id=_LINEAGE,
            workflow_run_id="wf",
            stage_run_id="s",
            model_version_id=_ID,
            idempotency_key="k",
            variables=_vars("technical_analyst"),
            session=None,
        )
        assert gateway.calls[0].role == "technical_analyst"
