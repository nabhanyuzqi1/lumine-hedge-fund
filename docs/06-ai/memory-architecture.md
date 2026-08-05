# Memory Architecture — Tier Model and Governed Evolution Path

## Overview

Decision **D6-5** (`memory-policy.md`) makes V1 stateless: every agent
call sees only what the current cycle's deterministic context builder
puts into the prompt, plus DB-backed facts fetched per cycle. That
decision is correct for V1 but, on its own, leaves the system capped at
"clever V1" forever: the deferral has no trigger condition, no tier
vocabulary, and no unblock path. This document fixes that gap.

Decision **D6-6**: memory is partitioned into four tiers with explicit
per-tier storage, versioning, replay, and reproducibility contracts.
Two tiers are **allowed in V1** (bounded); two tiers are **deferred
with trigger conditions** — deferrals are no longer ad hoc.

The invariant that governs every tier, including the deferred ones:

> **Any memory content used in a decision MUST be versioned and pinned
> in `lineage_records`. Unversioned memory is hidden state and is
> rejected (principle #6).**

This document does **not** enable memory in V1. It specifies the
governed evolution path so deferrals have a trigger, a contract, and a
rejection criterion, instead of an open "needs own decision later".

## Decision: four memory tiers

| Tier | V1 status | Storage | Bounded to |
|------|-----------|---------|------------|
| **WORKING** | allowed | in-process + lineage | one decision cycle |
| **EPISODIC** | allowed | DB-backed via `lineage_records` | fetched deterministically per cycle |
| **SEMANTIC** | deferred (trigger below) | concept graph / embeddings (future) | n/a until unblocked |
| **PROCEDURAL** | deferred (trigger below) | learned policies (future) | n/a until unblocked |

The split mirrors the cognitive-science vocabulary but is enforced as
engineering contracts, not metaphor. Each tier answers: where does it
live, how is it versioned, what is the replay story, what is the
reproducibility contract.

### Tier 1 — WORKING (intra-cycle)

**Definition.** Context that exists only within a single decision
cycle: the AutoGen intra-conversation debate, intermediate analyst
passes, the IC Forum's weighted merge, and the CIO Proposer's
synthesis. It does not persist past the cycle's terminal state.

**Storage.** In-process during the run; serialized into
`lineage_records.proposal` (Phase 3 JSONB) and into
`reasoning_traces` (Phase 7 amends Phase 3) at the blocking ACID write.
Nothing is held in a side store.

**Versioning.** The WORKING memory is itself part of the proposal
artifact. Its content is hashed via `proposal`'s JSONB serialization
and pinned by the four version UUIDs already in `lineage_records`
(model, prompt, policy, strategy). No separate WORKING-memory version
row exists — it is not separately addressable.

**Replay story.** Re-resolve the four pinned versions from the
registry, rebuild the deterministic context builder inputs from
`trigger` / `features` / `risk_context`, re-invoke the model. The
debate structure is reconstructed from the recorded proposal. The
replayed proposal is comparable to the original; byte-equality is not
required (LLM nondeterminism), but structural equality of the decision
(action, side, size, verdict) is the replay contract.

**Reproducibility contract.** WORKING memory never crosses cycle
boundaries. Any component that attempts to carry intra-cycle context
into the next cycle (e.g. an AutoGen agent instance reused across
cycles) is a defect. CI asserts agent instances are not reused across
cycles.

### Tier 2 — EPISODIC (past decisions, DB-backed)

**Definition.** Prior decisions and their outcomes, retrieved
deterministically per cycle to inform the current one. This is the
"memory" the system already has through the database — made explicit.

**Storage.** `lineage_records` (Phase 3) and the outcome tables filled
by the Review worker (Phase 2). No new store. Retrieval is a SQL query,
not a vector lookup.

**Versioning.** EPISODIC memory content is addressed by the pinned
version UUIDs already on each `lineage_records` row. When the context
builder selects "the last N decisions for this (book, strategy,
symbol)", every selected row carries its own four version pins. The
selection rule itself is part of `policy_versions` (a `context_selection`
scope), so the *which rows* question is itself versioned and pinned.

**Replay story.** Re-resolve the policy version, re-run the selection
query against the immutable `lineage_records` table, obtain the same
row set, feed the same serialized summaries into the prompt. Replay is
deterministic because the source table is append-only and the
selection rule is versioned.

**Reproducibility contract.** The set of `lineage_id`s selected as
EPISODIC memory for a decision is recorded in that decision's
`lineage_records.proposal.episodic_refs` (array of lineage_id). A
historical decision's episodic inputs are therefore re-addressable
exactly. If a selected row is later amended (it cannot be — the table
is append-only), replay diverges and the alert fires.

**V1 bound.** EPISODIC memory is allowed in V1 *only* when the
selection rule is in `policy_versions` and the selected IDs are
recorded in `proposal.episodic_refs`. Free-form "fetch whatever seems
relevant" is rejected — it is unversioned retrieval and fails #6.

### Tier 3 — SEMANTIC (concept graph / embeddings) — DEFERRED

**Definition.** A concept graph or embedding store over journals,
research notes, and analyst arguments, retrieved by similarity rather
than by deterministic SQL.

**V1 status.** Deferred. Not allowed in any production path. The
deferral is governed by the trigger below; it is not "later, maybe".

