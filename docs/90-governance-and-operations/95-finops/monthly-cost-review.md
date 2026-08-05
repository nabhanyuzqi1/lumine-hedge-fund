# Monthly Cost Review

- **Status:** active
- **Owner:** cio / ai-engineers
- **Last-reviewed:** 2026-08-02
- **Review-cadence:** 30

## Agenda
1. Total spend vs budget; per-tier, per-book, per-strategy, per-role breakdown.
2. Tokens-per-decision trend; cost-per-decision trend.
3. Spend vs decision outcomes: did the most expensive cycles produce the
   best decisions (P&L)? Cost without outcome is noise.
4. Escalation rate and calibration health (ADR-0032).
5. Research spend vs research outcomes (promotions produced).
6. Provider mix; any provider pricing changes to absorb.

## Artifacts
- Monthly cost report (generated from `llm_usage` × `lineage_records` ×
  `reasoning_traces`), hash-pinned and archived.
- Action items: budget adjustments (policy-version promotion), prompt/model
  changes (eval-gated), research-budget changes.

## Decision tie-in
If cost-per-decision is rising without outcome improvement, the response is
a **version promotion** (cheaper tier for a role, smaller context budget,
better calibration) — never a silent quality reduction. This keeps
behavioral changes diffable and reversible (principle #9, ADR-0027).
