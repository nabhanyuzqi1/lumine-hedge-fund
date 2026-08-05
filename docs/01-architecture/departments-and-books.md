# Departments & Strategy Books

## Overview

Lumine is organized like a real hedge fund. Each department is an independent
functional unit with clear responsibility, inputs, outputs, and suspension
authority. Departments map to zones defined in `high-level-architecture.md`.
Strategy books (intraday, swing) remain separately attributable, testable,
promotable, and suspendable per product-philosophy principle #5.

## Departments

### Research Department

- **Responsibility**: generate and validate strategy candidates.
- **Locus**: async worker (Zone 3).
- **Input**: historical data, features, hypotheses.
- **Output**: strategy candidates (sandboxed, versioned in registry).
- **Authority**: may NOT promote candidates to production.
- **Suspension**: by CIO; auto-suspend on breach.

### Market Reasoning Department (LLM)

- **Sub-roles** (AutoGen agents, detailed in Phase 4):
  - Technical Analyst
  - Macro Analyst
  - News Analyst
  - SMC (Smart Money Concept) Analyst
- **Responsibility**: interpret market conditions, propose actions.
- **Locus**: Zone 4 (LLM layer), proposer only.
- **Output**: proposed action + reasoning + confidence.
- **Authority**: no command path to MT5.

### Investment Committee / CIO Proposer (LLM)

- **Responsibility**: consolidate analyst arguments, resolve conflicts,
  produce final proposal to trade-core.
- **Locus**: Zone 4, proposer only.
- **Authority**: may NOT bypass the deterministic risk validator.

### Risk Department (deterministic)

- **Responsibility**: validate and veto LLM proposals against policy,
  exposure, and envelope.
- **Locus**: Zone 1 (critical path, synchronous).
- **Input**: proposed action, current exposure, risk policy, kill-switch flag.
- **Output**: APPROVE / REJECT / MODIFY + reason.
- **Authority**: FINAL VETO over execution (no override by any LLM).
- **Suspension**: may suspend a strategy book; CIO may override.

### Portfolio Department (deterministic)

- **Responsibility**: size calculation, book attribution.
- **Locus**: Zone 1 (critical path, synchronous).
- **Books**: INTRADAY book + SWING book (separately attributed).
- **Output**: sized order per book, attribution tag.
- **Authority**: size calculation; risk veto takes precedence.

### Execution Department (deterministic + MT5 bridge)

- **Responsibility**: route orders to MT5, track fills, reconcile.
- **Locus**: Zone 1 (router) + Zone 2 (bridge).
- **Output**: fill events, position updates, slippage tracking.
- **Authority**: order dispatch; reconnect isolated to bridge.

### Review Department (deterministic + LLM)

- **Responsibility**: post-trade attribution, drift detection, performance
  review, incident analysis.
- **Locus**: async worker (Zone 3).
- **Output**: review reports, drift flags, promotion recommendations
  (to CIO, never auto-promote).

### Governance (Human CIO)

- **Responsibility**: define mandate, production admission, emergency stop,
  restart, sandbox promotion approval.
- **Locus**: outside the system (human authority).
- **Authority**: independent kill switch, restart authorization, promotion
  gate. Cannot be bypassed by the system.

## Strategy books

Two independent books operate side by side under one MT5 account, with
separately attributed performance, risk limits, and suspension authority.

| Book | Horizon | Attribution | Risk limit | Suspension |
|------|---------|-------------|------------|------------|
| Intraday | Intra-session, flat or near-flat by session close | P&L, win rate, exposure tagged `intraday` | Independent envelope | Risk dept or CIO may suspend independently |
| Swing | Multi-day, position held across sessions | P&L, win rate, exposure tagged `swing` | Independent envelope | Risk dept or CIO may suspend independently |

Performance, risk, and capital are never blended into a single opaque
position. Each book's P&L is decomposable in the lineage store.

## Authority hierarchy

```
LLM proposer (Market Reasoning / IC / CIO)
        ↓ proposed action
Risk validator (deterministic) ── FINAL VETO
        ↓ if approved
Portfolio sizer (deterministic)
        ↓ sized order
Execution router (deterministic) ──→ MT5 bridge
        ↓ fill
Lineage store (PostgreSQL)
```

No LLM agent sits above the risk validator. No async worker sits on this
path. The CIO kill switch sits above the entire path and is read on every
tick.

## Separation guarantees

- **LLM never executes.** LLM output is data, not command.
- **Async workers never trade.** Research/review/sandbox consume streams;
  they cannot publish to `mt5.commands`.
- **Risk veto is absolute.** No component may override a REJECT.
- **Books never blend.** Attribution tags are mandatory on every order and
  fill; lineage records carry the book tag.
- **CIO authority is external.** The system cannot promote, restart, or
  bypass CIO gates.
