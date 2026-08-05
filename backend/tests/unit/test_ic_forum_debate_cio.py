# Copyright (c) 2026 Lumine. All rights reserved.
"""Unit tests for IC Forum, CIO Proposer, and Debate (D4-4/D4-5/D4-6)."""

from __future__ import annotations

import uuid

import pytest

from lumine.autogen_pipeline.cio_proposer import run_cio_proposer
from lumine.autogen_pipeline.debate import (
    disagreement_score,
    ic_confidence_predicted,
    run_debate,
    should_debate,
)
from lumine.autogen_pipeline.ic_forum import run_ic_forum
from lumine.shared.errors import SchemaValidationError
from tests.unit.fakes import (
    FakeGateway,
    debate_json,
    ic_output_json,
    make_registry,
    proposal_json,
)

_ID = uuid.uuid4()
_LINEAGE = uuid.uuid4()

_PINS = {
    "technical_analyst": str(_ID),
    "macro_analyst": str(_ID),
    "news_analyst": str(_ID),
    "smc_analyst": str(_ID),
    "ic_forum": str(_ID),
    "cio_proposer": str(_ID),
}


def _analysts() -> list[dict[str, object]]:
    return [
        {"sub_role": "technical_analyst", "argument": "hh", "confidence": 0.8, "bias": "bullish"},
        {"sub_role": "macro_analyst", "argument": "mm", "confidence": 0.7, "bias": "bullish"},
        {"sub_role": "news_analyst", "argument": "nn", "confidence": 0.6, "bias": "neutral"},
        {"sub_role": "smc_analyst", "argument": "ss", "confidence": 0.9, "bias": "bullish"},
    ]


class TestICForum:
    async def test_produces_valid_ic_output(self) -> None:
        gateway = FakeGateway(handler=lambda _req: ic_output_json())
        result = await run_ic_forum(
            gateway=gateway,
            registry=make_registry(),
            lineage_id=_LINEAGE,
            workflow_run_id="wf",
            stage_run_id="ic",
            model_version_id=_ID,
            idempotency_key="ic-1",
            symbol="XAUUSD",
            decision_ts="2026-08-05T00:00:00Z",
            analyst_inputs=_analysts(),
        )
        assert result.parsed["recommendation"] == "BUY"
        assert gateway.calls[0].role == "ic_forum"

    async def test_rejects_invalid_after_retry(self) -> None:
        gateway = FakeGateway(handler=lambda _req: ic_output_json(weights={"technical_analyst": 1}))
        # Missing 3 of the 4 required weight keys → schema violation both tries.
        with pytest.raises(SchemaValidationError):
            await run_ic_forum(
                gateway=gateway,
                registry=make_registry(),
                lineage_id=_LINEAGE,
                workflow_run_id="wf",
                stage_run_id="ic",
                model_version_id=_ID,
                idempotency_key="ic-2",
                symbol="XAUUSD",
                decision_ts="2026-08-05T00:00:00Z",
                analyst_inputs=_analysts(),
            )
        assert len(gateway.calls) == 2


class TestDebateFormulas:
    def test_ic_confidence_predicted_is_mean(self) -> None:
        assert ic_confidence_predicted(_analysts()) == 0.75

    def test_disagreement_score_consensus_is_zero(self) -> None:
        consensus = [
            {"confidence": 0.8, "bias": "bullish"} for _ in range(4)
        ]  # type: ignore[list-item]
        assert disagreement_score(consensus) == 0.0

    def test_disagreement_score_split(self) -> None:
        split = [
            {"bias": "bullish", "confidence": 0.5},
            {"bias": "bullish", "confidence": 0.5},
            {"bias": "bearish", "confidence": 0.5},
            {"bias": "bearish", "confidence": 0.5},
        ]
        # direction_disagreement = 0.5 (2v2), spread 0 → 0.7*0.5 = 0.35.
        assert disagreement_score(split) == pytest.approx(0.35)

    def test_should_debate_triggers_on_low_confidence(self) -> None:
        low_conf = [
            {"bias": "bullish", "confidence": 0.3} for _ in range(4)
        ]  # type: ignore[list-item]
        assert (
            should_debate(
                low_conf, ic_confidence_threshold=0.6, disagreement_threshold=0.3
            )
            is True
        )

    def test_should_debate_triggers_on_disagreement(self) -> None:
        assert (
            should_debate(
                [
                    {"bias": "bullish", "confidence": 0.9},
                    {"bias": "bullish", "confidence": 0.9},
                    {"bias": "bearish", "confidence": 0.9},
                    {"bias": "bearish", "confidence": 0.9},
                ],
                ic_confidence_threshold=0.2,
                disagreement_threshold=0.2,
            )
            is True
        )

    def test_should_debate_quiet_when_consensus_high_confidence(self) -> None:
        strong = [
            {"bias": "bullish", "confidence": 0.9} for _ in range(4)
        ]  # type: ignore[list-item]
        assert (
            should_debate(
                strong, ic_confidence_threshold=0.6, disagreement_threshold=0.4
            )
            is False
        )


class TestDebateStage:
    async def test_run_debate_produces_valid_output(self) -> None:
        gateway = FakeGateway(handler=lambda _req: debate_json())
        result = await run_debate(
            gateway=gateway,
            registry=make_registry(),
            lineage_id=_LINEAGE,
            workflow_run_id="wf",
            stage_run_id="debate",
            model_version_id=_ID,
            idempotency_key="debate-1",
            symbol="XAUUSD",
            decision_ts="2026-08-05T00:00:00Z",
            analyst_inputs=_analysts(),
        )
        assert result.parsed["consensus_direction"] == "bullish"
        assert gateway.calls[0].role == "debate_moderator"


class TestCIOProposer:
    async def test_produces_valid_proposal(self) -> None:
        gateway = FakeGateway(handler=lambda _req: proposal_json())
        result = await run_cio_proposer(
            gateway=gateway,
            registry=make_registry(),
            lineage_id=_LINEAGE,
            workflow_run_id="wf",
            stage_run_id="cio",
            model_version_id=_ID,
            idempotency_key="cio-1",
            symbol="XAUUSD",
            decision_ts="2026-08-05T00:00:00Z",
            ic_output={"recommendation": "BUY", "confidence": 0.8},
            analyst_inputs=_analysts(),
            portfolio_context={},
            policy_version_id=str(_ID),
            model_version_ids=_PINS,
            prompt_version_ids=_PINS,
            debate_held=False,
        )
        assert result.parsed["version"] == "v1"
        assert result.parsed["action"] == "BUY"
        assert gateway.calls[0].role == "cio_proposer"

    async def test_retry_on_invalid_schema_then_safe_state(self) -> None:
        gateway = FakeGateway(handler=lambda _req: proposal_json(action="HODL"))
        # "HODL" not in action enum → invalid on both attempts.
        with pytest.raises(SchemaValidationError):
            await run_cio_proposer(
                gateway=gateway,
                registry=make_registry(),
                lineage_id=_LINEAGE,
                workflow_run_id="wf",
                stage_run_id="cio",
                model_version_id=_ID,
                idempotency_key="cio-2",
                symbol="XAUUSD",
                decision_ts="2026-08-05T00:00:00Z",
                ic_output={"recommendation": "HOLD"},
                analyst_inputs=_analysts(),
                portfolio_context={},
                policy_version_id=str(_ID),
                model_version_ids=_PINS,
                prompt_version_ids=_PINS,
                debate_held=True,
            )
        assert len(gateway.calls) == 2
