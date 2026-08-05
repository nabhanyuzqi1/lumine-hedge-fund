# AI Governance

- **Status:** active
- **Owner:** cio / architects
- **Last-reviewed:** 2026-08-02
- **Review-cadence:** 90

AI governance binds the AI subsystems (models, prompts, agents, strategies)
to institutional discipline. For an AI hedge fund using LLMs for investment
decisions, this is the regulator- and LP-facing surface.

## Documents
- [`model-risk-management.md`](model-risk-management.md) — model inventory, approval, shadow period, rollback, drift (ADR-0030, SR 11-7 style).
- [`strategy-promotion-policy.md`](strategy-promotion-policy.md) — quantitative + qualitative promotion gates; demotion criteria (ADR-0031).
- [`prompt-change-policy.md`](prompt-change-policy.md) — prompt change workflow, eval gate, approval.
- [`agent-autonomy-limits.md`](agent-autonomy-limits.md) — what agents may and may not do autonomously.
- [`eval-gates.md`](eval-gates.md) — the eval gate matrix binding prompts, models, and strategies.

## Principles
- No model/prompt/strategy enters production without evidence (eval, calibration, reconciliation).
- The CIO is the model-risk approver of record; approvals are recorded immutably.
- LLMs only reason; deterministic code owns money and safety.
- Every behavioral change is a version promotion — diffable, reversible.
