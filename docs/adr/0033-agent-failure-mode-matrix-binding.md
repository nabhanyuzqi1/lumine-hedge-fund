# ADR-0033 — Agent failure-mode matrix binding

- **Status:** Accepted
- **Phase:** 90-governance-and-operations
- **Date:** 2026-08-02
- **Owner:** architects
- **Supersedes:** —
- **Superseded by:** —

## Context

`recovery-and-termination.md` (Phase 7) defines the failure taxonomy and
the recovery matrix at the stage level. But the CLAUDE.md requirement
that "each agent must define Failure Modes" is decorative without a
binding to agents and runbooks. An on-call engineer needs to reach for a
specific runbook when a specific agent fails with a specific code. The
matrix must be generated, CI-checked, and non-accidental — not a
documentation convention.

## Decision

Every `(agent, failure_code)` pair relevant to an agent has a binding
entry: expected cause, runbook reference, severity (`page` / `warn` /
`info`), and whether auto-recovery is allowed. The matrix is a generated
artifact from the agent registry + the Phase 7 taxonomy. CI verifies:
every agent has >= 1 failure-mode entry per relevant code, every populated
cell has a non-null `runbook_ref` resolving to an existing file, and the
matrix matches the generated output (no hand-edited drift).

## Rationale

- Makes "each agent defines Failure Modes" (CLAUDE.md) a machine-checked
  invariant, not a documentation convention.
- Per-agent severity differentiation: analyst `SCHEMA_INVALID` is `warn`
  (run lost but system safe); CIO/IC `SCHEMA_INVALID` is `page`
  (decision-critical stages cannot produce valid output).
- Deterministic agents (Risk Officer, Portfolio Manager, Execution
  Controller) do not have `TRANSIENT_PROVIDER` — the taxonomy
  distinguishes LLM-driven from deterministic agents.
- Shared entries (`KILL_SWITCH_ACTIVE`, `OPERATOR_CANCELLED`) are uniform
  across all agents — defined once at the run level.

## Consequences

- Positive: on-call engineers have a deterministic runbook for every
  (agent, code) pair.
- Positive: new agents or failure codes require a matrix update (CI
  enforces completeness).
- Negative: the matrix must be regenerated when the agent registry or
  taxonomy changes.
- Reversibility: the matrix is a generated artifact; the source of truth
  is the agent registry.

## Cross-references

- Related ADRs: ADR-0008
- Implements principle(s): #10
- Affects phases: 90, 07
- Source document: `../90-governance-and-operations/94-runbooks/agent-failure-matrix.md` (S10)
