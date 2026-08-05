# ADR-0003 — Stateless V1 memory policy

- **Status:** Accepted
- **Phase:** 06-ai
- **Date:** 2026-08-02
- **Owner:** architects
- **Supersedes:** —
- **Superseded by:** —

## Context

V1 must guarantee pure replayability: replaying a decision with the same
pinned versions and inputs produces the same result. Persistent agent
memory (rolling summaries, RAG, vector stores) introduces hidden state that
breaks this guarantee. The `llm_usage` and `lineage_records` tables already
capture the raw material for a future memory layer; adding memory now is
YAGNI before a measured consumer exists.

## Decision

V1 agents are stateless. Each decision is computed fully from current
market data plus registry state. No rolling summaries, no RAG, no vector
store. Retrieval-augmented context re-enters as its own justified decision
when the Research/Review sandbox (Phase 2) produces a consumer.

## Rationale

- Stateless agents guarantee pure replayability (principle #6).
- `llm_usage` and `lineage_records` provide the substrate for future
  memory; no need to build it prematurely.
- Adding memory before a measured consumer exists violates YAGNI.
- Dynamic memory would make two runs with the same pins produce different
  results — unacceptable for V1.

## Consequences

- Positive: every decision is fully reproducible from pinned versions and
  inputs.
- Positive: no vector-store or RAG infrastructure to build, operate, or
  debug in V1.
- Negative: system is capped at "clever V1" until a memory tier is
  introduced (governed by ADR-0027).
- Reversibility: memory can be added later as a governed, versioned,
  lineage-pinned tier.

## Cross-references

- Related ADRs: ADR-0027
- Implements principle(s): #6, #10
- Affects phases: 06
- Source document: `../06-ai/decisions.md` (D6-5)