**Trigger to unblock.** SEMANTIC memory may be proposed as a new
decision (amending this document and `memory-policy.md`) only when the
Research sandbox proves, in a pinned-corpus RAG eval, that retrieval
over past journals/research improves a measurable KPI by more than a
policy-defined threshold (initial value: ≥10% relative lift on the
eval's primary metric, with the eval corpus hash-pinned and the
comparison baseline being the no-retrieval V1 system). The proof is an
artifact: `eval_suite_id` + result manifest, hash-pinned, reviewed by
the CIO.

**Storage when unblocked.** A new embeddings/concept store joins Phase
5 as additional storage. The store is **not** a second source of
truth — it is a projection of `lineage_records` and research notes,
rebuildable from them.

**Versioning when unblocked.** Every retrieval result used in a
decision is captured as a `memory_snapshot_version_id` — a registry
artifact (see "Memory as a registry artifact" below). The snapshot
records: query, retrieved IDs, retrieved content hashes, embedding
model version, corpus version. The snapshot ID is pinned in
`lineage_records`.

**Replay story when unblocked.** Re-resolve the snapshot by ID,
re-inject the exact retrieved content (verified by content hash) into
the prompt. The embedding store is not consulted at replay time — the
snapshot is the replay source. If the store drifts (re-embedding
changes vectors), replay still succeeds because the snapshot is
canonical.

**Reproducibility contract.** Retrieval without a snapshot pinned in
lineage is rejected. This is the same invariant as EPISODIC, extended
to similarity retrieval: the *what was retrieved* must be addressable
forever.

### Tier 4 — PROCEDURAL (learned policies) — DEFERRED

**Definition.** Learned policies — a model that maps state to action
distribution, trained on the decision corpus. Distinct from
SEMANTIC (which retrieves content); PROCEDURAL encodes behavior.

**V1 status.** Deferred. V1 learns by **version promotion** (D6-5):
the Research sandbox analyzes the corpus offline, improvements ship as
new registry versions. PROCEDURAL memory would replace that with
online learned behavior.

**Trigger to unblock.** PROCEDURAL memory may be proposed only when a
learned policy, trained offline in the Research sandbox, beats the
current versioned baseline on out-of-sample (OOS) data with
statistical significance: p < 0.01 on the primary OOS metric, OOS
window ≥ 3 months, sample size ≥ 100 decisions, Sharpe delta > 0. The
comparison baseline is the current production `strategy_version_id`.
The proof is hash-pinned and CIO-reviewed.

**Storage when unblocked.** A model artifact store (Phase 5 extension).
The learned policy is itself a `model_versions` row — it enters the
same registry, the same promotion gate, the same lineage pinning as
any LLM. No parallel governance track.

**Versioning when unblocked.** The policy is a `model_version_id`
pinned in `lineage_records`. Changing the policy = new row, old rows
stay pinned. This is the existing replaceability contract (principle
#9), not a new one.

**Replay story when unblocked.** Re-resolve the pinned
`model_version_id`, re-invoke the policy with the pinned
`features` snapshot. Deterministic if the policy is deterministic; if
stochastic, the RNG seed is part of the model's `params` (registry
row) and is pinned.

**Reproducibility contract.** A learned policy not registered in
`model_versions` is rejected from any production path. Online updates
to a production policy are forbidden — updates are a new row, a new
promotion, a new CIO gate.

## Memory as a registry artifact

When SEMANTIC or PROCEDURAL memory is introduced, the memory content
used in a decision is itself a registry artifact, addressed by:

```
memory_snapshot_version_id   UUID   -- FK to memory_snapshots (new registry table)
```

added to `lineage_records` alongside the existing four pins. The
`memory_snapshots` table (defined when the first deferred tier
unblocks; not pre-allocated) records: snapshot content hash, source
corpus version, retrieval/derivation method, parent snapshot if
amended. The same status lifecycle (`sandbox` → `staging` →
`production` → `retired`) applies — the CIO gate governs memory
content promotion, not just model/prompt/policy/strategy.

This closes the loophole: without `memory_snapshot_version_id`,
deferred memory would be unversioned and would violate #6. With it,
the invariant holds uniformly across all four tiers.

## The invariant, restated

Across all tiers:

| Tier | How the invariant holds |
|------|-------------------------|
| WORKING | serialized into `proposal`; pinned by the four version UUIDs |
| EPISODIC | selected `lineage_id`s recorded in `proposal.episodic_refs`; selection rule is a `policy_versions` row |
| SEMANTIC (when unblocked) | `memory_snapshot_version_id` pinned in `lineage_records` |
| PROCEDURAL (when unblocked) | learned policy is a `model_version_id` pinned in `lineage_records` |

Unversioned memory = hidden state = rejected. This is the rule that
makes the deferral governable: a proposed memory mechanism either fits
the invariant or it is rejected, regardless of the tier.

## What this document does NOT define

- The context builder's exact data selection (Phase 7 orchestration +
  Phase 14 code).
- The `memory_snapshots` table DDL — defined when a deferred tier
  unblocks, not pre-allocated.
- Embedding model selection or vector store product (Phase 5
  extension, when triggered).
- Learned-policy training methodology (Research sandbox, when
  triggered).
- Online learning — explicitly out of scope for any tier; PROCEDURAL
  is offline-trained, registry-pinned.

## Phase boundary

This document extends `memory-policy.md` (Phase 6). It does not modify
the V1 stateless decision (D6-5), the registry schema (Phase 3), or
the lineage schema (Phase 3). It defines the evolution path for the
deferred tiers and the invariant that bounds them. Code, DDL for new
tables, and embedding/policy implementation belong to Phase 14+,
gated by the triggers above.
