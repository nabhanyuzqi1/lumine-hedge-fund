# ADR-0022 — LLM gateway admission control with priority lanes

- **Status:** Accepted
- **Phase:** 06-ai
- **Date:** 2026-08-02
- **Owner:** architects
- **Supersedes:** —
- **Superseded by:** —

## Context

Multi-asset scale (hundreds of concurrent cycles × ~6 LLM calls each) hits
provider rate-limits, triggers retry amplification, and starves the live
decision pipeline. Without admission control, parallel callers each
independently backing off amplify load by factor N. Research traffic can
starve production. The gateway needs a contract that bounds dispatch,
protects the live path, and prevents retry storms.

## Decision

The LLM gateway enforces an admission control layer: (a) global semaphore
per tier caps concurrent in-flight calls; (b) token-bucket per provider
account bounds request rate to MEASURED provider limits; (c) priority
lanes `production_live > production_replay > research` with preemption;
(d) bounded queue depth per lane, overflow returns
`ADMISSION_REJECTED` (distinct from `TRANSIENT_PROVIDER`); (e)
backpressure signal to the scheduler; (f) retry de-amplification via
jittered exponential backoff bounded by the token-bucket.

## Rationale

- Per-tier semaphore prevents any single tier from saturating the gateway.
- Token-bucket synchronized to provider `429`/`Retry-After` prevents retry
  storms — all callers coordinate through the bucket.
- Priority lanes guarantee the live decision path is never blocked behind
  research traffic.
- `ADMISSION_REJECTED` is distinct from `TRANSIENT_PROVIDER` — treating it
  as a provider error would waste a different provider's budget.

## Consequences

- Positive: live pipeline is never starved by research or retry storms.
- Positive: provider rate limits are respected without manual tuning.
- Negative: research calls may be preempted or rejected (by design).
- Reversibility: bounds are policy (`policy_versions.gateway.admission`),
  tunable without code change.

## Cross-references

- Related ADRs: ADR-0026, ADR-0004
- Implements principle(s): #6, #9, #10
- Affects phases: 06, 07
- Source document: `../06-ai/gateway-admission-control.md` (S5)
