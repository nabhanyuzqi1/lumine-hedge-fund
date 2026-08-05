# Phase 6 — AI & LLM Strategy

## Overview

Phase 4 already locked *how the committee talks* (prompt storage, AutoGen
orchestration, proposal schemas). Phase 6 locks *which model each role
uses, how routing and escalation work, how cost is bounded, and what
memory agents are allowed to have* — the parts the phase-mapping marks
as only partially covered.

Inputs: Phase 2 (committee roles, authority), Phase 3 (`model_versions`,
`prompt_versions`, `policy_versions` registries), Phase 4 (schemas +
orchestration). This phase adds the policy layer on top and introduces
the `llm_usage` accounting table (D6-7).

## Documents in this folder

| File | Purpose |
|------|---------|
| `decisions.md` | Locked Phase 6 decision log |
| `model-routing.md` | Static tier assignment per role + deterministic escalation |
| `llm-gateway.md` | 9router gateway role, model resolution, fallback rules |
| `cost-control.md` | Daily budget, circuit breaker, degrade policy, accounting |
| `memory-policy.md` | Stateless V1 policy; what agents may and may not carry |
| `model-registry.md` | How `model_versions` rows are curated, promoted, retired |

## What Phase 6 does NOT define

- Prompt contents themselves (Phase 4 + prompt files).
- AutoGen workflow recovery / observability (Phase 7).
- Model fine-tuning or training (explicitly out of scope — V1 is
  inference-only via 9router).
- LLM cost dashboard UI (Phase 10).
- Code / SDK wiring (Phase 14+).

## Phase boundary

Phase 6 fixes routing, gateway, cost, memory, and registry policy.
It does not change prompts, orchestration topology, risk math, or
execution protocol.
