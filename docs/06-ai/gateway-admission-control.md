# Gateway Admission Control

## Overview

Decision **D6-8**: the LLM gateway enforces an admission control layer
in front of every provider call. Without it, multi-asset scale
(hundreds of concurrent cycles × ~6 LLM calls each) hits provider
rate-limits, triggers retry amplification, and starves the live
decision pipeline. This document fixes the admission contract the
Phase 7 scheduler consumes.

This document amends `llm-gateway.md` (Phase 6). It does not redefine
routing tiers, fallback chains, or retry semantics — it bounds them.

## Decision(s)

- **D6-8a** — Global semaphore per tier caps concurrent in-flight
  gateway calls.
- **D6-8b** — Token-bucket per provider account bounds request rate
  to MEASURED provider limits, never guessed.
- **D6-8c** — Priority lanes: `production_live > production_replay >
  research`. Lower-priority calls are preempted (queued) when a
  higher-priority call is waiting.
- **D6-8d** — Bounded queue depth per lane; overflow returns
  `ADMISSION_REJECTED` (distinct from `TRANSIENT_PROVIDER`).
- **D6-8e** — Backpressure: the scheduler does not trigger new cycles
  when available budget falls below threshold.
- **D6-8f** — Retry de-amplification: gateway retries use jittered
  exponential backoff bounded by the token-bucket, never exceeding
  provider rate.
- **D6-8g** — Observability metrics exposed for every admission
  outcome.

## (a) Global semaphore per tier

Concurrent in-flight calls per tier are capped. Default bounds (tunable
via `policy_versions.gateway.admission`):

| Tier | Max concurrent | Rationale |
|------|----------------|-----------|
| `cost-efficient` | 20 | bulk analyst traffic; highest fan-out (4 analysts × N cycles) |
| `context-rich` | 8 | IC/CIO run once per cycle; lower volume, higher value |
| `strongest` | 2 | escalation-only; protect cost ceiling (D6-4) |

A call acquires a tier slot before dispatch and releases it on response
or failure. If no slot is available, the call enters the lane queue
(D6-8d) rather than dispatching immediately.

