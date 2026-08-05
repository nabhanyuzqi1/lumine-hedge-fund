# Runbook — Incident Response

- **Status:** active · **Drilled:** no
- **Owner:** devops / cio
- **Last-reviewed:** 2026-08-02
- **Review-cadence:** 90

## Triage
1. Classify severity (see runbooks README table). When in doubt, page P1.
2. Identify the affected surface (trading / data / AI / infra / audit).
3. Engage the right runbook (MT5, reconciliation, agent-failure-matrix,
   chain-verification, llm-cost-spike).

## Capital-protecting first actions (P0)
1. If capital is at risk: engage the kill switch (CIO authority). This
   terminates active runs at the next LLM call boundary (ADR-0010).
2. Do NOT attempt autonomous recovery. The kill switch does not auto-clear.
3. Notify the CIO. Record the activation in the journal
   (`actor=operator` or `actor=kill-switch`).

## Communication
- P0: notify CIO within 5 min; stakeholders within 30 min.
- P1: notify on-call lead; stakeholders within 2h.
- Use the incident channel; one incident = one thread.

## Resolution
1. Apply the surface-specific runbook.
2. Verify recovery via health checks (`make` health target, when added)
   and a passing reconciliation.
3. For audit-integrity incidents (chain break), do NOT resume trading
   until the chain is verified and the cause is known.

## Post-incident
- Post-mortem within 48h: timeline, cause, action items, ADR if architectural.
- Add to `deviation-log.md` if it changed a spec.
- Update the relevant runbook; mark drilled if the incident validated it.
