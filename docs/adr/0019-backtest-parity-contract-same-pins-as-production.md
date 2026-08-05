# ADR-0019 — Backtest parity contract: same pins as production

- **Status:** Accepted
- **Phase:** 13-testing
- **Date:** 2026-08-02
- **Owner:** architects
- **Supersedes:** —
- **Superseded by:** —

## Context

A backtest must use the SAME version pins as production, and there is
currently no parity contract. D13-4 establishes that backtest runs the same
`execute_decision_cycle()` code path as live, with mock LLM and simulated
fills injected. Same code path is necessary but not sufficient: if the pins
differ, the backtest is simulating a different system than the one that
traded. Features recomputed inside the backtest harness risk divergence
(float order, warmup window, lookahead).

## Decision

A backtest is a sequence of comparative re-executions (D7-8) over
historical context and MUST pin identical versions as the production
period being simulated: `model_version_id`, `prompt_version_id`,
`policy_version_id`, `strategy_version_id`, `feature_version_id`. Features
MUST be read from the feature store, point-in-time correct
(`as_of_ts <= T`), never recomputed. A pin mismatch is a hard CI failure
(`pin_mismatch`). Parity score >= 0.95 is required; below is
`parity_broken` and blocks strategy promotion. Lookahead
(`as_of_ts > T`) is a hard error. Idealized-fill backtests are prohibited.

## Rationale

- Same code + same pins = same system; different pins = backtest of a
  different system, inadmissible as evidence (principle #4).
- Reading features from the store closes the silent-divergence vector.
- Lookahead prohibition is the single most important correctness property
  of a backtest.
- Slippage must be TCA-measured, not idealized — an idealized-fill
  backtest is not evidence.

## Consequences

- Positive: backtest results are admissible evidence for strategy
  promotion.
- Positive: lookahead and pin drift are caught at CI, not after deployment.
- Negative: pre-production strategies have no production pins to match —
  they use a synthetic parity baseline (labeled, not production evidence).
- Reversibility: the parity threshold (0.95) is policy; the contract is
  structural.

## Cross-references

- Related ADRs: ADR-0007, ADR-0020, ADR-0031
- Implements principle(s): #4, #6
- Affects phases: 13, 07, 03
- Source document: `../13-testing/backtest-parity-contract.md` (S7)