Bounds are tunable, not hardcoded in code — they live in
`policy_versions` and are resolved at runtime (principle #9).

## (b) Token-bucket per provider account

Each provider account (one row in the gateway's internal account map,
keyed by `(provider, credential_set)`) owns a token bucket. Refill
rate is derived from **MEASURED** provider rate limits (RPM/TPM
observed in `llm_usage` and provider headers), not guessed defaults.

Bucket parameters:

| Field | Source |
|-------|--------|
| `capacity` | measured burst tolerance (provider docs + observed 429 headers) |
| `refill_rate_per_sec` | measured sustained RPM / 60 |
| `tokens_per_call` | max output tokens for the call's role (from `model_versions.config`) |

A call that would take the bucket negative is queued in its lane, not
dispatched. This is what prevents retry amplification: a rate-limited
provider cannot be hammered by parallel callers each independently
backing off.

When a provider returns `429` with `Retry-After`, the bucket is
drained to zero and refill is paused until `Retry-After` elapses. This
synchronizes all callers to the provider's actual state.

## (c) Priority lanes

Every gateway call carries a `lane` tag, set by the caller:

| Lane | Caller | Preemption rank |
|------|--------|-----------------|
| `production_live` | live decision pipeline (trade-core) | highest |
| `production_replay` | audit/comparative replay of a production-pinned run | middle |
| `research` | Research sandbox (Phase 2/6) | lowest |

Preemption rule: when a higher-priority call is waiting in the queue
and a lower-priority call is about to dispatch, the lower-priority call
yields its slot. The lower-priority call returns to the queue (it does
not abort; its `idempotency_key` is preserved). This guarantees the
live decision path is never blocked behind research traffic.

A `production_live` call is never preempted. A `research` call is
always preemptable. `production_replay` preempts `research` but yields
to `production_live`.

Lane assignment is the caller's responsibility and is recorded in
`llm_usage.lane` for audit.

## (d) Bounded queue and ADMISSION_REJECTED

Each lane has a bounded queue depth (default 50, tunable via
`policy_versions.gateway.admission.queue_depth`). When a call cannot
dispatch (semaphore full, token-bucket dry) and its lane queue is
full, the gateway returns:

```
ADMISSION_REJECTED
```

This is **distinct** from `TRANSIENT_PROVIDER`:

| Code | Meaning | Retry? |
|------|---------|--------|
| `TRANSIENT_PROVIDER` | provider is down/rate-limited (5xx, timeout, 429) | gateway fallback chain applies |
| `ADMISSION_REJECTED` | WE chose not to send — budget/queue exhausted | caller must back off; no fallback hop |

`ADMISSION_REJECTED` is not a provider failure. It is a capacity
decision by the gateway. Treating it as a transient provider error
would trigger fallback hops, wasting a different provider's budget on
a problem that is not provider-side. The caller (orchestrator) handles
it via Phase 7 recovery — typically queueing the run or degrading.

## (e) Backpressure to the scheduler

The gateway exposes a `budget_available` signal (per tier and global)
consumed by the Phase 7 scheduler before triggering a new cycle:

```
if gateway.budget_available(tier=required_tier) < threshold:
    do NOT trigger new cycle
    record BACKPRESSURE_HELD in scheduler telemetry
```

`threshold` is a percentage of max concurrent (default: 20%). This
prevents the scheduler from flooding the gateway when capacity is low.
Held triggers are not dropped — they remain pending and fire when
budget recovers (bounded by the scheduler's own trigger queue, Phase 7).

This is the coupling point between this document and
`concurrency-budget.md` (Phase 7): the scheduler's resource budget is
informed by the gateway's real-time capacity.

## (f) Retry de-amplification

Gateway-level retries (D6-6 fallback chain, provider 429/5xx) obey:

1. **Jittered exponential backoff**: base delay × 2^attempt ×
   uniform(0.5, 1.0), capped at `policy.gateway.max_backoff_seconds`.
2. **Token-bucket bounded**: a retry consumes from the same
   token-bucket as the original call. If the bucket is dry, the retry
   waits in the lane queue rather than dispatching.
3. **Never exceeds provider rate**: the token-bucket's refill rate IS
   the provider rate. A retry cannot bypass it.

This prevents the classic retry storm: N parallel callers each
retrying independently amplify load by factor N. With a shared
token-bucket, all callers coordinate through the bucket — total
dispatch rate never exceeds provider RPM.

The existing fallback chain (D6-6: same-tier alternates, then tier
down) remains. Admission control does not replace fallback; it gates
dispatch so fallback is triggered less often.

## (g) Observability

Metrics exposed by the gateway (Prometheus format, scraped by Phase 11
observability):

| Metric | Labels | Purpose |
|--------|--------|---------|
| `gateway_admission_total` | `lane`, `outcome` (`admitted`/`queued`/`rejected`) | admission decisions per lane |
| `gateway_tokens_in_flight` | `tier`, `provider` | concurrent in-flight calls |
| `gateway_queue_depth` | `lane` | current queue depth |
| `gateway_token_bucket_available` | `provider` | remaining bucket capacity |
| `gateway_backpressure_held_total` | `tier` | cycles held by backpressure |

`outcome=rejected` spiking is an operational signal to either raise
tier concurrency bounds, add provider accounts, or throttle research
traffic. It is NOT a transient error to be retried silently.

## What this document does NOT define

- Scheduler-side concurrency budget (Phase 7 `concurrency-budget.md`).
- Research isolation mechanics (Phase 7
  `comparative-replay-isolation.md`).
- Provider credential management (Phase 12).
- Specific numeric tuning (Phase 14, from measured load).
- 9router deployment topology (Phase 11).

## Phase boundary

This document fixes the gateway admission contract: per-tier
semaphore, per-provider token-bucket, priority lanes, bounded queue,
`ADMISSION_REJECTED` failure code, backpressure signal, and retry
de-amplification. It is consumed by the Phase 7 scheduler
(`concurrency-budget.md`) and the Phase 7 research isolation model
(`comparative-replay-isolation.md`). It does not define scheduler
internals, deployment, or credentials.
