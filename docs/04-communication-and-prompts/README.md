# Phase 4 — Prompt Engineering & AutoGen Configuration

## Overview

Phase 4 fixes how the Market Reasoning Department (LLM committee) is
implemented in prompts and in AutoGen. It does NOT write production code
(Phase 14+) and it does NOT change risk math or execution protocol
(Phase 8), API contracts (Phase 9), or workflow recovery semantics
(Phase 7).

Phase 2 locked the committee topology and responsibilities. Phase 3 locked
the registry tables (`model_versions`, `prompt_versions`, etc.) and the
`lineage_records.proposal` JSONB column. Phase 4 now defines:

- how prompts are stored and versioned,
- how AutoGen orchestrates the adaptive-parallel committee,
- what structured schemas the analysts, IC Forum, and CIO Proposer return,
- what the final `proposal` JSONB looks like.

## Documents in this folder

| File | Purpose |
|------|---------|
| `decisions.md` | Locked Phase 4 decision log |
| `prompt-storage.md` | Prompt file layout, `prompt_ref`, and hash contract |
| `prompt-versioning.md` | Prompt registry contract, import-time hash, promotion gate, runtime loader |
| `inter-agent-message-versioning.md` | Inter-agent message schema versioning (semver registry, compatibility policy) |
| `proposal-schema.md` | JSON schemas for analyst, IC Forum, and CIO Proposer outputs |

> AutoGen orchestration topology and the deterministic debate trigger live in
> Phase 7: `../07-autogen/orchestration.md`. Phase 4 owns the *prompts and
> message schemas*; Phase 7 owns the *runtime orchestration*.

## What Phase 4 does NOT define

- Risk math, kill-switch logic, or position sizing (Phase 8).
- MT5 command protocol or bridge behavior (Phase 8).
- Workflow lifecycle, recovery, or termination semantics (Phase 7).
- API / backtest-facing contracts (Phase 9).
- Production code / SDK wiring (Phase 14+).

## Phase boundary

This phase fixes prompt and AutoGen configuration design. Implementation
(code, prompt tuning, eval datasets) belongs to later phases.
