# Research, Review & Sandbox Department (Async Workers)

## Overview

Three async workers run in Zone 3, off the critical path. They follow a
hybrid split by function: LLM is used only in generative / interpretive
roles; deterministic computation handles verification and execution. None of
these workers can trade.

This document fixes the worker responsibilities, the LLM/deterministic split
per worker, and the closed learning loop. It does not define prompt text,
backtest engine implementation, or code.

## Worker responsibility matrix

| Worker | LLM-driven | Deterministic | Authority |
|--------|-----------|---------------|-----------|
| Research | Generate hypothesis, design strategy candidates | Validate candidate format, register to registry | Cannot promote to production |
| Review | Interpret drift, narrative attribution | Compute attribution metrics, drift detection, performance | Cannot auto-promote; recommends to CIO |
| Sandbox | (none) | Backtest engine, replay historical, compute metrics | Cannot deploy; outputs to Review |

## Research Worker (LLM + deterministic)

```
Input:
  - historical data (PostgreSQL time-series)
  - features
  - feedback from Review worker (drift flags, performance gaps) via stream

Process:
  - LLM generates hypothesis ("strategy X drifts in high-vol regime")
  - LLM designs strategy candidate (spec + parameters)
  - Deterministic validates candidate format (schema, completeness)
  - Registers candidate to registry (versioned, status=sandbox)

Output:
  - strategy candidate (sandboxed) → Sandbox worker for backtest
  - does NOT promote to production
```

The Research worker is generative. It produces candidates; it does not
validate their real-world performance (Sandbox does) and does not promote
them (CIO does).

## Sandbox Worker (deterministic only)

```
Input:
  - strategy candidate from Research
  - historical data range

Process:
  - deterministic backtest (replay historical ticks / bars)
  - compute metrics: P&L, win rate, max drawdown, Sharpe, exposure
  - out-of-sample test (holdout period — principle #4: evidence before capital)
  - no LLM — pure computation

Output:
  - backtest result + metrics → Review worker
  - does NOT deploy
```

Sandbox is the verification gate. No LLM here means no non-determinism in the
validation step — the same candidate + data always produces the same metrics
(principle #6: reproducibility).

## Review Worker (deterministic + LLM)

```
Input:
  - decision.outcomes stream (from trade-core, live trade results)
  - backtest results from Sandbox
  - lineage records (for attribution)

Process (deterministic):
  - post-trade attribution (P&L per book, per strategy, per trigger)
  - drift detection (live vs expected, vs backtest)
  - performance metrics (win rate, slippage, execution quality)
  - flag drift / anomaly → stream

Process (LLM, interpretive):
  - narrative attribution (why strategy X underperformed)
  - generate hypothesis for Research (feedback loop)
  - promotion recommendation (to CIO, never auto-promote)

Output:
  - review reports
  - drift flags → Research worker (closed loop)
  - promotion recommendation → CIO (human gate)
```

The LLM in Review is interpretive, not authoritative. It explains drift and
proposes hypotheses; it does not decide promotion. Promotion is always a
human CIO gate (principle #7).

## Closed learning loop

```
TRADE (live)
  ↓ decision.outcomes stream
REVIEW (deterministic attribution + LLM narrative)
  ↓ drift flags + hypothesis
RESEARCH (LLM generates new candidate)
  ↓ strategy candidate
SANDBOX (deterministic backtest)
  ↓ backtest result
REVIEW (evaluates candidate)
  ↓ promotion recommendation
CIO (human gate, principle #7)
  ↓ approve
PRODUCTION (registry update, new version pinned)
```

The loop never bypasses the CIO. Promotion is a human gate, not an automated
step. Old versions stay pinned in lineage (reproducibility, principle #6).

## Async invariants (Phase 1, reaffirmed)

- Workers consume streams; they never call trade-core in-proc.
- Workers cannot publish to `mt5.commands`.
- Worker crashes are non-critical; they resume from the last consumed stream
  offset.
- Workers are low-priority: they may be throttled or paused without affecting
  trading (Phase 1 deployment policy).

## Separation guarantees

- **LLM only in generative / interpretive roles.** Research (generate) and
  Review (interpret). Sandbox is fully deterministic.
- **No worker can trade.** Stream-consuming, no command path to MT5.
- **No worker can promote.** Promotion recommendation only; CIO decides.
- **No worker on critical path.** Trading never blocks on a worker.

## Phase boundary

This document fixes the worker responsibilities, LLM/deterministic split, and
closed loop. It does not define:

- Prompt text for Research / Review LLM calls (Phase 4).
- Backtest engine implementation (Phase 9 — Research & Backtesting).
- Strategy candidate schema (Phase 3 / Phase 9).
- Attribution metric formulas (Phase 7 / Phase 9).
- Code (Phase 14+).
