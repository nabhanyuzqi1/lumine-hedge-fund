# ADR-0026 — Comparative replay resource isolation

- **Status:** Accepted
- **Phase:** 07-autogen
- **Date:** 2026-08-02
- **Owner:** architects
- **Supersedes:** —
- **Superseded by:** —

## Context

Comparative re-execution (D7-8) is "not routable to the live decision path"
— that is LOGICAL isolation. Without RESOURCE isolation, research runs
(which may run many parallel comparative re-executions) compete with the
live pipeline for gateway slots, DB write capacity, and cost budget. A
research burst can starve production, inflate cost, and pressure the
`lineage_pending` write SLA. Logical isolation prevents data corruption
but does not prevent resource starvation.

## Decision

Research runs use PHYSICAL resource isolation: separate gateway budget
(separate provider key OR reserved token-bucket partition); priority-lane
preemption (`production_live > production_replay > research`); separate
`research` DB schema OR throttled writes below the `lineage_pending` SLA;
global `research_budget` knob (0-100%) the CIO can cut to zero; research
cannot acquire `strongest`-tier gateway budget. Isolation is physical
(separate budgets/keys), not just logical (separate `workflow_run_id`
prefix).

## Rationale

- Physical isolation is what makes logical guarantees hold under load.
- Without it, a research burst indirectly disrupts the live path by
  starving it of gateway slots.
- The `research_budget` knob gives the CIO a panic control during
  high-volatility events.
- Blocking `strongest` tier for research protects the cost ceiling (D6-4).

## Consequences

- Positive: research cannot starve or disrupt production.
- Positive: CIO can cut research to zero instantly.
- Negative: research throughput is bounded by its own budget partition.
- Reversibility: the isolation mechanism is a deployment decision (Phase
  11); the contract is structural.

## Cross-references

- Related ADRs: ADR-0007, ADR-0022
- Implements principle(s): #6, #10
- Affects phases: 07, 06, 11
- Source document: `../07-autogen/comparative-replay-isolation.md` (S18)
