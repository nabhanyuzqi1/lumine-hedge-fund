# Runbook — Agent Stuck in Loop (P1)

- **Status:** active · **Drilled:** no
- **Owner:** ai-engineers
- **Last-reviewed:** 2026-08-02
- **Review-cadence:** 90

## Symptoms
- Repeated `FAILED_SAFE` or `ABORTED_STALE` for the same `(book, strategy, symbol)`.
- `CONTEXT_STALE` cluster (recovery-and-termination.md alert).
- A run keeps superseding its predecessor without producing a proposal.

## Steps
1. Identify the failing stage from the journal (`failure_code` + `stage_run_id`).
2. Consult `agent-failure-matrix.md` for the (agent, failure_code) action.
3. Common causes:
   - `SCHEMA_INVALID` repeated → prompt/model regression; roll back the
     prompt/model version (rollback-runbook). Eval gate should have caught
     this (ADR-0028) — investigate the gate.
   - `CONTEXT_STALE` cluster → market-data feed stale or cycle latency too
     high; check the feature store freshness and deadline propagation
     (ADR-0039).
   - `VERSION_MISMATCH` repeated → a promotion broke in-flight runs; check
     the supersession compatibility edges (ADR-0025).
4. If the loop can't be broken: engage the kill switch for that
   (book, strategy) (CIO authority). Other books continue (ADR-0009).
5. Post-mortem; add the failure mode to the agent-failure-matrix if new.

## Never
- Never relax a schema to break the loop (ADR-0011).
- Never auto-clear a kill switch (ADR-0010).
