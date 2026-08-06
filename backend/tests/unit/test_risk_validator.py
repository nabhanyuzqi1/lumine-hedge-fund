# Copyright (c) 2026 Lumine. All rights reserved.
"""Unit tests for the deterministic risk validator (ADR-0016)."""

from __future__ import annotations

from decimal import Decimal

from lumine.trade_core.risk_validator import (
    RiskAssessment,
    RiskInputs,
    RiskLimits,
    any_reject,
    assess_proposal,
    check_kill_switch,
)

_EQUITY = Decimal(100000)


def _inputs(**overrides: object) -> RiskInputs:
    base: dict[str, object] = {
        "equity": _EQUITY,
        "proposed_notional": Decimal(1500),  # 1.5% of equity — under 2%
        "total_notional": Decimal(3000),  # book 3% + 1.5% = 4.5% < 5%
        "correlated_notional": Decimal(1000),  # 1% + 1.5% = 2.5% < 3%
        "daily_pnl": Decimal(0),
        "open_positions": 3,
        "strategy_notional": Decimal(5000),
    }
    base.update(overrides)
    return RiskInputs(**base)  # type: ignore[arg-type]


def _limits(**overrides: object) -> RiskLimits:
    base: dict[str, object] = {}
    base.update(overrides)
    return RiskLimits(**base)  # type: ignore[arg-type]


class TestPerTradeExposure:
    def test_approves_within_per_trade_cap(self) -> None:
        verdict = assess_proposal(_inputs(), _limits())
        assert verdict.approved is True
        assert verdict.violations == ()

    def test_rejects_over_per_trade_cap(self) -> None:
        verdict = assess_proposal(
            _inputs(proposed_notional=Decimal(2500)),  # 2.5% > 2%
            _limits(),
        )
        assert verdict.approved is False
        assert any(v.startswith("per_trade_exposure_exceeded") for v in verdict.violations)


class TestTotalExposure:
    def test_rejects_over_total_cap(self) -> None:
        verdict = assess_proposal(_inputs(total_notional=Decimal(50000)), _limits())
        # 50% + 1.5% = 51.5% > 5%
        assert verdict.approved is False
        assert any(v.startswith("total_exposure_exceeded") for v in verdict.violations)


class TestCorrelatedExposure:
    def test_rejects_over_correlated_cap(self) -> None:
        verdict = assess_proposal(
            _inputs(correlated_notional=Decimal(30000)),  # 30% + 1.5% > 3%
            _limits(),
        )
        assert verdict.approved is False
        assert any(v.startswith("correlated_exposure_exceeded") for v in verdict.violations)

    def test_non_correlated_proposal_ignores_own_notional(self) -> None:
        verdict = assess_proposal(
            _inputs(correlated_notional=Decimal(30000), proposed_is_correlated=False),
            _limits(),
        )
        # 30% correlated book alone still exceeds the 3% cap.
        assert verdict.approved is False

        verdict = assess_proposal(
            _inputs(correlated_notional=Decimal(2500), proposed_is_correlated=False),
            _limits(),
        )
        assert verdict.approved is True


class TestDailyLossHalt:
    def test_halt_at_or_below_daily_loss_cap(self) -> None:
        verdict = assess_proposal(_inputs(daily_pnl=Decimal(-3200)), _limits())
        assert verdict.approved is False
        assert any(v.startswith("daily_loss_halt") for v in verdict.violations)

    def test_small_loss_does_not_halt(self) -> None:
        verdict = assess_proposal(_inputs(daily_pnl=Decimal(-500)), _limits())
        assert verdict.approved is True


class TestPositionLimit:
    def test_rejects_at_position_cap(self) -> None:
        verdict = assess_proposal(_inputs(open_positions=10), _limits(max_position_count=10))
        assert verdict.approved is False
        assert any(v.startswith("position_limit_exceeded") for v in verdict.violations)


class TestKillSwitch:
    def test_kill_switch_rejects_everything(self) -> None:
        verdict = assess_proposal(_inputs(), _limits(kill_switch=True))
        assert verdict.approved is False
        assert "kill_switch_active" in verdict.violations

    def test_check_kill_switch_predicate(self) -> None:
        assert check_kill_switch(active=True) is True
        assert check_kill_switch(active=False) is False


class TestStrategyLimit:
    def test_rejects_over_strategy_book_limit(self) -> None:
        verdict = assess_proposal(
            _inputs(strategy_notional=Decimal(90000)),
            _limits(strategy_limit=Decimal("0.90")),
        )
        assert verdict.approved is False
        assert any(v.startswith("strategy_limit_exceeded") for v in verdict.violations)


class TestExposureRatios:
    def test_ratios_reported_for_lineage(self) -> None:
        verdict = assess_proposal(_inputs(), _limits())
        assert verdict.per_trade_exposure == Decimal("0.015")
        assert verdict.total_exposure == Decimal("0.045")
        assert verdict.correlated_exposure == Decimal("0.025")
        assert verdict.daily_loss_pct == Decimal(0)

    def test_zero_equity_rejected(self) -> None:
        verdict = assess_proposal(_inputs(equity=Decimal(0)), _limits())
        assert verdict.approved is False
        assert "non_positive_equity" in verdict.violations


class TestHelpers:
    def test_any_reject(self) -> None:
        ok = RiskAssessment(
            approved=True,
            violations=(),
            per_trade_exposure=Decimal(0),
            total_exposure=Decimal(0),
            correlated_exposure=Decimal(0),
            daily_loss_pct=Decimal(0),
        )
        bad = RiskAssessment(
            approved=False,
            violations=("x",),
            per_trade_exposure=Decimal(0),
            total_exposure=Decimal(0),
            correlated_exposure=Decimal(0),
            daily_loss_pct=Decimal(0),
        )
        assert any_reject([ok, bad]) is True
        assert any_reject([ok, ok]) is False

    def test_default_limits_values(self) -> None:
        limits = RiskLimits()
        assert limits.max_exposure_per_trade == Decimal("0.02")
        assert limits.max_total_exposure == Decimal("0.05")
        assert limits.strategy_limit is None
