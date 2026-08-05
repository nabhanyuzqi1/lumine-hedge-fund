# Agent Memory Policy — Stateless V1

## Overview

Decision **D6-5**: in V1 every agent call is **stateless**. The model
sees only what the current cycle's deterministic context builder puts
into the prompt: current market data, current positions, registry
versions, and the Phase 4 schemas. Nothing carried from prior cycles
except through the database.

## Why stateless

| Concern | Stateless answer |
|---------|------------------|
| Reproducibility (#6) | Replay = rebuild context from DB + registry → same prompt → same model → comparable output. Any hidden memory makes replay depend on an unrecorded state. |
| Audit (#4) | Everything the model "knew" is either in the prompt (stored in lineage) or in a versioned registry row. |
| Cost (#6 budgets) | No growing context windows; token cost per call is flat and predictable. |
| YAGNI | No vector store, no embedding pipeline, no retrieval bugs before a consumer exists. |

## What counts as "memory" and its status

| Mechanism | V1 status |
|-----------|-----------|
| DB-backed facts (positions, fills, prior lineage rows) | allowed — deterministic, auditable, fetched per cycle |
| Rolling text summary of last N decisions in prompt | **not allowed** in V1 |
| Vector/RAG retrieval over journals or research | **not allowed** in V1 |
| Few-shot examples baked into prompt file | allowed — versioned with the prompt, hash-audited |
| AutoGen intra-conversation context (one cycle's debate) | allowed — bounded to the single decision cycle, recorded in lineage |

The distinction: **intra-cycle context is fine** (it's part of the
decision and stored); **inter-cycle carry-over is not** (it's hidden
state).

## Where "learning" lives instead

Learning in V1 is **offline and human/algorithm-driven**, not
online agent memory:

1. `lineage_records` + `llm_usage` accumulate the full decision corpus.
2. The Research/Review sandbox (Phase 2) analyzes that corpus offline.
3. Improvements ship as **new versions**: new prompt file, new model
   row, new policy thresholds — all registry-versioned and hash-audited.

The system gets smarter by *version promotion*, not by agents
remembering. That keeps every behavioral change diffable and
reversible (principle #9).

## Deferred (explicit, needs own decision later)

When a concrete consumer appears (e.g. Research sandbox proves that
retrieval over past journals improves a measurable KPI), the following
may be proposed as a new decision:

- rolling-summary memory for specific roles;
- RAG over journals/research with a pinned corpus snapshot
  (retrieval input must itself be versioned to stay reproducible);
- embedding store (would join Phase 5 as new storage).

Each must answer: what is the replay story? If memory content isn't
versioned, it fails principle #6 and is rejected.

## What this document does NOT define

- The context builder's exact data selection (Phase 7 orchestration +
  Phase 14 code).
- Offline analysis methods (Research sandbox, later phases).

## Phase boundary

This document fixes the stateless policy and the learning-by-versioning
model. It does not define retrieval systems or context-building code.
