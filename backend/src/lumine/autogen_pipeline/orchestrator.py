# Copyright (c) 2026 Lumine. All rights reserved.
"""Decision-cycle orchestrator (Phase 4/7, D3-12, D4-*, D7-*).

Wires the end-to-end cycle: 4 analysts (parallel, isolated) → optional
debate (deterministic trigger) → IC Forum → CIO Proposer → deterministic
sizing → advisory LLM risk assessor → deterministic risk validation →
lineage write (write-before-dispatch, D3-7) → execution dispatch.

Safe state by default: any stage failure raises and nothing dispatches.
Checkpoints ANALYSTS_VALIDATED / DEBATE_VALIDATED / IC_VALIDATED /
PROPOSAL_VALIDATED are journaled per cycle (workflow_journal). Deadline
propagation (D7-4) tracks a soft budget and fails fast before any stage
whose reserve would be exceeded.

``trade_core`` is the deterministic layer below this; the orchestrator is
the only place that composes LLM stages with the deterministic engine.
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from lumine.autogen_pipeline import debate
from lumine.autogen_pipeline.agents import (
    run_macro_analyst,
    run_news_analyst,
    run_smc_analyst,
    run_technical_analyst,
)
from lumine.autogen_pipeline.cio_proposer import run_cio_proposer
from lumine.autogen_pipeline.ic_forum import run_ic_forum
from lumine.autogen_pipeline.journal import log_step
from lumine.autogen_pipeline.risk_assessor import apply_assessment, run_risk_assessor
from lumine.bridge.types import BridgeCommand
from lumine.data.lineage import LineageInputs, LineageWriteError, write_lineage
from lumine.shared.errors import DeadlineExceededError
from lumine.trade_core.execution_router import TcaDispatchContext
from lumine.trade_core.risk_validator import RiskInputs, RiskLimits, assess_proposal
from lumine.trade_core.sizing_calculator import calculate_size

if TYPE_CHECKING:
    from collections.abc import Callable

    from sqlalchemy.ext.asyncio import AsyncSession

    from lumine.autogen_pipeline._base import StageResult
    from lumine.llm_gateway.gateway import Gateway
    from lumine.prompts.registry import Registry
    from lumine.shared.config import Settings
    from lumine.trade_core.execution_router import ExecutionRouter

# Per-role deadline reserves (ms) from deadline-propagation.md D7-4 (D3-12).
_ANALYST_RESERVE_MS = 500
_IC_RESERVE_MS = 800
_CIO_RESERVE_MS = 1000
_RISK_RESERVE_MS = 500

ANALYST_ROLES = ("technical_analyst", "macro_analyst", "news_analyst", "smc_analyst")


def _now_ms() -> int:
    return int(datetime.now(UTC).timestamp() * 1000)


def volatility_band(
    atr_14: Decimal,
    price: Decimal,
    *,
    low_pct: str = "0.005",
    high_pct: str = "0.01",
) -> str:
    """Deterministic ATR%-based band: ``low`` | ``med`` | ``high``."""
    pct = (atr_14 / price) if price > 0 else Decimal(0)
    if pct < Decimal(low_pct):
        return "low"
    if pct < Decimal(high_pct):
        return "med"
    return "high"


class _Deadline:
    """Tracks the soft cycle deadline; fails fast before a stage (D7-4)."""

    def __init__(self, total_ms: int) -> None:
        self.total_ms = total_ms
        self.started_ms = _now_ms()

    def remaining(self) -> int:
        return self.total_ms - (_now_ms() - self.started_ms)

    def ensure(self, reserve_ms: int) -> None:
        if self.remaining() <= reserve_ms:
            message = (
                f"deadline exceeded (remaining {self.remaining()}ms <= {reserve_ms}ms reserve)"
            )
            raise DeadlineExceededError(message)


@dataclass(frozen=True)
class CycleContext:
    """Static inputs for one decision cycle."""

    symbol: str
    book: str
    workflow_id: str
    decision_ts: str
    equity: Decimal
    entry_price: Decimal
    atr_14: Decimal
    strategy_id: uuid.UUID
    policy_version_id: uuid.UUID
    # role -> model_versions.id / prompt_versions.id; proposal pins all 6
    # agent roles; "risk_officer" is used by the advisory assessor.
    model_version_ids: dict[str, str]
    prompt_version_ids: dict[str, str]
    analyst_variables: dict[str, dict[str, object]]
    policy: dict[str, Any]
    risk_limits: RiskLimits
    broker_id: str | None = None
    account_id: str | None = None
    pip_value: Decimal | None = None
    pip_size: Decimal | None = None
    regime_id: str = "normal"
    feature_version_id: uuid.UUID | None = None
    regime_version_id: uuid.UUID | None = None
    calendar_version_id: uuid.UUID | None = None


@dataclass(frozen=True)
class PortfolioState:
    """Current-book metrics consumed by the deterministic risk engine."""

    equity: Decimal
    total_notional: Decimal = Decimal(0)
    correlated_notional: Decimal = Decimal(0)
    daily_pnl: Decimal = Decimal(0)
    open_positions: int = 0
    strategy_notional: Decimal = Decimal(0)
    proposed_is_correlated: bool = True
    kill_switch: bool = False


@dataclass(frozen=True)
class CycleResult:
    """Outcome of one full decision cycle."""

    lineage_id: uuid.UUID
    verdict: str  # approved | rejected | noop | safe_state
    action: str  # BUY | SELL | HOLD | REJECT
    volume: Decimal
    reasons: tuple[str, ...]
    dispatch: dict[str, Any] | None = None


class DecisionOrchestrator:
    """Compose LLM stages with the deterministic engine for one cycle."""

    def __init__(
        self,
        *,
        gateway: Gateway,
        registry: Registry,
        session: AsyncSession,
        execution_router: ExecutionRouter,
        settings: Settings,
        spend: dict[str, float] | None = None,
        session_factory: Callable[[], AsyncSession] | None = None,
    ) -> None:
        """Wire injected collaborators; ``spend`` is today's per-tier spend.

        ``session_factory`` gives each parallel analyst stage its own
        session for reasoning-trace writes (SQLAlchemy AsyncSession is
        not safe for concurrent commit on one instance). When ``None``
        (unit tests), the shared ``session`` is used.
        """
        self._gateway = gateway
        self._registry = registry
        self._session = session
        self._execution_router = execution_router
        self._settings = settings
        self._spend = spend
        self._session_factory = session_factory

    # ── helpers ─────────────────────────────────────────────────────────────

    def _deadline(self) -> _Deadline:
        return _Deadline(self._settings.decision_cycle_timeout_s * 1000)

    def _prompt_version_id(self, ctx: CycleContext, role: str) -> uuid.UUID | None:
        raw = ctx.prompt_version_ids.get(role)
        return uuid.UUID(raw) if raw else None

    async def _journal(
        self,
        ctx: CycleContext,
        lineage_id: uuid.UUID,
        step_name: str,
        status: str,
        *,
        output_snapshot: dict[str, Any] | None = None,
    ) -> None:
        await log_step(
            self._session,
            workflow_id=ctx.workflow_id,
            step_name=step_name,
            status=status,
            output_snapshot=output_snapshot,
            lineage_id=lineage_id,
        )

    # ── cycle ──────────────────────────────────────────────────────────────

    async def execute(  # noqa: PLR0915 — the cycle is a fixed multi-stage sequence
        self, ctx: CycleContext, portfolio: PortfolioState
    ) -> CycleResult:
        """Run the full cycle; raises (safe state) or returns a result."""
        lineage_id = uuid.uuid4()
        dl = self._deadline()

        # 1. Four analysts in parallel, isolated conversations.
        dl.ensure(_ANALYST_RESERVE_MS)
        tasks = [self._run_analyst(ctx, lineage_id, role) for role in ANALYST_ROLES]
        results = await asyncio.gather(*tasks)
        analyst_outputs = [r.parsed for r in results]
        for role, result in zip(ANALYST_ROLES, results, strict=True):
            self._require_trace_evidence(result.trace_ids, role)
        trace_ids = [tid for r in results for tid in r.trace_ids]
        self._require_trace_evidence(trace_ids, "analysts")
        await self._journal(
            ctx,
            None,
            "ANALYSTS_VALIDATED",
            "ok",
            output_snapshot={"analysts": analyst_outputs},
        )

        # 2. Debate: deterministic trigger, bounded moderator round.
        policy = ctx.policy
        debate_held = debate.should_debate(
            analyst_outputs,
            ic_confidence_threshold=float(policy.get("ic_confidence_threshold", 0.6)),
            disagreement_threshold=float(policy.get("disagreement_threshold", 0.4)),
        )
        debate_summary = ""
        if debate_held:
            dl.ensure(_IC_RESERVE_MS)
            dbg = await debate.run_debate(
                gateway=self._gateway,
                registry=self._registry,
                lineage_id=lineage_id,
                workflow_run_id=ctx.workflow_id,
                stage_run_id="debate",
                model_version_id=uuid.UUID(ctx.model_version_ids["ic_forum"]),
                idempotency_key=f"{lineage_id}:debate",
                symbol=ctx.symbol,
                decision_ts=ctx.decision_ts,
                analyst_inputs=analyst_outputs,
                session=self._session,
                spend=self._spend,
                prompt_version_id=self._prompt_version_id(ctx, "ic_forum"),
            )
            debate_summary = str(dbg.parsed.get("summary", ""))
            trace_ids.extend(dbg.trace_ids)
            self._require_trace_evidence(trace_ids, "debate_moderator")
            await self._journal(ctx, None, "DEBATE_VALIDATED", "ok")
        else:
            await self._journal(ctx, None, "DEBATE_SKIPPED", "ok")

        # 3. IC Forum (consumes original analyst outputs + debate summary).
        dl.ensure(_IC_RESERVE_MS)
        ic_result = await run_ic_forum(
            gateway=self._gateway,
            registry=self._registry,
            lineage_id=lineage_id,
            workflow_run_id=ctx.workflow_id,
            stage_run_id="ic_forum",
            model_version_id=uuid.UUID(ctx.model_version_ids["ic_forum"]),
            idempotency_key=f"{lineage_id}:ic_forum",
            symbol=ctx.symbol,
            decision_ts=ctx.decision_ts,
            analyst_inputs=analyst_outputs,
            debate_summary=debate_summary,
            session=self._session,
            spend=self._spend,
            prompt_version_id=self._prompt_version_id(ctx, "ic_forum"),
        )
        ic_output = ic_result.parsed
        trace_ids.extend(ic_result.trace_ids)
        self._require_trace_evidence(trace_ids, "ic_forum")
        await self._journal(ctx, None, "IC_VALIDATED", "ok", output_snapshot=ic_output)

        # 4. CIO Proposer; re-stamp authoritative pins afterwards.
        dl.ensure(_CIO_RESERVE_MS)
        cio_result = await run_cio_proposer(
            gateway=self._gateway,
            registry=self._registry,
            lineage_id=lineage_id,
            workflow_run_id=ctx.workflow_id,
            stage_run_id="cio_proposer",
            model_version_id=uuid.UUID(ctx.model_version_ids["cio_proposer"]),
            idempotency_key=f"{lineage_id}:cio_proposer",
            symbol=ctx.symbol,
            decision_ts=ctx.decision_ts,
            ic_output=ic_output,
            analyst_inputs=analyst_outputs,
            portfolio_context=self._portfolio_context(portfolio),
            policy_version_id=str(ctx.policy_version_id),
            model_version_ids=ctx.model_version_ids,
            prompt_version_ids=ctx.prompt_version_ids,
            debate_held=debate_held,
            trade_memory=ctx.analyst_variables.get("technical_analyst", {}).get("trade_memory", ""),
            session=self._session,
            spend=self._spend,
            prompt_version_id=self._prompt_version_id(ctx, "cio_proposer"),
        )
        proposal = cio_result.parsed
        trace_ids.extend(cio_result.trace_ids)
        proposal["model_version_ids"] = dict(ctx.model_version_ids)
        proposal["prompt_version_ids"] = dict(ctx.prompt_version_ids)
        proposal["policy_version_id"] = str(ctx.policy_version_id)
        proposal["reasoning_trace_ids"] = [str(tid) for tid in trace_ids]
        await self._journal(ctx, None, "PROPOSAL_VALIDATED", "ok", output_snapshot=proposal)

        # 5. Route by action.
        action = str(proposal["action"])
        if action in {"HOLD", "REJECT"}:
            await self._write_lineage(
                ctx,
                lineage_id,
                proposal,
                verdict="noop",
                side="NONE",
                reasons=("no_trade",),
                trace_ids=trace_ids,
            )
            await self._journal(ctx, lineage_id, "NOOP", "ok")
            return CycleResult(
                lineage_id=lineage_id,
                verdict="noop",
                action=action,
                volume=Decimal(0),
                reasons=("no_trade",),
            )

        side = "BUY" if action == "BUY" else "SELL"

        # 6. Deterministic sizing (base volume from ATR + risk budget).
        settings = self._settings
        size = calculate_size(
            entry_price=ctx.entry_price,
            atr_14=ctx.atr_14,
            equity=portfolio.equity,
            risk_per_trade=Decimal(str(settings.risk_per_trade)),
            atr_multiplier=Decimal(str(settings.default_stop_loss_atr_multiplier)),
            pip_value=Decimal(str(settings.pip_value_per_lot)),
            side=side,
            pip_size=Decimal(str(settings.pip_size)),
            min_volume=Decimal(str(settings.min_volume)),
            max_volume=Decimal(str(settings.broker_max_volume)),
        )

        # 7. Advisory LLM risk assessor → deterministic multiplier lookup.
        dl.ensure(_RISK_RESERVE_MS)
        band = volatility_band(ctx.atr_14, ctx.entry_price)
        assessor_result = await run_risk_assessor(
            gateway=self._gateway,
            registry=self._registry,
            lineage_id=lineage_id,
            workflow_run_id=ctx.workflow_id,
            stage_run_id="risk_assessor",
            model_version_id=uuid.UUID(
                ctx.model_version_ids.get("risk_officer", ctx.model_version_ids["cio_proposer"])
            ),
            idempotency_key=f"{lineage_id}:risk_assessor",
            symbol=ctx.symbol,
            decision_ts=ctx.decision_ts,
            proposal_summary=proposal,
            portfolio_context=self._portfolio_context(portfolio),
            volatility_band=band,
            trade_memory=ctx.analyst_variables.get("technical_analyst", {}).get("trade_memory", ""),
            session=self._session,
            spend=self._spend,
            prompt_version_id=self._prompt_version_id(ctx, "risk_officer"),
        )
        trace_ids.extend(assessor_result.trace_ids)
        self._require_trace_evidence(trace_ids, "risk_assessor")
        assessed = apply_assessment(
            assessment=assessor_result.parsed,
            base_volume=size.base_volume,
            risk_adjustments=policy.get("risk_adjustments", {}),
            volatility_band=band,
            min_volume=Decimal(str(settings.min_volume)),
            max_volume=Decimal(str(settings.broker_max_volume)),
        )

        # 8. Deterministic risk validation on the final notional.
        notional = assessed.final_volume * ctx.entry_price
        base_limits = ctx.risk_limits
        limits = RiskLimits(
            max_exposure_per_trade=base_limits.max_exposure_per_trade,
            max_total_exposure=base_limits.max_total_exposure,
            max_correlated_exposure=base_limits.max_correlated_exposure,
            max_daily_loss_pct=base_limits.max_daily_loss_pct,
            max_position_count=base_limits.max_position_count,
            strategy_limit=base_limits.strategy_limit,
            kill_switch=portfolio.kill_switch,
        )
        risk_verdict = assess_proposal(
            RiskInputs(
                equity=portfolio.equity,
                proposed_notional=notional,
                total_notional=portfolio.total_notional,
                correlated_notional=portfolio.correlated_notional,
                daily_pnl=portfolio.daily_pnl,
                open_positions=portfolio.open_positions,
                strategy_notional=portfolio.strategy_notional,
                proposed_is_correlated=portfolio.proposed_is_correlated,
            ),
            limits,
        )
        risk_context = {
            "per_trade_exposure": str(risk_verdict.per_trade_exposure),
            "total_exposure": str(risk_verdict.total_exposure),
            "correlated_exposure": str(risk_verdict.correlated_exposure),
            "daily_loss_pct": str(risk_verdict.daily_loss_pct),
            "violations": list(risk_verdict.violations),
            "veto": assessed.veto,
            "regime_bucket": assessed.regime_bucket,
            "risk_adjustment_multiplier": str(assessed.multiplier),
            "volatility_band": band,
            "risk_notes": assessed.risk_notes,
            "base_volume": str(size.base_volume),
            "stop_distance": str(size.stop_distance),
            "stop_price": str(size.stop_price),
        }
        reasons = list(risk_verdict.violations)
        if assessed.veto:
            reasons.append("risk_assessor_veto")
        if reasons:
            await self._write_lineage(
                ctx,
                lineage_id,
                proposal,
                verdict="rejected",
                side=side,
                size=assessed.final_volume,
                risk_context=risk_context,
                reasons=tuple(reasons),
                trace_ids=trace_ids,
            )
            await self._journal(
                ctx, lineage_id, "RISK_REJECTED", "ok", output_snapshot=risk_context
            )
            return CycleResult(
                lineage_id=lineage_id,
                verdict="rejected",
                action=action,
                volume=assessed.final_volume,
                reasons=tuple(reasons),
            )

        # 9. Lineage write BEFORE dispatch (write-before-dispatch, D3-7).
        await self._write_lineage(
            ctx,
            lineage_id,
            proposal,
            verdict="approved",
            side=side,
            size=assessed.final_volume,
            risk_context=risk_context,
            reasons=(),
            trace_ids=trace_ids,
        )

        # 10. Dispatch once through the execution router.
        command = BridgeCommand(
            command_id=f"{lineage_id}:1",
            order_id=str(lineage_id),
            action=action,
            symbol=ctx.symbol,
            volume=float(assessed.final_volume),
            order_type="market",
            stop_loss=float(size.stop_price),
        )
        tca_context = None
        if ctx.broker_id is not None and ctx.account_id is not None and ctx.pip_value is not None:
            tca_context = TcaDispatchContext(
                strategy_id=ctx.strategy_id,
                book=ctx.book,
                regime_id=ctx.regime_id,
                broker_id=ctx.broker_id,
                account_id=ctx.account_id,
                pip_value=ctx.pip_value,
                pip_size=ctx.pip_size,
                decision_ts=datetime.fromisoformat(ctx.decision_ts),
            )
        dispatched = await self._execution_router.dispatch(
            self._session,
            lineage_id=lineage_id,
            command=command,
            attempt=1,
            tca_context=tca_context,
        )
        dispatch_info = {
            "status": dispatched.status,
            "ticket": dispatched.ticket,
            "fill_price": str(dispatched.fill_price) if dispatched.fill_price is not None else None,
            "replayed": dispatched.replayed,
        }
        await self._journal(ctx, lineage_id, "DISPATCHED", "ok", output_snapshot=dispatch_info)
        return CycleResult(
            lineage_id=lineage_id,
            verdict="approved",
            action=action,
            volume=assessed.final_volume,
            reasons=(),
            dispatch=dispatch_info,
        )

    # ── stage internals ─────────────────────────────────────────────────────

    async def _run_analyst(
        self, ctx: CycleContext, lineage_id: uuid.UUID, role: str
    ) -> StageResult:
        """Run one analyst stage; role maps to its runner + prompt variables.

        Each analyst gets its own session when ``session_factory`` is
        provided, so parallel trace writes never share a live
        AsyncSession (parallel, isolated conversations).
        """
        runners = {
            "technical_analyst": run_technical_analyst,
            "macro_analyst": run_macro_analyst,
            "news_analyst": run_news_analyst,
            "smc_analyst": run_smc_analyst,
        }
        kwargs = {
            "gateway": self._gateway,
            "registry": self._registry,
            "lineage_id": lineage_id,
            "workflow_run_id": ctx.workflow_id,
            "stage_run_id": role,
            "model_version_id": uuid.UUID(ctx.model_version_ids[role]),
            "idempotency_key": f"{lineage_id}:{role}",
            "variables": ctx.analyst_variables[role],
            "spend": self._spend,
            "prompt_version_id": self._prompt_version_id(ctx, role),
        }
        if self._session_factory is None:
            return await runners[role](session=self._session, **kwargs)
        async with self._session_factory() as analyst_session:
            return await runners[role](session=analyst_session, **kwargs)

    @staticmethod
    def _portfolio_context(portfolio: PortfolioState) -> dict[str, Any]:
        return {
            "equity": str(portfolio.equity),
            "total_notional": str(portfolio.total_notional),
            "correlated_notional": str(portfolio.correlated_notional),
            "daily_pnl": str(portfolio.daily_pnl),
            "open_positions": portfolio.open_positions,
            "strategy_notional": str(portfolio.strategy_notional),
            "kill_switch": portfolio.kill_switch,
        }

    @staticmethod
    def _require_trace_evidence(trace_ids: list[uuid.UUID], stage: str) -> None:
        if trace_ids:
            return
        message = f"missing reasoning trace evidence for {stage}"
        raise LineageWriteError(message)

    async def _write_lineage(
        self,
        ctx: CycleContext,
        lineage_id: uuid.UUID,
        proposal: dict[str, Any],
        *,
        verdict: str,
        side: str,
        size: Decimal | None = None,
        risk_context: dict[str, Any] | None = None,
        reasons: tuple[str, ...] = (),
        trace_ids: list[uuid.UUID] | None = None,
    ) -> None:
        """Append the immutable lineage record (write-before-dispatch).

        The lineage INSERT and the trace/journal backfill share one
        transaction so they commit or roll back together (A3 fix). If
        the backfill fails, the lineage row is rolled back too — no
        orphan lineage record can reach dispatch, and no trace is left
        with a dangling ``lineage_id`` (D3-11).
        """
        self._require_trace_evidence(trace_ids or [], "lineage")
        risk_payload = dict(risk_context or {})
        risk_payload.setdefault("violations", list(reasons))
        # commit=False: the lineage row is flushed but not committed.
        # The single commit below owns the atomic boundary.
        await write_lineage(
            self._session,
            LineageInputs(
                lineage_id=lineage_id,
                book=ctx.book,
                strategy_id=ctx.strategy_id,
                symbol=ctx.symbol,
                side=side,
                verdict=verdict,
                size=size,
                fill_price=None,
                model_version_ids=ctx.model_version_ids,
                prompt_version_ids=ctx.prompt_version_ids,
                policy_version_id=ctx.policy_version_id,
                strategy_version_id=ctx.strategy_id,
                feature_version_id=ctx.feature_version_id,
                regime_version_id=ctx.regime_version_id,
                calendar_version_id=ctx.calendar_version_id,
                trigger={"workflow_id": ctx.workflow_id, "decision_ts": ctx.decision_ts},
                features=None,
                proposal=proposal,
                risk_context=risk_payload,
                decision_ts=datetime.now(UTC),
            ),
            commit=False,
        )
        try:
            if trace_ids:
                from sqlalchemy import update

                from lumine.data.models import (
                    ReasoningTrace,
                    WorkflowJournal,
                )

                await self._session.execute(
                    update(ReasoningTrace)
                    .where(ReasoningTrace.trace_id.in_(trace_ids))
                    .values(lineage_id=lineage_id)
                )
                # Pre-lineage journal checkpoints are linked the same way.
                await self._session.execute(
                    update(WorkflowJournal)
                    .where(WorkflowJournal.workflow_id == ctx.workflow_id)
                    .values(lineage_id=lineage_id)
                )
            await self._session.commit()
        except Exception as exc:
            # Rollback undoes both the trace/journal backfill AND the
            # lineage INSERT (flushed, not committed) — atomicity holds.
            await self._session.rollback()
            msg = (
                f"lineage backfill commit failed for {ctx.symbol} "
                f"(workflow={ctx.workflow_id}): {exc}"
            )
            raise LineageWriteError(msg) from exc


__all__ = (
    "ANALYST_ROLES",
    "CycleContext",
    "CycleResult",
    "DecisionOrchestrator",
    "PortfolioState",
    "volatility_band",
)
