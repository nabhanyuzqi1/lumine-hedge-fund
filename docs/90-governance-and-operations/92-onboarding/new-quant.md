# Onboarding — New Quant

- **Status:** active
- **Owner:** cio / architects
- **Last-reviewed:** 2026-08-02
- **Review-cadence:** 180

## Day 1
1. `91-glossary.md` (trading + architecture terms).
2. `docs/00-vision/` and `docs/02-departments/` (departments, governance).
3. `docs/03-agents-and-contracts/feature-store-contract.md` (point-in-time correctness — the #1 quant trap).
4. `docs/13-testing/backtest-parity-contract.md` (parity is non-negotiable).

## Week 1
5. `docs/03-agents-and-contracts/regime-model.md` and `market-calendar-contract.md`.
6. `docs/05-data/physical-erd.md` and `lineage-scale-and-partitioning.md`.
7. `docs/08-trading/risk-engine.md` + `risk-engine-determinism.md` (ADR-0016).
8. `docs/08-trading/tca-and-execution-quality.md` and `reconciliation.md`.
9. `docs/90-governance-and-operations/96-ai-governance/strategy-promotion-policy.md` (promotion gates).

## Quant-specific invariants
- **No lookahead bias.** Features carry `as_of_ts`; backtest may not read
  features with `as_of_ts > decision_ts` (ADR-0020).
- **Backtest pins match production.** A backtest whose pins don't match a
  production lineage row for the period is rejected (ADR-0019).
- **Parity score ≥ 0.95.** Below = investigate before trusting the backtest.
- **Slippage-adjusted Sharpe.** Strategy promotion uses TCA-adjusted metrics
  (ADR-0031, ADR-0040).

## Research sandbox
- The sandbox runs comparative re-executions (D7-8) on isolated resources
  (ADR-0026). It cannot starve production.
- A candidate strategy enters the sandbox, then faces the promotion gates,
  then the CIO signs off.
