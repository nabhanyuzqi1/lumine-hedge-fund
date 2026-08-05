# Cost Alerts

- **Status:** active
- **Owner:** devops / ai-engineers
- **Last-reviewed:** 2026-08-02
- **Review-cadence:** 90

## Alerts
| Condition | Severity | Target |
|-----------|----------|--------|
| Daily spend > budget | warn | on-call |
| Daily spend > 2× budget | page | on-call + ai-engineers |
| `strongest` tier spend > tier budget | warn | ai-engineers |
| Tokens/decision > p99 baseline | warn | ai-engineers (possible context bloat — ADR-0036) |
| Research monthly cap reached | info | ai-engineers (research halts) |
| Escalation rate > baseline | warn | ai-engineers (calibration drift — ADR-0032) |

## Routing
- Alerts flow through the same observability pipeline as trading alerts
  (Phase 11). Cost alerts do NOT page the CIO unless capital is at risk.
- A cost spike with no decision-volume increase → `llm-cost-spike.md` runbook.

## Attribution check
Weekly automated check: sum of `llm_usage.cost` must reconcile to provider
invoices within tolerance. Divergence > tolerance → P1 (billing or
attribution bug).
