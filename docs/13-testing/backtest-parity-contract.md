# Backtest Parity Contract

## Overview

Finding S7: a backtest must use the SAME version pins as production,
and there is currently no parity contract. D13-4 establishes that
backtest runs the same `execute_decision_cycle()` code path as live,
with mock LLM and simulated fills injected. Same code path is
necessary but not sufficient: if the pins differ, the backtest is
simulating a *different* system than the one that traded. This
document fixes the parity contract that binds backtest to production.

Decision **D13-5**: a backtest is a sequence of comparative
re-executions (D7-8) over historical context and MUST pin identical
versions as the production period being simulated. Parity is measured
and gated.

## Decision D13-5 — Backtest parity contract

### Definition

A backtest is a sequence of comparative re-executions (D7-8) over
historical context. For each simulated decision at decision time `T`,
the backtest MUST pin:

- `model_version_id`
- `prompt_version_id`
- `policy_version_id`
- `strategy_version_id`
- `feature_version_id` (see `feature-store-contract.md`)

identical to the production `lineage_records` row for the same
`decision_ts` (or the nearest production decision for that strategy
within the cycle window). If a production row does not exist for `T`
(the strategy did not fire in production at `T`), the backtest cannot
claim parity for that decision and must mark it `unpaired`.

### Features come from the feature store

- Features in a backtest MUST be read from the feature store
  (`feature-store-contract.md`), point-in-time correct
  (`as_of_ts <= T`). They MUST NOT be recomputed inside the backtest
  harness.
- Recomputing features in the backtest risks divergence from the
  production feature computation (different float order, different
  warmup window, lookahead). The feature store is the single source
  of truth; the backtest reads the same rows production read.
- This closes the silent-divergence vector: a backtest that recomputes
  ATR with a slightly different window can look profitable while
  production loses.

### CI gate: pin match

- A backtest run declares its target production period
  (`[start_ts, end_ts]`) and the `strategy_id`.
- For every backtest decision, the harness looks up the production
  `lineage_records` row for the same `strategy_id` and `decision_ts`
  (within the cycle window). It compares the 5 pins above.
- A backtest decision whose pins do not match the corresponding
  production row is **REJECTED**. The backtest run fails CI with a
  `pin_mismatch` report listing the divergent decisions.
