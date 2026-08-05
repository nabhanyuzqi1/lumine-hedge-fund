# FinOps — LLM Cost Management

- **Status:** active
- **Owner:** ai-engineers / cio
- **Last-reviewed:** 2026-08-02
- **Review-cadence:** 90

The LLM gateway is the largest variable cost surface and the easiest place
for runaway spend. FinOps here means: budgets, alerts, attribution, and a
monthly review that ties spend to decision outcomes.

- [`llm-budget.md`](llm-budget.md) — per-tier, per-role, per-book budgets and the kill-switch-adjacent cost circuit breaker.
- [`cost-alerts.md`](cost-alerts.md) — alert thresholds and routing.
- [`monthly-cost-review.md`](monthly-cost-review.md) — monthly review tying `llm_usage` to decision KPIs.

## Attribution
Every token is attributed via `llm_usage` (Phase 6) joined to
`lineage_records` (Phase 3) and `reasoning_traces` (ADR-0029). Spend is
attributable to: book, strategy, agent role, model version, tier, and
decision outcome (P&L). No orphan tokens.
