# ADR-0027 — Four-tier memory architecture with governed deferral triggers

- **Status:** Accepted
- **Phase:** 06-ai
- **Date:** 2026-08-02
- **Owner:** architects
- **Supersedes:** —
- **Superseded by:** —

## Context

D6-5 makes V1 stateless: every agent call sees only what the current
cycle's deterministic context builder puts into the prompt, plus DB-backed
facts fetched per cycle. That decision is correct for V1 but, on its own,
leaves the system capped at "clever V1" forever: the deferral has no
trigger condition, no tier vocabulary, and no unblock path. The invariant
that governs every tier, including deferred ones: any memory content used
in a decision MUST be versioned and pinned in `lineage_records`.
Unversioned memory is hidden state and is rejected (principle #6).

## Decision

Memory is partitioned into four tiers: WORKING (intra-cycle, allowed in
V1), EPISODIC (DB-backed past decisions, allowed in V1 when selection rule
is versioned), SEMANTIC (concept graph / embeddings, deferred with
trigger), PROCEDURAL (learned policies, deferred with trigger). Two tiers
are allowed in V1 (bounded); two are deferred with explicit trigger
conditions — deferrals are no longer ad hoc. SEMANTIC unblocks when a
pinned-corpus RAG eval proves >=10% relative lift. PROCEDURAL unblocks
when a learned policy beats the versioned baseline out-of-sample with
statistical significance (p < 0.01, OOS >= 3 months, n >= 100, Sharpe
delta > 0).

## Rationale

- The four-tier split mirrors cognitive-science vocabulary but is enforced
  as engineering contracts, not metaphor.
- WORKING memory is part of the proposal artifact, pinned by the four
  version UUIDs — no separate versioning needed.
- EPISODIC memory is allowed in V1 only when the selection rule is in
  `policy_versions` and selected IDs are recorded in
  `proposal.episodic_refs`.
- Deferred tiers have explicit triggers, not open "needs own decision
  later" — the deferral is governed.
- Unversioned memory = hidden state = rejected, uniformly across all
  tiers.

## Consequences

- Positive: V1 stays stateless while the evolution path is specified and
  governed.
- Positive: deferred tiers cannot silently appear — they require pinned
  eval evidence and CIO review.
- Negative: the system is bounded at "clever V1" until a trigger fires.
- Reversibility: each tier's contract is additive; no tier modifies the
  V1 stateless decision (D6-5).

## Cross-references

- Related ADRs: ADR-0003, ADR-0030
- Implements principle(s): #6, #9
- Affects phases: 06, 03
- Source document: `../06-ai/memory-architecture.md` (S4)
