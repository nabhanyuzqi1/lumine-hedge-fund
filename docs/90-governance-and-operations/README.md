# Governance & Operations

- **Status:** active
- **Owner:** architects
- **Last-reviewed:** 2026-08-02
- **Review-cadence:** 180

This tier holds **permanent operating standards** — distinct from the phase
docs (`00-15`) which are design sources. Phase docs describe how the system
was *designed*; this tier describes how the system is *operated, governed,
and contributed to*. When a phase doc and a governance doc disagree, the
governance doc is the operating standard and the phase doc is reconciled
via an ADR.

## Structure

| Folder | Purpose |
|--------|---------|
| `91-glossary.md` | Domain + system terminology (XAUUSD, SMC, IC, drawdown, fill, slippage, lineage, …). |
| `91-anti-scope-register.md` | Consolidated "V1 will NOT" list, each linked to its rejecting ADR. |
| `92-onboarding/` | Role-specific onboarding (engineer, quant, AI engineer, ops). |
| `93-standards/` | Coding, API, DB, prompt, security standards — promoted from phases as permanent references. |
| `94-runbooks/` | Operational runbooks: incident response, deployment, rollback, MT5, reconciliation, agent failures. |
| `95-finops/` | LLM budget, cost alerts, monthly cost review. |
| `96-ai-governance/` | Model approval, prompt-change policy, agent autonomy limits, model risk management, strategy promotion. |
| `97-change-management/` | RFC process, architecture review board. |
| `98-faq.md` | Frequently asked questions. |

## Maintenance

- Docs here carry frontmatter (`owner`, `last-reviewed`, `review-cadence`,
  `status`) enforced by `docs/_ci/doc-freshness-check.py`.
- Changes to governance standards require an ADR when architectural.
- Runbooks are drilled; a runbook that has never been run is a draft.
