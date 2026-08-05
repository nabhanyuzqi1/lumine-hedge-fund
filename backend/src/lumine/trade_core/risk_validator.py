# Copyright (c) 2026 Lumine. All rights reserved.
"""Deterministic risk validation (ADR-0016, Phase 8 risk engine).

The validator is pure arithmetic-free-of-Gateway/LLM: it takes a
proposal's notional plus the current book state and returns an
``approved`` verdict with a list of violations. It implements:

- per-trade exposure cap (default 2% of equity),
- total book exposure cap (5%),
- correlated exposure cap (3%),
- daily-loss halt (3%),
- open-position count cap,
- strategy-book limit,
- kill-switch guard.

Any violation rejects the proposal. The pipeline raises
``RiskRejectionError`` only when the verdict says reject — the validator
itself stays side-effect free and fully unit-testable.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence


@dataclass(frozen=True)
class RiskLimits:
    """Limit configuration. Expressed as fractions of equity."""

    max_exposure_per_trade: Decimal = Decimal("0.02")
    max_total_exposure: Decimal = Decimal("0.05")
    max_correlated_exposure: Decimal = Decimal("0.03")
    max_daily_loss_pct: Decimal = Decimal("0.03")
    max_position_count: int = 10
    strategy_limit: Decimal | None = None
    kill_switch: bool = False


@dataclass(frozen=True)
class RiskInputs:
    """Snapshot of the current book plus the proposed trade."""

    equity: Decimal
    proposed_notional: Decimal
    total_notional: Decimal
    correlated_notional: Decimal
    daily_pnl: Decimal
    open_positions: int
    strategy_notional: Decimal
    proposed_is_correlated: bool = True


@dataclass(frozen=True)
class RiskAssessment:
    """Verdict plus the exposure ratios that led to it (for lineage)."""

    approved: bool
    violations: tuple[str, ...]
    per_trade_exposure: Decimal
    total_exposure: Decimal
    correlated_exposure: Decimal
    daily_loss_pct: Decimal


def _ratio(numerator: Decimal, equity: Decimal) -> Decimal:
    if equity <= 0:
        return Decimal(0)
    return numerator / equity


def assess_proposal(
    inputs: RiskInputs,
    limits: RiskLimits,
) -> RiskAssessment:
    """Evaluate ``inputs`` against ``limits`` and return a verdict.

    ``approved`` is ``True`` iff there are no violations. Violations are
    collected (not first-fail) so the operator sees every reason.
    """
    violation: list[str] = []

    equity = inputs.equity
    if equity <= 0:
        violation.append("non_positive_equity")
    per_trade = _ratio(inputs.proposed_notional, equity)
    total = _ratio(inputs.total_notional + inputs.proposed_notional, equity)

    correlated_base = (
        inputs.correlated_notional + inputs.proposed_notional
        if inputs.proposed_is_correlated
        else inputs.correlated_notional
    )
    correlated = _ratio(correlated_base, equity)

    daily_loss = _ratio(inputs.daily_pnl, equity)

    if limits.kill_switch:
        violation.append("kill_switch_active")
    if per_trade > limits.max_exposure_per_trade:
        violation.append(f"per_trade_exposure_exceeded:{per_trade:.6f}")
    if total > limits.max_total_exposure:
        violation.append(f"total_exposure_exceeded:{total:.6f}")
    if correlated > limits.max_correlated_exposure:
        violation.append(f"correlated_exposure_exceeded:{correlated:.6f}")
    if daily_loss <= -limits.max_daily_loss_pct:
        violation.append(f"daily_loss_halt:{daily_loss:.6f}")
    if inputs.open_positions >= limits.max_position_count:
        violation.append(f"position_limit_exceeded:{inputs.open_positions}")
    if limits.strategy_limit is not None:
        strategy = _ratio(inputs.strategy_notional + inputs.proposed_notional, equity)
        if strategy > limits.strategy_limit:
            violation.append(f"strategy_limit_exceeded:{strategy:.6f}")

    return RiskAssessment(
        approved=not violation,
        violations=tuple(violation),
        per_trade_exposure=per_trade,
        total_exposure=total,
        correlated_exposure=correlated,
        daily_loss_pct=daily_loss,
    )


def check_kill_switch(*, active: bool) -> bool:
    """Return ``True`` when trading must halt.

    Kept as a distinct predicate so orchestrators can consult the live
    flag before building proposals, not only at validation time.
    """
    return active


def any_reject(assessments: Sequence[RiskAssessment]) -> bool:
    """Return True if any assessment in ``assessments`` rejected its proposal."""
    return any(assessment.approved is False for assessment in assessments)


__all__ = (
    "RiskAssessment",
    "RiskInputs",
    "RiskLimits",
    "any_reject",
    "assess_proposal",
    "check_kill_switch",
)
