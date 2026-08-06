# Copyright (c) 2026 Lumine. All rights reserved.
"""Unit tests for the decision-cycle orchestrator (D3-12, D4-*, D7-*).

The orchestrator is exercised end-to-end with a scripted FakeGateway
(simulating all LLM roles), a FakeSession (in-memory persistence), and a
stub execution router. Scenarios cover the plan's Level 4 list at unit
granularity: strong buy, hold/noop, risk rejection, assessor veto,
debate-triggered cycle, and safe state on lineage-write failure.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import TYPE_CHECKING, Any

import pytest

from lumine.autogen_pipeline.orchestrator import (
    CycleContext,
    DecisionOrchestrator,
    PortfolioState,
    volatility_band,
)
from lumine.data.lineage import LineageWriteError
from lumine.data.models import LineageRecord, WorkflowJournal
from lumine.shared.config import get_settings
from lumine.shared.errors import DeadlineExceededError
from lumine.trade_core.execution_router import DispatchResult
from lumine.trade_core.risk_validator import RiskLimits
from tests.unit.fakes import (
    FakeGateway,
    FakeSession,
    analyst_json,
    debate_json,
    ic_output_json,
    make_registry,
    proposal_json,
    risk_assessment_json,
)

if TYPE_CHECKING:
    from lumine.llm_gateway.types import RouterRequest

_ROLE = "technical_analyst"


def _handler(
    *,
    action: str = "BUY",
    analyst_confidence: float = 0.8,
    veto: bool = False,
) -> Any:  # noqa: ANN401 — scripted fixture returns raw model text
    """Scripted per-role LLM output handler."""

    def handle(req: RouterRequest) -> str:
        role = req.role
        if role in {"technical_analyst", "macro_analyst", "news_analyst", "smc_analyst"}:
            return analyst_json(sub_role=role, confidence=analyst_confidence)
        if role == "debate_moderator":
            return debate_json()
        if role == "ic_forum":
            return ic_output_json()
        if role == "cio_proposer":
            return proposal_json(action=action)
        if role == "risk_officer":
            return risk_assessment_json(veto=veto)
        msg = f"unexpected role {role}"
        raise AssertionError(msg)

    return handle


def _vars(role: str) -> dict[str, object]:
    """Domain variables for the analyst prompt of ``role``."""
    common = {"symbol": "XAUUSD", "decision_ts": "2026-08-05T00:00:00Z"}
    match role:
        case "technical_analyst":
            return {
                **common,
                "atr_14": 15.0,
                "ema_20": 2730.0,
                "ema_50": 2725.0,
                "rsi_14": 58.0,
                "ohlc": "[2734.5, 2736.1, 2728.0, 2732.4]",
                "swing_structure": "HH/HL",
            }
        case "macro_analyst":
            return {
                **common,
                "us_10y": 4.25,
                "us_2y": 4.10,
                "dxy": 103.5,
                "real_yields": 2.1,
                "fed_stance": "neutral",
                "risk_regime": "risk-on",
            }
        case "news_analyst":
            return {
                **common,
                "headlines": '["Fed holds"]',
                "sentiment_score": 0.4,
                "relevance_score": 0.8,
                "scheduled_events": '["CPI 08:30 UTC"]',
            }
        case "smc_analyst":
            return {
                **common,
                "order_blocks": '[{"level": 2720}]',
                "liquidity_pools": '["2730-2740"]',
                "liquidity_sweep": "none",
                "fair_value_gaps": '[{"level": 2732}]',
                "market_structure": "bullish",
            }
    return dict(common)


_ROLES = ("technical_analyst", "macro_analyst", "news_analyst", "smc_analyst")
_ANALYST_VARS = {r: _vars(r) for r in _ROLES}


def _ctx(**overrides: Any) -> CycleContext:  # noqa: ANN401
    pins = {r: str(uuid.uuid4()) for r in (*_ROLES, "ic_forum", "cio_proposer", "risk_officer")}
    base = {
        "symbol": "XAUUSD",
        "book": "main",
        "workflow_id": "wf-test",
        "decision_ts": "2026-08-05T00:00:00Z",
        "equity": Decimal(100000),
        "entry_price": Decimal("2734.50"),
        "atr_14": Decimal(15),
        "strategy_id": uuid.uuid4(),
        "policy_version_id": uuid.uuid4(),
        "model_version_ids": pins,
        "prompt_version_ids": pins,
        "analyst_variables": _ANALYST_VARS,
        "policy": {
            "ic_confidence_threshold": 0.6,
            "disagreement_threshold": 0.4,
            "risk_adjustments": {"trending": {"low": "1.0"}},
        },
        "risk_limits": RiskLimits(),
    }
    base.update(overrides)
    return CycleContext(**base)  # type: ignore[arg-type]


def _portfolio(**overrides: Any) -> PortfolioState:  # noqa: ANN401
    base = {
        "equity": Decimal(100000),
        "total_notional": Decimal(0),
        "correlated_notional": Decimal(0),
        "daily_pnl": Decimal(0),
        "open_positions": 0,
        "strategy_notional": Decimal(0),
        "kill_switch": False,
    }
    base.update(overrides)
    return PortfolioState(**base)  # type: ignore[arg-type]


class StubExecutionRouter:
    """Records dispatches; never touches Redis/DB (unit-test double)."""

    def __init__(self) -> None:
        """Initialize the recording stub."""
        self.calls: list[tuple[Any, Any, int]] = []

    async def dispatch(
        self,
        _session: Any,  # noqa: ANN401 — interface parity with ExecutionRouter
        *,
        lineage_id: Any,  # noqa: ANN401
        command: Any,  # noqa: ANN401
        attempt: int = 1,
    ) -> DispatchResult:
        """Record the dispatch and return a scripted fill."""
        self.calls.append((lineage_id, command, attempt))
        return DispatchResult(status="filled", ticket=1001, fill_price=Decimal("2734.50"))


def _orchestrator(
    gateway: FakeGateway, session: FakeSession, router: StubExecutionRouter
) -> DecisionOrchestrator:
    return DecisionOrchestrator(
        gateway=gateway,
        registry=make_registry(),
        session=session,
        execution_router=router,
        settings=get_settings(),
    )


class TestVolatilityBand:
    def test_band_thresholds(self) -> None:
        assert volatility_band(Decimal(5), Decimal(2734)) == "low"  # 0.18%
        assert volatility_band(Decimal(20), Decimal(2734)) == "med"  # 0.73%
        assert volatility_band(Decimal(50), Decimal(2734)) == "high"  # 1.8%


class TestDecisionCycle:
    async def test_strong_buy_approves_and_dispatches(self) -> None:
        gateway = FakeGateway(handler=_handler())
        session = FakeSession()
        router = StubExecutionRouter()
        result = await _orchestrator(gateway, session, router).execute(_ctx(), _portfolio())

        assert result.verdict == "approved"
        assert result.action == "BUY"
        assert result.volume > 0
        assert len(router.calls) == 1
        command = router.calls[0][1]
        assert command.symbol == "XAUUSD"
        assert command.stop_loss is not None
        # Lineage written before dispatch: record exists with the proposal.
        lineage = [o for o in session.added if isinstance(o, LineageRecord)]
        assert len(lineage) == 1
        assert lineage[0].verdict == "approved"
        assert lineage[0].proposal["reasoning_trace_ids"]  # traces pinned

    async def test_hold_produces_noop_without_dispatch(self) -> None:
        gateway = FakeGateway(handler=_handler(action="HOLD"))
        session = FakeSession()
        router = StubExecutionRouter()
        result = await _orchestrator(gateway, session, router).execute(_ctx(), _portfolio())

        assert result.verdict == "noop"
        assert result.action == "HOLD"
        assert router.calls == []
        lineage = [o for o in session.added if isinstance(o, LineageRecord)]
        assert lineage[0].verdict == "noop"

    async def test_risk_rejection_stops_before_dispatch(self) -> None:
        gateway = FakeGateway(handler=_handler())
        session = FakeSession()
        router = StubExecutionRouter()
        # A 5M notional book dwarfs the 5% total-exposure cap.
        result = await _orchestrator(gateway, session, router).execute(
            _ctx(), _portfolio(total_notional=Decimal(5000000))
        )

        assert result.verdict == "rejected"
        assert router.calls == []
        assert any("total_exposure_exceeded" in r for r in result.reasons)

    async def test_assessor_veto_rejects(self) -> None:
        gateway = FakeGateway(handler=_handler(veto=True))
        session = FakeSession()
        router = StubExecutionRouter()
        result = await _orchestrator(gateway, session, router).execute(_ctx(), _portfolio())

        assert result.verdict == "rejected"
        assert "risk_assessor_veto" in result.reasons
        assert router.calls == []

    async def test_debate_fires_on_low_analyst_confidence(self) -> None:
        gateway = FakeGateway(handler=_handler(analyst_confidence=0.3))
        session = FakeSession()
        router = StubExecutionRouter()
        result = await _orchestrator(gateway, session, router).execute(_ctx(), _portfolio())

        assert result.verdict == "approved"
        # The moderator stage ran: role debate_moderator was called.
        assert any(c.role == "debate_moderator" for c in gateway.calls)
        # Debate evidence lands in the journal as DEBATE_VALIDATED.
        steps = [o for o in session.added if isinstance(o, WorkflowJournal)]
        assert any(s.step_name == "DEBATE_VALIDATED" for s in steps)

    async def test_lineage_write_failure_is_safe_state(self) -> None:
        gateway = FakeGateway(handler=_handler())
        session = FakeSession(fail_on_lineage=True)
        router = StubExecutionRouter()

        with pytest.raises(LineageWriteError):
            await _orchestrator(gateway, session, router).execute(_ctx(), _portfolio())
        assert router.calls == []  # nothing dispatched after a failed write

    async def test_backfill_failure_rolls_back_lineage_atomically(self) -> None:
        # A3: the lineage INSERT and the trace/journal backfill share one
        # transaction. If the backfill commit fails, the lineage row must
        # be rolled back too — no orphan lineage record reaches dispatch.
        gateway = FakeGateway(handler=_handler())
        session = FakeSession(fail_backfill_commit=True)
        router = StubExecutionRouter()

        with pytest.raises(LineageWriteError):
            await _orchestrator(gateway, session, router).execute(_ctx(), _portfolio())
        assert router.calls == []  # dispatch never ran
        # Rollback dropped the flushed lineage row — it is not persisted.
        lineage = [o for o in session.added if isinstance(o, LineageRecord)]
        assert lineage == [], "lineage row must be rolled back with the failed backfill"

    async def test_trace_write_failure_is_safe_state(self) -> None:
        gateway = FakeGateway(handler=_handler())
        session = FakeSession(fail_commit=True)  # fails on the very first trace commit
        router = StubExecutionRouter()

        from lumine.autogen_pipeline.traces import ReasoningTraceError

        with pytest.raises(ReasoningTraceError):
            await _orchestrator(gateway, session, router).execute(_ctx(), _portfolio())
        assert router.calls == []

    async def test_kill_switch_halts(self) -> None:
        gateway = FakeGateway(handler=_handler())
        session = FakeSession()
        router = StubExecutionRouter()
        result = await _orchestrator(gateway, session, router).execute(
            _ctx(), _portfolio(kill_switch=True)
        )

        assert result.verdict == "rejected"
        assert any("kill_switch_active" in r for r in result.reasons)
        assert router.calls == []


class TestDeadline:
    async def test_zero_budget_fails_fast(self) -> None:
        from lumine.shared.config import Settings, override_settings

        settings = Settings(decision_cycle_timeout_s=0)
        override_settings(settings)
        try:
            gateway = FakeGateway(handler=_handler())
            orchestrator = DecisionOrchestrator(
                gateway=gateway,
                registry=make_registry(),
                session=FakeSession(),
                execution_router=StubExecutionRouter(),
                settings=settings,
            )
            with pytest.raises(DeadlineExceededError):
                await orchestrator.execute(_ctx(), _portfolio())
        finally:
            override_settings(get_settings())


__all__ = ("StubExecutionRouter",)
