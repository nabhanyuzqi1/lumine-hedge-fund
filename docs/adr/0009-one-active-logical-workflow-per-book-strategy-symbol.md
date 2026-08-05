# ADR-0009 — One active logical workflow per (book, strategy, symbol)

- **Status:** Accepted
- **Phase:** 07-autogen
- **Date:** 2026-08-02
- **Owner:** architects
- **Supersedes:** —
- **Superseded by:** —

## Context

Two committees deciding on the same market state concurrently produce
conflicting proposals, duplicate orders, and an unauditable decision
history. Books must be isolated from each other. Duplicate triggers
(scheduler retry, stream rewind) must be idempotent, not additive.

## Decision

At most one non-terminal run exists per (book, strategy, symbol). Duplicate
triggers are idempotent; a newer trigger may supersede a stale in-flight
run. Books are isolated from each other.

## Rationale

- Prevents two committees deciding on the same market state concurrently.
- Books are isolated by design (principle #5: books never blend).
- Idempotent triggers prevent duplicate orders from stream rewinds or
  scheduler retries.
- A newer trigger superseding a stale run avoids deadlock on a stuck
  in-flight cycle.

## Consequences

- Positive: no conflicting proposals or duplicate orders for the same key.
- Positive: book isolation enforced at the workflow layer.
- Negative: a strategy that needs parallel runs on the same symbol must
  use different books or separate strategy IDs.
- Reversibility: the invariant is structural; relaxing it requires a new
  ADR.

## Cross-references

- Related ADRs: ADR-0005
- Implements principle(s): #5, #10
- Affects phases: 07
- Source document: `../07-autogen/decisions.md` (D7-2)
