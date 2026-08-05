# ADR-0031 — Strategy promotion / demotion policy with quantitative gates

- **Status:** Accepted
- **Phase:** 90-governance-and-operations
- **Date:** 2026-08-02
- **Owner:** architects
- **Supersedes:** —
- **Superseded by:** —

## Context

Phase 2 defines strategy promotion as a human CIO gate. Phase 3 defines
the status lifecycle. Neither defines the criteria the CIO applies. A
strategy enters production on undisclosed judgment — no documented rubric,
no sample-size floor, no regime coverage check, no capacity headroom test.
Without quantitative gates, a strategy that looks good on a tiny sample or
in one regime can reach production and lose capital.

## Decision

Strategy promotion to `production` is governed by quantitative gates the
CIO signs off against: minimum sample size (>= 100 OOS trades, >= 3 months
live paper), performance (Sharpe >= 1.0, max drawdown <= policy, profit
factor >= 1.3, slippage-adjusted), regime coverage (>= 20 trades per
regime bucket), and capacity check (slippage at target AUM <= alpha / 2).
The system generates a hash-pinned promotion readiness report. Demotion is
automatic for drawdown breach and sustained regime mismatch; degrade
events and eval regression trigger demotion on CIO acknowledgment. A
demoted strategy's new cycles are blocked; re-promotion requires a new
`strategy_versions` row through the full policy.

## Rationale

- The human still decides (principle #7); the decision is made against a
  documented, hash-pinned rubric — not undisclosed judgment.
- Slippage-adjusted metrics prevent a strategy that only passes on raw
  (idealized) numbers from reaching production.
- Regime coverage ensures the strategy is tested in every applicable
  regime, not just the one it performs well in.
- Automatic demotion on drawdown breach is a protective action (principle
  #10).

## Consequences

- Positive: no strategy reaches production without quantitative evidence.
- Positive: capital is protected by automatic demotion on drawdown or
  regime mismatch.
- Negative: pre-production strategies have no production pins — they use
  a synthetic parity baseline (labeled, not production evidence).
- Reversibility: a demoted strategy can be re-promoted via a new version
  row through the full policy.

## Cross-references

- Related ADRs: ADR-0019, ADR-0034, ADR-0040
- Implements principle(s): #4, #7, #10
- Affects phases: 90, 02, 13
- Source document: `../90-governance-and-operations/96-ai-governance/strategy-promotion-policy.md` (S16)
