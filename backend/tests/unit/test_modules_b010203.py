# Copyright (c) 2026 Lumine. All rights reserved.
"""Unit tests for B-01/B-02/B-03 modules (backtest, monitoring, registry)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from lumine.backtest.engine import run_backtest
from lumine.monitoring.metrics import MetricsRegistry
from lumine.registry.agents import get_agent, list_agents


class TestBacktestEngine:
    def test_run_is_deterministic(self) -> None:
        first = run_backtest("XAUUSD", "1h")
        second = run_backtest("XAUUSD", "1h")
        assert first.equity == second.equity
        assert [t.entry_price for t in first.trades] == [t.entry_price for t in second.trades]

    def test_metrics_are_computed(self) -> None:
        result = run_backtest("EURUSD", "1h")
        assert result.metrics is not None
        assert result.metrics.trade_count >= 0
        assert isinstance(result.metrics.total_return_pct, Decimal)
        assert result.metrics.max_drawdown_pct <= 0

    def test_equity_starts_at_100k(self) -> None:
        result = run_backtest("XAUUSD", "4h")
        assert result.equity[0] == Decimal("100000")


class TestMetricsRegistry:
    def test_counter_and_gauge(self) -> None:
        registry = MetricsRegistry()
        registry.inc("requests_total")
        registry.inc("requests_total", 4)
        registry.set_gauge("connections", 3)
        assert registry.snapshot()["requests_total"] == 5
        assert registry.snapshot()["connections"] == 3

    def test_prometheus_text_format(self) -> None:
        registry = MetricsRegistry()
        registry.inc("requests_total")
        registry.set_gauge("connections", 2)
        text = registry.render_prometheus()
        assert "# TYPE requests_total counter" in text
        assert "requests_total 1" in text
        assert "# TYPE connections gauge" in text
        assert text.endswith("\n")


class TestAgentRegistry:
    def test_hierarchy_contains_all_roles(self) -> None:
        roles = {agent.role for agent in list_agents()}
        expected = {
            "CEO",
            "CIO",
            "Investment Committee",
            "Technical Analyst",
            "Macro Analyst",
            "News Analyst",
            "SMC Analyst",
            "Risk Officer",
            "Portfolio Manager",
            "Execution Controller",
            "Trade Journal",
            "Performance Reviewer",
        }
        assert roles == expected

    def test_lookup_case_insensitive(self) -> None:
        assert get_agent("risk_officer") is not None
        assert get_agent("RISK_OFFICER") is not None
        assert get_agent("nobody") is None

    def test_agent_spec_has_full_contract(self) -> None:
        for agent in list_agents():
            assert agent.purpose
            assert agent.responsibilities
            assert agent.inputs
            assert agent.outputs
            assert agent.kpis
            assert agent.prompt_philosophy
            assert agent.memory_requirements
            assert agent.failure_modes
