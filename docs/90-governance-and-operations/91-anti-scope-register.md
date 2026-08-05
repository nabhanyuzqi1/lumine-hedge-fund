# Anti-Scope Register — what V1 will NOT do

- **Status:** active
- **Owner:** architects / cio
- **Last-reviewed:** 2026-08-02
- **Review-cadence:** 180

Consolidates every "V1 will NOT" decision so scope creep is caught at PR
review. Each entry links to the ADR that rejected it. Reintroducing a
rejected feature requires superseding the ADR.

## Out of scope for V1

| Rejected feature / capability | Reason | ADR |
|-------------------------------|--------|-----|
| Multi-tenant isolation | Single-operator VPS deployment | ADR-0001 |
| Compliance enforcement (SOC 2 / ISO 27001) | No V1 compliance requirement | ADR-0001 |
| Sophisticated DDoS mitigation | Single-node VPS; not a V1 threat | ADR-0001 |
| Physical-access threat modeling | Cloud VPS | ADR-0001 |
| Insider-attack threat modeling | Single operator | ADR-0001 |
| Agent inter-cycle memory (rolling summary, RAG) | Violates reproducibility (#6) unless versioned; deferred with trigger | ADR-0027 |
| Embedding store / vector DB | No consumer yet; deferred until Research proves KPI lift | ADR-0027 |
| Learned policies (procedural memory) | Deferred until a learned policy beats baseline OOS with significance | ADR-0027 |
| Dynamic LLM router ("ask a model which model to use") | Breaks reproducibility | ADR-0004 |
| LLM continuous sizing multiplier | Non-deterministic input on critical path | ADR-0016 |
| Schema relaxation to coerce malformed LLM output | Malformed decision worse than no decision | ADR-0011 |
| Autonomous kill-switch restart | Only CIO/human may clear | ADR-0010 |
| In-place replay output swap | Replay never mutates history | ADR-0007 |
| De-escalation mid-cycle | Tiers only move up within a cycle | ADR-0004 |
| Multi-broker *execution* (multiple live brokers) | Schema is multi-broker-ready; V1 ships one MT5 adapter | ADR-0024 |
| Frontend code before Phase 14 approval | CLAUDE.md rule 3 | ADR-0042 |

## How to use this register

- PR review: if a PR introduces a feature listed here, block it and
  request an ADR superseding the rejecting entry.
- Quarter review: re-affirm or supersede entries. The deferral triggers
  (ADR-0027) are the primary mechanism for moving items off this list.
