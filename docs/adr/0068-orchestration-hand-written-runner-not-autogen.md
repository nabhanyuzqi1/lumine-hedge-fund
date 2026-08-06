# ADR-0068 — Orchestration: hand-written deterministic runner, not AutoGen

- **Status:** Accepted
- **Phase:** 15-implementation
- **Date:** 2026-08-06
- **Owner:** Chief AI Architect
- **Supersedes:** —
- **Superseded by:** —

## Context

`CLAUDE.md` lists Microsoft AutoGen as the AI Orchestration component of
the technology stack. During Sprint 3 (Decision Engine) implementation it
became clear that AutoGen's conversational group-chat model fights the
deterministic, single-turn, schema-validated stage contract that the
governing specs require:

- **D7-11 / ADR-0029** — every LLM call produces exactly one
  `reasoning_traces` row (a faithful one-row-per-call audit log).
  AutoGen's multi-turn conversational turns do not map 1:1 to a gateway
  call, so trace-per-call auditability would have to be reconstructed
  after the fact rather than enforced at the call site.
- **D3-12** — per-stage deadline reserves must be under direct control
  so a stage that overruns its budget fails fast into `DeadlineExceededError`
  rather than silently consuming the cycle's time budget.
- **ADR-0016** — the risk engine is deterministic and fail-closed; the
  orchestration layer must not inject non-deterministic conversational
  state onto the critical path (CLAUDE.md: "LLMs only for reasoning").
- **Strictness (Phase 7)** — a non-conforming output triggers exactly one
  "fix your JSON" retry that names the violation; a second failure is a
  stage failure, never a relaxed parse. AutoGen has no native hook for
  this single-shot-then-fail contract.

The decision-engine roles (the four analysts, IC Forum, CIO Proposer)
all follow one narrow pattern: load+render the prompt, build a
`RouterRequest`, call the injected `Gateway` (which owns budget,
resolution, fallback, and `llm_usage` accounting), robustly parse the
JSON, validate against the output-schema, and write a trace row.

## Decision

Multi-agent orchestration is implemented with a hand-written runner in
`backend/src/lumine/autogen_pipeline/` (`_base.run_llm_stage` for a
single stage, `orchestrator.DecisionOrchestrator` for the cycle) rather
than Microsoft AutoGen.

The runner preserves the properties the specs require:

- **Single-turn per stage** — each role is one gateway call with one
  schema-validation gate. No conversational state crosses stages.
- **Trace-per-call** — `run_llm_stage` writes one `reasoning_traces` row
  per gateway call (including a failed retry attempt), so D7-11 holds by
  construction, not reconstruction.
- **Strict retry** — exactly one schema-correction retry; a second
  failure raises `SchemaValidationError` (safe state, never a guess).
- **Direct deadline/budget control** — the orchestrator owns the
  cycle timeout and per-stage reserves (D3-12); the injected `Gateway`
  owns `BudgetDecision` per call (ADR-0016 fail-closed).
- **Dependency direction** — `autogen_pipeline` depends on `data`,
  `llm_gateway`, `prompts`, and `schemas`; `trade_core` never touches it
  (keeps `trade_core` LLM-free, per CLAUDE.md).

The module is named `autogen_pipeline/` (not e.g. `orchestration/`) to
honor the spec's module path in `docs/14-implementation/` and avoid
churning repository-structure references. The name is a path label, not
a vendor commitment.

## Rationale

- **AutoGen rejected:** its conversational group-chat abstraction
  conflicts with the single-turn, schema-validated, trace-per-call
  contract. Wrapping it to recover these guarantees would mean fighting
  the framework on every stage — more adapter code than the hand-written
  runner, with worse auditability.
- **LangGraph / other frameworks rejected for V1:** same class of
  conflict (opaque turn/state ownership). The runner is ~230 lines and
  fully under our control; introducing a framework now would add a
  dependency and an abstraction layer without removing code.
- **Revisit trigger:** if a future phase needs genuinely multi-turn
  agent behavior (e.g. a research agent that iterates on tool use), that
  is a different contract and should be evaluated against AutoGen /
  LangGraph then — with its own ADR. The decision engine is not that
  case.
- **Naming retained:** renaming the module would cascade through spec
  references and tests for no behavioral gain; the deviation is
  recorded in the deviation-log (2026-08-06).

## Consequences

- **Positive:** trace-per-call auditability is enforced at the call
  site; strict validation and fail-closed behavior are direct, not
  emulated; deadline/budget reserves are under explicit control.
- **Positive:** no third-party orchestration framework on the critical
  path — one less supply-chain and upgrade-risk surface (ADR-0053).
- **Negative:** the operator owns the runner's evolution. Multi-turn
  agent patterns, if needed later, must be added deliberately.
- **Negative:** `CLAUDE.md` stack line still names AutoGen; readers must
  consult this ADR to understand the substitution. Mitigated: deviation
  recorded in deviation-log; this ADR is the authoritative reference.
- **Reversibility:** high — the runner is a thin, well-tested layer.
  Swapping in a framework later is a localized change to
  `autogen_pipeline/`, bounded by the existing test suite (487 tests,
  including 8 Level 4 system scenarios that exercise the full cycle).

## Cross-references

- Related ADRs: ADR-0016 (deterministic risk engine, fail-closed),
  ADR-0029 (reasoning-trace audit), ADR-0053 (supply chain)
- Implements principle(s): #4 (modular, observable), #5 (LLMs only for
  reasoning), #6 (safe state by default), #8 (reproducibility)
- Affects phases: 4, 7, 15
- Source documents: `../04-communication-and-prompts/`,
  `../07-autogen/`, deviation-log entry (2026-08-06)
