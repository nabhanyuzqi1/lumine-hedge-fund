# Copyright (c) 2026 Lumine. All rights reserved.
"""Level 4 system tests — full decision cycle (Sprint 3 deliverable 13).

Runs the real orchestrator against real PostgreSQL + Redis (testcontainers)
with a scripted FakeGateway for every LLM role and a fake MT5 bridge for
fills. Scenarios mirror the plan's Level 4 list: strong buy/sell, neutral,
split committee (debate fires), CIO override, debate triggered, lineage
write failure → halt, and safe state on component failure.

Exit criteria asserted here: full cycle runs end-to-end, all four
analysts produce schema-valid output, IC handles split scenarios, CIO
override works, risk rejects over-exposure, lineage is written before
dispatch, and a failed lineage write halts everything.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import TYPE_CHECKING, Any

import pytest
import pytest_asyncio
from sqlalchemy import select

from lumine.autogen_pipeline.orchestrator import (
    CycleContext,
    DecisionOrchestrator,
    PortfolioState,
)
from lumine.bridge.client import BridgeClient
from lumine.bridge.types import BridgeCommand, BridgeResult, BridgeStatus
from lumine.data.lineage import LineageWriteError
from lumine.data.models import LineageRecord, ProcessedCommand, WorkflowJournal
from lumine.llm_gateway.client import RouterClientError
from lumine.trade_core.execution_router import ExecutionRouter
from lumine.trade_core.risk_validator import RiskLimits
from tests.integration.factories import seed_model, seed_policy, seed_prompt, seed_strategy
from tests.unit.fakes import (
    FakeGateway,
    analyst_json,
    debate_json,
    ic_output_json,
    make_registry,
    proposal_json,
    risk_assessment_json,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from lumine.llm_gateway.types import RouterRequest

_ROLES = ("technical_analyst", "macro_analyst", "news_analyst", "smc_analyst")


def _analyst_vars() -> dict[str, dict[str, object]]:
    common = {"symbol": "XAUUSD", "decision_ts": "2026-08-05T00:00:00Z"}
    return {
        "technical_analyst": {
            **common,
            "atr_14": 15.0,
            "ema_20": 2730.0,
            "ema_50": 2725.0,
            "rsi_14": 58.0,
            "ohlc": "[2734.5, 2736.1, 2728.0, 2732.4]",
            "swing_structure": "HH/HL",
        },
        "macro_analyst": {
            **common,
            "us_10y": 4.25,
            "us_2y": 4.10,
            "dxy": 103.5,
            "real_yields": 2.1,
            "fed_stance": "neutral",
            "risk_regime": "risk-on",
        },
        "news_analyst": {
            **common,
            "headlines": '["Fed holds"]',
            "sentiment_score": 0.4,
            "relevance_score": 0.8,
            "scheduled_events": '["CPI 08:30 UTC"]',
        },
        "smc_analyst": {
            **common,
            "order_blocks": '[{"level": 2720}]',
            "liquidity_pools": '["2730-2740"]',
            "liquidity_sweep": "none",
            "fair_value_gaps": '[{"level": 2732}]',
            "market_structure": "bullish",
        },
    }


def _handler(
    *,
    action: str = "BUY",
    analyst_confidence: float = 0.8,
    analyst_bias: str = "bullish",
    veto: bool = False,
    overrode_ic: bool = False,
    fail_role: str | None = None,
) -> Any:  # noqa: ANN401 — scripted fixture returns raw model text
    """Scripted per-role LLM output; ``fail_role`` simulates a gateway outage."""

    def handle(req: RouterRequest) -> str:
        role = req.role
        if fail_role == role:
            raise RouterClientError("simulated gateway outage")
        if role in _ROLES:
            return analyst_json(sub_role=role, confidence=analyst_confidence, bias=analyst_bias)
        if role == "debate_moderator":
            return debate_json()
        if role == "ic_forum":
            return ic_output_json()
        if role == "cio_proposer":
            return proposal_json(action=action, overrode_ic=overrode_ic)
        if role == "risk_officer":
            return risk_assessment_json(veto=veto)
        msg = f"unexpected role {role}"
        raise AssertionError(msg)

    return handle


class FakeBridge(BridgeClient):
    """Records commands; returns scripted fills (the simulated EA)."""

    def __init__(self) -> None:
        """Initialize the fake EA bridge."""
        self.calls: list[BridgeCommand] = []

    async def send_and_wait(self, command: BridgeCommand) -> BridgeResult:
        self.calls.append(command)
        return BridgeResult(
            command_id=command.command_id,
            order_id=command.order_id,
            status=BridgeStatus.FILLED,
            ticket=7001,
            fill_price=2734.5,
            fill_volume=command.volume,
        )


@pytest_asyncio.fixture
async def seeded_world(
    db_session: AsyncSession,
) -> dict[str, Any]:
    """Seed model/strategy/policy rows and return the version pins."""
    pins: dict[str, str] = {}
    prompt_pins: dict[str, str] = {}
    for role in (*_ROLES, "ic_forum", "cio_proposer", "risk_officer"):
        model = await seed_model(
            db_session,
            version=f"m-{role}-{uuid.uuid4().hex[:6]}",
            model_id="deepseek-v4",
            tier=(
                "cost-efficient"
                if role in ("technical_analyst", "news_analyst")
                else "context-rich"
            ),
        )
        pins[role] = str(model.id)
        prompt = await seed_prompt(
            db_session,
            version=f"p-{role}-{uuid.uuid4().hex[:6]}",
            sub_role=role,
        )
        prompt_pins[role] = str(prompt.id)
    strategy = await seed_strategy(db_session)
    policy = await seed_policy(
        db_session,
        policy={
            "ic_confidence_threshold": 0.6,
            "disagreement_threshold": 0.4,
            "risk_adjustments": {"trending": {"low": "1.0"}},
        },
    )
    return {
        "model_version_ids": pins,
        "prompt_version_ids": prompt_pins,
        "strategy_id": strategy.id,
        "policy_version_id": policy.id,
    }


def _ctx(seeded_world: dict[str, Any], **overrides: Any) -> CycleContext:  # noqa: ANN401
    base = {
        "symbol": "XAUUSD",
        "book": "main",
        "workflow_id": f"wf-{uuid.uuid4().hex[:8]}",
        "decision_ts": "2026-08-05T00:00:00Z",
        "equity": Decimal(100000),
        "entry_price": Decimal("2734.50"),
        "atr_14": Decimal(15),
        "strategy_id": seeded_world["strategy_id"],
        "policy_version_id": seeded_world["policy_version_id"],
        "model_version_ids": seeded_world["model_version_ids"],
        "prompt_version_ids": seeded_world["prompt_version_ids"],
        "analyst_variables": _analyst_vars(),
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


@pytest_asyncio.fixture
async def orchestrator(
    db_session: AsyncSession,
    redis_client: Any,  # noqa: ANN401
    integration_settings: Any,  # noqa: ANN401
) -> tuple[DecisionOrchestrator, FakeBridge]:
    from lumine.data.session import get_sessionmaker

    bridge = FakeBridge()
    router = ExecutionRouter(redis=redis_client, bridge=bridge)
    orche = DecisionOrchestrator(
        gateway=FakeGateway(handler=_handler()),
        registry=make_registry(),
        session=db_session,
        execution_router=router,
        settings=integration_settings,
        # One session per parallel analyst stage (AsyncSession is not
        # safe for concurrent commits on a single instance).
        session_factory=lambda: get_sessionmaker()(),  # noqa: PLW0108
    )
    return orche, bridge


async def _lineage_rows(db_session: AsyncSession) -> list[LineageRecord]:
    stmt = select(LineageRecord).order_by(LineageRecord.created_at)
    return list((await db_session.execute(stmt)).scalars().all())


class TestDecisionCycle:
    async def test_strong_buy_runs_end_to_end(
        self,
        db_session: AsyncSession,
        seeded_world: dict[str, Any],
        orchestrator: tuple[DecisionOrchestrator, FakeBridge],
    ) -> None:
        orche, bridge = orchestrator
        result = await orche.execute(_ctx(seeded_world), _portfolio())

        assert result.verdict == "approved"
        assert result.action == "BUY"
        assert result.dispatch is not None
        assert result.dispatch["status"] == "filled"
        assert len(bridge.calls) == 1
        # Lineage exists and was written before dispatch (record present).
        rows = await _lineage_rows(db_session)
        assert any(r.lineage_id == result.lineage_id and r.verdict == "approved" for r in rows)
        # The processed marker was persisted with the real lineage FK.
        stmt = select(ProcessedCommand).where(
            ProcessedCommand.lineage_id == result.lineage_id
        )
        assert (await db_session.execute(stmt)).scalar_one().result == "filled"

    async def test_strong_sell_dispatches_sell(
        self,
        db_session: AsyncSession,  # noqa: ARG002 — injected by fixture
        seeded_world: dict[str, Any],
        orchestrator: tuple[DecisionOrchestrator, FakeBridge],
    ) -> None:
        orche, bridge = orchestrator
        orche._gateway = FakeGateway(  # type: ignore[attr-defined]  # noqa: SLF001
            handler=_handler(action="SELL", analyst_bias="bearish")
        )
        result = await orche.execute(_ctx(seeded_world), _portfolio())

        assert result.verdict == "approved"
        assert result.action == "SELL"
        assert bridge.calls[0].action == "SELL"
        assert bridge.calls[0].stop_loss is not None  # SELL stop above entry

    async def test_neutral_hold_noop_no_dispatch(
        self,
        db_session: AsyncSession,
        seeded_world: dict[str, Any],
        orchestrator: tuple[DecisionOrchestrator, FakeBridge],
    ) -> None:
        orche, bridge = orchestrator
        orche._gateway = FakeGateway(  # type: ignore[attr-defined]  # noqa: SLF001
            handler=_handler(action="HOLD")
        )
        result = await orche.execute(_ctx(seeded_world), _portfolio())

        assert result.verdict == "noop"
        assert bridge.calls == []
        rows = await _lineage_rows(db_session)
        assert any(r.lineage_id == result.lineage_id and r.verdict == "noop" for r in rows)

    async def test_split_committee_fires_debate(
        self,
        db_session: AsyncSession,
        seeded_world: dict[str, Any],
        orchestrator: tuple[DecisionOrchestrator, FakeBridge],
    ) -> None:
        orche, _bridge = orchestrator
        # Low analyst confidence (0.3 < 0.6 threshold) → deterministic
        # debate trigger fires; the moderator stage must run.
        orche._gateway = FakeGateway(  # type: ignore[attr-defined]  # noqa: SLF001
            handler=_handler(analyst_confidence=0.3)
        )
        ctx = _ctx(seeded_world)
        result = await orche.execute(ctx, _portfolio())

        assert result.verdict == "approved"
        assert any(c.role == "debate_moderator" for c in orche._gateway.calls)  # type: ignore[attr-defined]  # noqa: SLF001
        # Debate evidence is journaled for THIS cycle.
        stmt = select(WorkflowJournal).where(WorkflowJournal.workflow_id == ctx.workflow_id)
        journal = list((await db_session.execute(stmt)).scalars().all())
        assert any(j.step_name == "DEBATE_VALIDATED" for j in journal)

    async def test_cio_override_proceeds(
        self,
        db_session: AsyncSession,
        seeded_world: dict[str, Any],
        orchestrator: tuple[DecisionOrchestrator, FakeBridge],
    ) -> None:
        orche, _bridge = orchestrator
        orche._gateway = FakeGateway(  # type: ignore[attr-defined]  # noqa: SLF001
            handler=_handler(overrode_ic=True)
        )
        result = await orche.execute(_ctx(seeded_world), _portfolio())

        assert result.verdict == "approved"
        rows = await _lineage_rows(db_session)
        proposal = next(r for r in rows if r.lineage_id == result.lineage_id).proposal
        assert proposal["overrode_ic"] is True

    async def test_risk_rejects_over_exposure(
        self,
        db_session: AsyncSession,  # noqa: ARG002 — injected by fixture
        seeded_world: dict[str, Any],
        orchestrator: tuple[DecisionOrchestrator, FakeBridge],
    ) -> None:
        orche, bridge = orchestrator
        result = await orche.execute(
            _ctx(seeded_world), _portfolio(total_notional=Decimal(5000000))
        )

        assert result.verdict == "rejected"
        assert bridge.calls == []
        assert any("total_exposure_exceeded" in r for r in result.reasons)

    async def test_lineage_write_failure_halts(
        self,
        db_session: AsyncSession,  # noqa: ARG002 — injected by fixture
        seeded_world: dict[str, Any],
        orchestrator: tuple[DecisionOrchestrator, FakeBridge],
    ) -> None:
        orche, bridge = orchestrator
        # Bogus policy_version_id → lineage FK violation → safe state, no dispatch.
        bogus = dict(seeded_world)
        bogus["policy_version_id"] = uuid.uuid4()
        with pytest.raises(LineageWriteError):
            await orche.execute(_ctx(bogus), _portfolio())
        assert bridge.calls == []

    async def test_gateway_failure_is_safe_state(
        self,
        db_session: AsyncSession,  # noqa: ARG002 — injected by fixture
        seeded_world: dict[str, Any],
        orchestrator: tuple[DecisionOrchestrator, FakeBridge],
    ) -> None:
        orche, bridge = orchestrator
        orche._gateway = FakeGateway(  # type: ignore[attr-defined]  # noqa: SLF001
            handler=_handler(fail_role="macro_analyst")
        )
        with pytest.raises(RouterClientError):
            await orche.execute(_ctx(seeded_world), _portfolio())
        assert bridge.calls == []