- This is a hard gate, not advisory. A backtest with pin mismatches
  is not a backtest of this system; it is a backtest of a different
  system and its results are not admissible as evidence (principle #4).

### Parity score

- For every paired decision (backtest decision with a matching
  production row and matching pins), compare the backtest's committee
  output (action, side, confidence band) to the production output.
- Parity score = (paired decisions with matching action) / (total
  paired decisions).
- Threshold: parity score **>= 0.95**. Below this, parity is broken
  and the backtest run is flagged `parity_broken`. The harness does
  not auto-promote or auto-reject strategy changes on a
  `parity_broken` run; it forces investigation. A `parity_broken`
  result blocks strategy promotion (Phase 13 gates).
- Note: 0.95 is not "95% as profitable." It is "95% of decisions
  produced the same action on the same inputs." Divergence above 5%
  indicates the backtest is not reproducing production behavior and
  its P&L numbers are not trustworthy.

### Lookahead-bias prohibition

- Every feature value carries `as_of_ts` (the timestamp of the latest
  data point used to compute it). A backtest decision at `T` MAY NOT
  read a feature with `as_of_ts > T`.
- This is enforced at feature-store read time: the harness queries
  `feature_values WHERE feature_version_id = ? AND as_of_ts <= T`.
  A read that would return a future `as_of_ts` is a hard error; the
  backtest aborts with `lookahead_violation`.
- This is the single most important correctness property of a
  backtest. A backtest with lookahead is not evidence of anything
  (principle #4).

### Slippage and friction

- A backtest applies TCA-measured slippage, not idealized fills. The
  slippage model is calibrated from production `fills.slippage`
  (already recorded per fill, `positions-fills-schema.md`).
- The TCA doc (planned, Phase 8/13) will define the slippage model
  parameters and their refresh cadence. Until it exists, the
  backtest uses the pessimistic model already defined in
  `backtest-paper.md` (0.1–0.5 pip random, 50–200ms latency, 5%
  partial fill, 2% rejection).
- An idealized-fill backtest (zero slippage, zero latency) is
  prohibited. A backtest that cannot show its slippage model is
  rejected at the harness config gate.

### Exemptions: pre-production strategies

- A strategy that has never run in production has no production pins
  to match. It cannot satisfy the parity contract as defined.
- Pre-production strategies use a **synthetic parity baseline**: a
  documented, versioned set of pins (`model_version_id`,
  `prompt_version_id`, `policy_version_id`, `strategy_version_id`,
  `feature_version_id`) declared as the intended production
  configuration. The backtest pins to this baseline. The baseline is
  stored alongside the strategy in `strategy_versions.params` and is
  reviewed at promotion.
- A synthetic-parity backtest is labeled as such in its report. It is
  admissible for sandbox -> staging promotion but is not evidence of
  production behavior. Once the strategy runs in production, subsequent
  backtests must use the production parity contract.
- The synthetic baseline MUST be documented in the backtest report:
  which pins, why, and when they will be superseded by production
  pins.

### Parity report artifact

Every backtest run produces a parity report (hash-pinned, stored as an
artifact):

| Field | Content |
|-------|---------|
| `backtest_run_id` | UUID |
| `strategy_id`, `strategy_version_id` | What was tested |
| `period` | `[start_ts, end_ts]` |
| `pins` | The 5 pinned version IDs |
| `paired_decisions` | Count of decisions with a matching production row |
| `unpaired_decisions` | Count without a match (marked `unpaired`) |
| `pin_mismatches` | List of divergent decisions (hard fail if non-empty) |
| `parity_score` | Fraction of paired decisions with matching action |
| `parity_status` | `pass` (>= 0.95) \| `parity_broken` (< 0.95) \| `pin_mismatch` \| `unpaired_only` |
| `slippage_model` | Version + parameters used |
| `artifact_hash` | SHA-256 of the report |

The report is the evidence artifact (principle #4). A strategy
promotion request without a passing parity report is rejected.

## Interaction with existing decisions

- **D7-8 (replay never mutates):** a backtest is a comparative
  re-execution. It writes new rows with new `workflow_run_id`; it
  never overwrites production lineage.
- **D13-4 (same code path):** this document adds the pin-parity
  contract on top of the same-code-path guarantee. Same code + same
  pins = same system.
- **Feature store (`feature-store-contract.md`):** parity depends on
  features being versioned and point-in-time correct. The
  `feature_version_id` pin closes the last divergence vector.
- **Lineage gate (Phase 3):** the production `lineage_records` row is
  the parity reference. Without lineage, there is no parity to check.

## Phase boundary

- Binds Phase 13 (testing) to Phase 7 (replay) and Phase 3 (lineage).
- The slippage/TCA model parameters are Phase 8/13 (TCA doc, planned).
- The backtest harness code is Phase 14+.
- Physical storage of parity reports is Phase 5/11.

## What this document does NOT define

- The backtest harness implementation (Phase 14+).
- The TCA/slippage model parameters (TCA doc, planned).
- The numeric parity threshold for strategies beyond V1 (may tighten).
- Strategy promotion policy beyond the parity gate (Phase 13/14).

## Phase boundary

This document fixes the backtest parity definition, the pin-match CI
gate, the parity score and threshold, the lookahead prohibition, the
slippage requirement, the pre-production synthetic-parity exemption,
and the parity report artifact. It does not define harness code
(Phase 14+), TCA parameters (Phase 8/13), or physical artifact storage
(Phase 5/11).
