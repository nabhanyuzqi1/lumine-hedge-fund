# Copyright (c) 2026 Lumine. All rights reserved.
"""Unit tests for the advisory risk assessor (D8-7, ADR-0016, D3-9)."""

from __future__ import annotations

import uuid
from decimal import Decimal

from lumine.autogen_pipeline.risk_assessor import (
    apply_assessment,
    resolve_risk_adjustment,
    run_risk_assessor,
)
from tests.unit.fakes import FakeGateway, make_registry, risk_assessment_json


class TestResolveRiskAdjustment:
    def test_lookup_by_bucket_and_band(self) -> None:
        policy = {
            "trending": {"low": "1.0", "high": "0.8"},
            "ranging": {"low": "0.9"},
        }
        assert resolve_risk_adjustment(policy, "trending", "high") == Decimal("0.8")
        assert resolve_risk_adjustment(policy, "ranging", "low") == Decimal("0.9")

    def test_missing_bucket_or_band_fails_closed_to_one(self) -> None:
        policy = {"trending": {"low": "0.8"}}
        assert resolve_risk_adjustment(policy, "volatile", "high") == Decimal(1)
        assert resolve_risk_adjustment(policy, "trending", "high") == Decimal(1)

    def test_non_mapping_and_bad_values_fail_closed(self) -> None:
        assert resolve_risk_adjustment({"trending": "nope"}, "trending", "low") == Decimal(1)
        assert resolve_risk_adjustment({}, "trending", "low") == Decimal(1)

    def test_malformed_band_value_fails_closed(self) -> None:
        # Regression: Decimal("not_a_number") raises InvalidOperation (an
        # ArithmeticError, NOT a ValueError). The fail-closed contract
        # must catch it and return DEFAULT_MULTIPLIER rather than crash.
        policy = {"calm": {"low": "not_a_number", "high": "1.5"}}
        assert resolve_risk_adjustment(policy, "calm", "low") == Decimal(1)
        assert resolve_risk_adjustment(policy, "calm", "high") == Decimal("1.5")


class TestApplyAssessment:
    def test_final_volume_is_base_times_multiplier(self) -> None:
        assessed = apply_assessment(
            assessment={"veto": False, "regime_bucket": "trending", "risk_notes": "ok"},
            base_volume=Decimal("5.00"),
            risk_adjustments={"trending": {"low": "0.5"}},
            volatility_band="low",
        )
        assert assessed.final_volume == Decimal("2.50")
        assert assessed.multiplier == Decimal("0.5")
        assert assessed.veto is False

    def test_veto_flag_surfaces(self) -> None:
        assessed = apply_assessment(
            assessment={"veto": True, "regime_bucket": "volatile", "risk_notes": "binary event"},
            base_volume=Decimal("5.00"),
            risk_adjustments={},
            volatility_band="high",
        )
        assert assessed.veto is True

    def test_missing_bucket_uses_default_multiplier(self) -> None:
        assessed = apply_assessment(
            assessment={"veto": False, "regime_bucket": "volatile", "risk_notes": "x"},
            base_volume=Decimal("5.00"),
            risk_adjustments={},
            volatility_band="high",
        )
        assert assessed.multiplier == Decimal(1)
        assert assessed.final_volume == Decimal("5.00")

    def test_volume_clamped_to_broker_range(self) -> None:
        assessed = apply_assessment(
            assessment={"veto": False, "regime_bucket": "trending", "risk_notes": "x"},
            base_volume=Decimal("5.00"),
            risk_adjustments={"trending": {"low": "30"}},  # 150 lots > broker max
            volatility_band="low",
            max_volume=Decimal(100),
        )
        assert assessed.final_volume == Decimal(100)


class TestRiskAssessorStage:
    async def test_valid_assessment_parses(self) -> None:
        gateway = FakeGateway(handler=lambda _req: risk_assessment_json())
        result = await run_risk_assessor(
            gateway=gateway,
            registry=make_registry(),
            lineage_id=uuid.uuid4(),
            workflow_run_id="wf",
            stage_run_id="risk",
            model_version_id=uuid.uuid4(),
            idempotency_key="risk-1",
            symbol="XAUUSD",
            decision_ts="2026-08-05T00:00:00Z",
            proposal_summary={"action": "BUY", "confidence": 0.7},
            portfolio_context={"exposure": 0.01},
            volatility_band="low",
        )
        assert result.parsed["veto"] is False
        assert result.parsed["regime_bucket"] == "trending"
        assert gateway.calls[0].role == "risk_officer"

    async def test_veto_true_is_accepted_as_valid_output(self) -> None:
        gateway = FakeGateway(handler=lambda _req: risk_assessment_json(veto=True))
        result = await run_risk_assessor(
            gateway=gateway,
            registry=make_registry(),
            lineage_id=uuid.uuid4(),
            workflow_run_id="wf",
            stage_run_id="risk",
            model_version_id=uuid.uuid4(),
            idempotency_key="risk-2",
            symbol="XAUUSD",
            decision_ts="2026-08-05T00:00:00Z",
            proposal_summary={"action": "BUY"},
            portfolio_context={},
            volatility_band="high",
        )
        assert result.parsed["veto"] is True
