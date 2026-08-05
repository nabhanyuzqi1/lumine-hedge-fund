# ADR-0036 — Per-role, per-tier context-window budget with deterministic truncation

- **Status:** Accepted
- **Phase:** 06-ai
- **Date:** 2026-08-02
- **Owner:** architects
- **Supersedes:** —
- **Superseded by:** —

## Context

`memory-policy.md` fixes the stateless V1 contract: the context builder
assembles each prompt from DB + registry per cycle. It does not bound the
assembled prompt against the model's context window. Rich feature
snapshots, extended journal context, and news payloads will silently
overflow a cost-efficient model's 8k window — and silent truncation by the
gateway is a reproducibility bug, because two runs with the same pinned
versions can produce different prompts if the gateway's truncation is
nondeterministic or unlogged.

## Decision

Every agent call resolves a `(sub_role, model_tier)` pair and fetches a
token budget for that pair from `policy_versions` scope `context_budget`.
The context builder assembles content in three prioritized layers:
MUST_HAVE (never dropped), NICE_TO_HAVE (dropped second, oldest-first),
OPTIONAL (dropped first, oldest-first). Truncation is deterministic given
the same inputs and budget. If MUST_HAVE alone exceeds budget, the call
fails safe (`context_budget_exceeded`). The full prompt actually sent is
stored in `reasoning_traces` with its SHA-256 hash contributing to lineage.
A near-budget alert (within 10%) signals design pressure.

## Rationale

- A budget per `(sub_role, model_tier)` pair prevents silent overflow.
- Deterministic truncation order makes two runs with the same pins produce
  the same truncated prompt (principle #6).
- Storing the full prompt + hash in `reasoning_traces` closes the
  silent-truncation reproducibility hole.
- MUST_HAVE exceeding budget is a design error, not a runtime truncation —
  fails safe (principle #10).

## Consequences

- Positive: no silent truncation — the prompt the model sees is the prompt
  in the record.
- Positive: near-budget alerts provide design pressure to shrink prompts
  or bump tiers.
- Negative: a prompt that grows beyond its tier's budget fails safe
  (intentional).
- Reversibility: budgets are policy (`policy_versions`), tunable without
  code change.

## Cross-references

- Related ADRs: ADR-0029, ADR-0003
- Implements principle(s): #6, #10
- Affects phases: 06, 07
- Source document: `../06-ai/context-budget-policy.md` (S15)
