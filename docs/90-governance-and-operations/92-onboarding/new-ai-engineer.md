# Onboarding — New AI Engineer

- **Status:** active
- **Owner:** ai-engineers / architects
- **Last-reviewed:** 2026-08-02
- **Review-cadence:** 180

## Day 1
1. `91-glossary.md` (AI/LLM + architecture terms).
2. `docs/06-ai/` — all of it: model-routing, llm-gateway, cost-control,
   memory-policy, memory-architecture, model-registry, gateway-admission-control,
   confidence-calibration, context-budget-policy.
3. `docs/04-communication-and-prompts/` — prompt-storage, proposal-schema,
   inter-agent-message-versioning.
4. `docs/07-autogen/` — workflow-lifecycle, recovery-and-termination,
   checkpoint-and-replay, observability, reasoning-trace-storage,
   deadline-propagation.

## Week 1
5. `docs/12-security/prompt-injection-defense.md` (ADR-0018) — untrusted-input boundary.
6. `docs/13-testing/ai-testing.md` and `ai-promotion-gates.md` (ADR-0028).
7. `docs/90-governance-and-operations/96-ai-governance/model-risk-management.md` (ADR-0030).
8. `docs/06-ai/confidence-calibration.md` (ADR-0032) — escalation uses calibrated confidence.

## AI-specific invariants
- **Prompts are versioned, hashed, auditable** (ADR-0015, CLAUDE.md rule 10).
- **No prompt ships without a passing eval** (ADR-0028). The promotion API
  refuses to flip a prompt to `production` without `eval_pass_hash`.
- **LLMs only reason.** Sizing, risk limits, execution are deterministic.
  The LLM risk role is advisory; the multiplier is a registry lookup (ADR-0016).
- **Stateless V1.** No inter-cycle memory unless versioned and pinned (ADR-0027).
- **Reproducibility.** Same pins → same prompt → comparable output. The full
  prompt actually sent is stored in `reasoning_traces` (ADR-0029).
- **News is untrusted input.** Structured extraction, instruction hierarchy,
  and output validation (ADR-0018).

## Prompt change workflow
1. Edit `backend/src/lumine/prompts/templates/{agent}@v{n}.prompt`.
2. Run `make eval` — must pass for the target model_version.
3. Register new `prompt_versions` row with `eval_suite_id` + `eval_pass_hash`.
4. Promotion API flips status → `production` only if eval passes.
5. ADR if the change is architectural; deviation-log entry otherwise.
