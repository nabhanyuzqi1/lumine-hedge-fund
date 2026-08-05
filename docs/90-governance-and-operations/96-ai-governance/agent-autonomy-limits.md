# Agent Autonomy Limits

- **Status:** active
- **Owner:** cio / architects
- **Last-reviewed:** 2026-08-02
- **Review-cadence:** 90

What agents may and may not do without human (CIO) authorization. This is
the LP- and regulator-facing autonomy contract.

## Agents may autonomously
- Produce market reads, proposals, and debate within a single decision cycle.
- Escalate model tier deterministically within a cycle (ADR-0004).
- Recommend a regime bucket (the deterministic classifier is authoritative — ADR-0034).
- Veto a trade (RiskValidator final veto — deterministic).
- Write to the journal, lineage, reasoning_traces (append-only).
- Trigger the cost circuit breaker (degrade, not halt).

## Agents may NOT autonomously
- Dispatch an order that has not passed the blocking ACID lineage gate (principle #10).
- Clear or engage the kill switch (ADR-0010 — CIO authority only).
- Promote a strategy/model/prompt/feature/policy to production (CIO sign-off + gates).
- Relax a schema to coerce a malformed output (ADR-0011).
- Carry memory across cycles (V1 stateless — ADR-0027; future tiers require versioned memory).
- Execute a trade the RiskValidator rejected.
- Bypass reconciliation to reach SETTLED (ADR-0021).
- Spend beyond the cost circuit breaker without degrading.

## Boundaries
- No LLM sits above RiskValidator (`02-departments/governance-and-cross-department.md`).
- No async worker sits on the critical path.
- The CIO kill switch is read every cycle and sits above the entire path.
