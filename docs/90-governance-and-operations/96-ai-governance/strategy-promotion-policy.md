# Strategy Promotion Policy — Quantitative Gates for CIO Sign-Off

## Overview

Decision **D-GOV-2**: strategy promotion to `production` is governed
by quantitative gates the CIO signs off against. The human still
decides (principle #7, `governance-and-cross-department.md`), but the
decision is made against a documented, hash-pinned rubric — not
undisclosed judgment.

Phase 2 defines the promotion as a human CIO gate. Phase 3
(`registry-schema.md:139-148`) defines the status lifecycle. Neither
defines the *criteria* the CIO applies. This document fixes the
criteria and the demotion policy.

The invariant:

> **A strategy enters production only after passing quantitative
> gates (sample size, performance, regime coverage, OOS, capacity)
> and qualitative gates (code review, risk review, capacity check,
> prompt review). The CIO signs off on a machine-generated promotion
> readiness report that is hash-pinned and auditable.**

## Decision: quantitative gates

### Minimum sample size

| Requirement | Threshold |
|-------------|-----------|
| OOS trades | ≥ 100 |
| Live paper-trading duration | ≥ 3 months |

Both must be met; whichever is longer governs. "OOS trades" are
closed trades on out-of-sample data (defined below). A strategy with
99 OOS trades is not promotable regardless of performance.

### Performance (OOS, slippage-adjusted)

| Metric | Threshold | Notes |
|--------|-----------|-------|
| Sharpe ratio | ≥ 1.0 | Annualized, OOS |
| Max drawdown | ≤ policy `max_dd` (initial: 8%) | Ties to `policy_versions` risk envelope |
| Profit factor | ≥ 1.3 | Gross of fees, net of slippage |
| Slippage adjustment | Required | Metrics computed after applying the `backtest-paper.md` slippage model; raw (pre-slippage) metrics are not acceptable as pass evidence |

A strategy that meets Sharpe but blows drawdown is not promotable.
All four must pass. The slippage model is the pessimistic one from
`backtest-paper.md` (bid/ask spread + 0.1–0.5 pip random); a strategy
that only passes on raw metrics is not promotable.

### Regime coverage

| Requirement | Threshold |
|-------------|-----------|
| Trades per regime bucket | ≥ 20 in EACH bucket |

Regime buckets are defined by the regime model (ties to
`regime-model`). A strategy that trades 80 times in trending markets
and 5 times in ranging markets is not promotable — it is untested in
ranging conditions. Every bucket in the strategy's applicable regime
set must have ≥ 20 OOS trades.

### Out-of-sample definition

OOS period is data **not used in strategy development**. Concretely:

- The strategy's `strategy_versions.params` and `entry_rules` were
  finalized before the OOS period begins. Any parameter tuning during
  the OOS period invalidates it (it becomes in-sample).
- The OOS start date is recorded in the promotion readiness report.
- The OOS window is contiguous; cherry-picked sub-periods are not
  acceptable.
- Walk-forward OOS is acceptable if the walk-forward windows are
  pre-registered (hash-pinned before the first window runs).

The promotion readiness report includes the OOS window, the
development-sample window, and a statement that no parameter changes
occurred during OOS. The CIO verifies; the system does not police
intent.

### Capacity check

| Requirement | Threshold |
|-------------|-----------|
| Estimated slippage at target AUM | ≤ alpha / 2 |

Estimated slippage at target AUM is computed from the slippage model
scaled to the strategy's target position size. Alpha is the strategy's
expected annualized return. If slippage consumes more than half the
alpha at target AUM, the strategy has no capacity headroom and is not
promotable at that AUM. Ties to TCA (transaction cost analysis) from
the execution layer.

## Decision: qualitative gates

| Gate | Owner | Artifact |
|------|-------|----------|
| Code review | Engineering lead | PR approval record |
| Risk review | Risk Officer (deterministic layer) | Risk envelope fit report |
| Capacity check | Execution / ops | Slippage-at-AUM estimate |
| Prompt review (if LLM-driven) | CIO or delegate | Prompt-version eval pass (`ai-promotion-gates.md`) |

A strategy with deterministic rules only (no LLM in its decision
path) skips prompt review. A strategy whose entry/exit involves LLM
proposal (the default for Lumine) requires the prompt review gate.

## Decision: promotion readiness report

The system generates a **promotion readiness report** — a
machine-generated artifact the CIO signs off on. The report is
hash-pinned (SHA-256) and stored as an immutable registry artifact.
It contains:

```json
{
  "strategy_version_id": "<uuid>",
  "report_hash": "<sha256>",
  "generated_at": "<iso8601>",
  "quantitative": {
    "sample_size": {
      "oos_trades": 142,
      "live_paper_months": 3.5,
      "pass": true
    },
    "performance": {
      "sharpe_oos": 1.18,
      "max_drawdown_oos": 0.064,
      "profit_factor_oos": 1.41,
      "slippage_adjusted": true,
      "pass": true
    },
    "regime_coverage": {
      "buckets": {
        "trending": 48,
        "ranging": 31,
        "volatile": 42,
        "quiet": 21
      },
      "min_per_bucket": 20,
      "pass": true
    },
    "capacity": {
      "target_aum": 5000000,
      "est_slippage_at_aum": 0.0042,
      "alpha": 0.011,
      "slippage_alpha_ratio": 0.38,
      "pass": true
    }
  },
  "qualitative": {
    "code_review": {"reviewer": "...", "pr": "...", "pass": true},
    "risk_review": {"reviewer": "...", "pass": true},
    "capacity_check": {"reviewer": "...", "pass": true},
    "prompt_review": {"prompt_version_id": "...", "eval_pass_hash": "...", "pass": true}
  },
  "oos_window": {"start": "...", "end": "...", "development_sample_end": "..."},
  "overall_verdict": "ready_for_cio_signoff"
}
```

The CIO reviews the report, may reject it, may request changes, or
signs off. Sign-off is recorded immutably (approval record with CIO
identity, timestamp, report hash). The strategy cannot reach
`production` without a signed-off report.

## Decision: demotion policy (kill criteria)

A strategy in `production` is demoted (`status` → `demoted`; new
cycles blocked) when any of:

| Criterion | Threshold | Action |
|-----------|-----------|--------|
| Drawdown breach | Live drawdown exceeds policy `max_dd` | Immediate demotion |
| Sustained regime mismatch | ≥ N cycles (initial: 20) of underperformance in the current regime bucket, where underperformance = negative P&L net of slippage | Demotion |
| Degrade events sustained | FAILED_SAFE or degrade rate for the strategy's cycles > 2× baseline for ≥ 2 weeks | Demotion |
| Eval regression | Strategy's contribution to decision-quality eval drops below 90% of promotion-time values | Demotion (review) |

Demotion is **automatic** for drawdown breach and sustained regime
mismatch (protective action, principle #10). Demotion on degrade
events and eval regression requires CIO acknowledgment but does not
require CIO approval — it is protective.

A demoted strategy:

- Has `status` flipped to `demoted`.
- New cycles are blocked from selecting it.
- Open positions are managed per the strategy's `exit_rules` (the
  strategy is not force-closed unless the risk engine mandates it).
- The demotion event is recorded as a governance audit event with
  the trigger, threshold, and timestamp.
- The CIO is notified within the cycle.

Re-promotion requires a new `strategy_versions` row (the demoted row
stays pinned in lineage forever). The new row goes through the full
promotion policy again.

## What this document does NOT define

- Slippage model calibration (`backtest-paper.md`, Phase 13).
- Regime model definition (`regime-model`).
- TCA implementation (Phase 8 execution layer).
- Risk envelope math (`risk-engine.md`, Phase 8).
- The CIO's review UI (Phase 10 frontend).
- Code for the readiness report generator (Phase 14+).

## Phase boundary

This document is governance policy. It is consumed by:

- **Phase 2** departments: the promotion gate and demotion policy
  that the Research/Review/Sandbox loop feeds into.
- **Phase 13** testing: the eval evidence and backtest/paper metrics
  that the quantitative gates require.

It does not modify the registry schema (Phase 3), the status
lifecycle, or the CIO human gate. It adds the criteria the CIO
applies and the demotion triggers that protect capital. Code, report
generation, and demotion enforcement belong to Phase 14+.
