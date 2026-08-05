# ADR-0004 — Static tier model routing + deterministic escalation

- **Status:** Accepted
- **Phase:** 06-ai
- **Date:** 2026-08-02
- **Owner:** architects
- **Supersedes:** —
- **Superseded by:** —

## Context

Every agent role must be pinned to a default model tier so that replaying a
decision selects the same model. The Phase 3 `model_versions.tier` enum
(`cost-efficient`, `context-rich`, `strongest`) provides the vocabulary.
Escalation to a higher tier must fire on deterministic conditions, not on
dynamic LLM-router judgment, which is non-deterministic and unauditable.

## Decision

Every agent role is pinned to a default model tier recorded in
`policy_versions.routing`. Escalation to a higher tier happens only when
deterministic conditions fire (low confidence, high inter-analyst
disagreement, CIO override of IC, debate round triggered). Dynamic
LLM-router is rejected.

## Rationale

- Keeps model choice reproducible (principle #6): replay selects the same
  model.
- Dynamic router is non-deterministic and unauditable — rejected.
- Deterministic escalation conditions are auditable and replayable.
- Per-tier fallback chains (same-tier alternates, then tier down) handle
  provider failure without silent cost upgrades.

## Consequences

- Positive: model selection is fully reproducible and auditable.
- Positive: cost ceiling protected — no silent upgrades to more expensive
  tiers on failure.
- Negative: a dynamic router might save cost in edge cases; this is
  foregone until a measured need arises.
- Reversibility: routing table is policy (`policy_versions`), tunable
  without code change.

## Cross-references

- Related ADRs: ADR-0032, ADR-0036
- Implements principle(s): #6, #9
- Affects phases: 06
- Source document: `../06-ai/decisions.md` (D6-1)
