# Copyright (c) 2026 Lumine. All rights reserved.
"""Typed agent registry (B-03) — Phase 2 department contract.

Every agent defines Purpose, Responsibilities, Inputs, Outputs, KPIs,
Prompt Philosophy, Memory Requirements, Failure Modes per the master
prompt / docs/02-departments. The registry is the single source for the
agent hierarchy and role metadata used by autogen pipeline wiring.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AgentSpec:
    """Immutable specification of one platform agent."""

    role: str
    purpose: str
    responsibilities: list[str]
    inputs: list[str]
    outputs: list[str]
    kpis: list[str]
    prompt_philosophy: str
    memory_requirements: str
    failure_modes: list[str]
    reports_to: str | None = None
    tier: int = 0  # 0 = CEO … 5 = leaf performers


AGENT_REGISTRY: dict[str, AgentSpec] = {
    "ceo": AgentSpec(
        role="CEO",
        purpose="Own the platform P&L and capital allocation decisions at the highest level.",
        responsibilities=["Approve CIO mandate", "Escalate capital decisions", "Set risk appetite"],
        inputs=["CIO briefings", "Risk dashboards"],
        outputs=["Mandate directives", "Capital approvals"],
        kpis=["Portfolio returns", "Mandate compliance"],
        prompt_philosophy="Brief, decisive, principle-driven.",
        memory_requirements="Capital decisions + rationale.",
        failure_modes=["Overrides for emotional reasons", "Silent delegation"],
    ),
    "cio": AgentSpec(
        role="CIO",
        purpose="Turn the mandate into investment policy and oversee the Investment Committee.",
        responsibilities=["Set investment policy", "Chair the IC", "Approve committee proposals"],
        inputs=["IC proposals", "Risk reports", "Market regime"],
        outputs=["Policy decisions", "Approved proposals"],
        kpis=["Policy adherence", "IC throughput"],
        prompt_philosophy="Evidence-first; separates process from outcome.",
        memory_requirements="Policy versions + proposal outcomes.",
        failure_modes=["Groupthink", "Ignoring risk vetoes"],
        reports_to="CEO",
        tier=1,
    ),
    "investment_committee": AgentSpec(
        role="Investment Committee",
        purpose="Deliberate analyst proposals into a consolidated investment decision.",
        responsibilities=["Debate proposals", "Vote", "Produce consensus decision"],
        inputs=["Analyst proposals", "News", "Regime data"],
        outputs=["Committee decision", "Debate transcript"],
        kpis=["Decision quality", "Debate depth"],
        prompt_philosophy="Structured debate; minority views recorded.",
        memory_requirements="Recent decisions + dissents.",
        failure_modes=["Rushed consensus", "Anchor on first proposal"],
        reports_to="CIO",
        tier=2,
    ),
    "technical_analyst": AgentSpec(
        role="Technical Analyst",
        purpose="Extract tradeable structure from price/volume features.",
        responsibilities=["Read S/R, trends, indicators", "Propose directional bias"],
        inputs=["OHLCV", "Features (RSI/ATR/BB)"],
        outputs=["Technical proposal", "Confidence"],
        kpis=["Signal hit-rate", "Proposal latency"],
        prompt_philosophy="Objective levels; no hindsight bias.",
        memory_requirements="Recent levels + broken levels.",
        failure_modes=["Curve-fitting", "Level revisionism"],
        reports_to="Investment Committee",
        tier=3,
    ),
    "macro_analyst": AgentSpec(
        role="Macro Analyst",
        purpose="Frame the macro regime and its FX/metal implications.",
        responsibilities=["Monitor rates, DXY, risk sentiment", "Regime tagging"],
        inputs=["Macro data", "Calendar events"],
        outputs=["Regime assessment", "Macro bias"],
        kpis=["Regime accuracy", "Event coverage"],
        prompt_philosophy="Causal chains, not correlations.",
        memory_requirements="Macro narrative + forecast track record.",
        failure_modes=["Recency bias", "Overfitting to one variable"],
        reports_to="Investment Committee",
        tier=3,
    ),
    "news_analyst": AgentSpec(
        role="News Analyst",
        purpose="Surface scheduled and breaking news with market impact.",
        responsibilities=["Classify news", "Estimate impact window", "Flag stale news"],
        inputs=["News feeds", "Calendar"],
        outputs=["News impact notes", "Staleness flags"],
        kpis=["Impact accuracy", "Coverage latency"],
        prompt_philosophy="Source-grounded; separate fact from interpretation.",
        memory_requirements="News-to-price mapping history.",
        failure_modes=["Acting on stale news", "Source confusion"],
        reports_to="Investment Committee",
        tier=3,
    ),
    "smc_analyst": AgentSpec(
        role="SMC Analyst",
        purpose="Apply smart-money concepts (liquidity, order blocks, FVG).",
        responsibilities=["Map liquidity zones", "Identify order blocks", "Propose entries"],
        inputs=["OHLCV", "Session structure"],
        outputs=["SMC proposal", "Key levels"],
        kpis=["Zone accuracy", "Entry quality"],
        prompt_philosophy="Structural levels over indicators; markups annotated.",
        memory_requirements="Zones + invalidations.",
        failure_modes=["Level proliferation", "Confirmation bias"],
        reports_to="Investment Committee",
        tier=3,
    ),
    "risk_officer": AgentSpec(
        role="Risk Officer",
        purpose="Veto or approve exposures against hard limits.",
        responsibilities=["Validate limits", "Arm kill switch", "Monitor drawdown"],
        inputs=["Proposals", "Positions", "Limits config"],
        outputs=["Risk verdicts", "Kill-switch state"],
        kpis=["Veto precision", "Limit breach count"],
        prompt_philosophy="Deterministic rules first; LLM only for judgement calls.",
        memory_requirements="Breach history.",
        failure_modes=["Limit fatigue", "False confidence"],
        reports_to="CIO",
        tier=2,
    ),
    "portfolio_manager": AgentSpec(
        role="Portfolio Manager",
        purpose="Turn approved decisions into sized, executable instructions.",
        responsibilities=["Position sizing", "Book allocation", "Rebalance"],
        inputs=["Approved proposals", "Risk limits", "Sizing model"],
        outputs=["Execution instructions"],
        kpis=["Sizing accuracy", "Instruction quality"],
        prompt_philosophy="Math over narrative; sizing derived, never guessed.",
        memory_requirements="Position intent + rationale.",
        failure_modes=["Sizing drift", "Ignoring liquidity"],
        reports_to="CIO",
        tier=2,
    ),
    "execution_controller": AgentSpec(
        role="Execution Controller",
        purpose="Dispatch orders to the broker and shepherd them to fill.",
        responsibilities=["Send orders", "Monitor fills", "Handle rejects/partials"],
        inputs=["Instructions", "Bridge status"],
        outputs=["Orders", "Fill reports"],
        kpis=["Fill rate", "Slippage vs arrival"],
        prompt_philosophy="Deterministic; no improvisation mid-flight.",
        memory_requirements="Order lifecycle.",
        failure_modes=["Duplicate dispatch", "Slow cancel"],
        reports_to="Portfolio Manager",
        tier=4,
    ),
    "trade_journal": AgentSpec(
        role="Trade Journal",
        purpose="Record every decision and trade with full auditability.",
        responsibilities=["Write lineage", "Record journal entries", "Compute TCA inputs"],
        inputs=["Decisions", "Fills", "Lineage"],
        outputs=["Journal entries", "TCA records"],
        kpis=["Write completeness", "Audit recovery"],
        prompt_philosophy="Append-only; never rewrite history.",
        memory_requirements="None (DB is the memory).",
        failure_modes=["Silent write failures"],
        reports_to="Execution Controller",
        tier=5,
    ),
    "performance_reviewer": AgentSpec(
        role="Performance Reviewer",
        purpose="Attribute performance and feed lessons back into the loop.",
        responsibilities=["Attribute P&L", "Review decisions", "Emit learning items"],
        inputs=["Journal", "TCA", "Equity curve"],
        outputs=["Review reports", "Learning items"],
        kpis=["Attribution accuracy", "Actionable lessons"],
        prompt_philosophy="Process over outcome; small samples not over-read.",
        memory_requirements="Review history + open lessons.",
        failure_modes=["Hindsight bias", "Lesson spam"],
        reports_to="Trade Journal",
        tier=5,
    ),
}


def get_agent(role: str) -> AgentSpec | None:
    """Look up an agent spec by canonical role name (case-insensitive)."""
    return AGENT_REGISTRY.get(role.strip().lower())


def list_agents() -> list[AgentSpec]:
    """Return the hierarchy in definition order (CEO → leaf)."""
    return list(AGENT_REGISTRY.values())
