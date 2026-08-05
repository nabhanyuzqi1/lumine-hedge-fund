# Comparative Replay Isolation

## Overview

Decision **D7-10**: comparative re-execution (D7-8) is "not routable
to the live decision path" — that is a LOGICAL isolation. This
document adds RESOURCE isolation: research runs use a separate
gateway budget, are preempted by production, throttle below the
lineage SLA, and cannot acquire strongest-tier budget.

Without resource isolation, research runs (which may run many
parallel comparative re-executions to test candidate prompts/models)
compete with the live pipeline for gateway slots, DB write capacity,
and cost budget. A research burst can starve production, inflate
cost, and pressure the `lineage_pending` write SLA (D5-9f).

This document amends `checkpoint-and-replay.md` (Phase 7) and
`gateway-admission-control.md` (Phase 6).

## Decision(s)

- **D7-10a** — Research runs use a SEPARATE gateway budget (separate
  provider key OR a reserved token-bucket partition).
- **D7-10b** — Priority lanes (D6-8c) enforce `production_live >
  production_replay > research` preemption.
- **D7-10c** — Research DB writes go to a separate `research` schema
  OR are throttled below the `lineage_pending` SLA (p99 < 10ms,
  D5-9f).
- **D7-10d** — Global `research_budget` knob (0-100%) the CIO can cut
  to zero; zero = no new research runs, in-flight runs drain.
- **D7-10e** — Research runs CANNOT acquire `strongest`-tier gateway
  budget (protects cost ceiling, D6-4).
- **D7-10f** — Isolation is PHYSICAL (separate budgets/keys), not
  just logical (separate `workflow_run_id` prefix).

## (a) Separate gateway budget

Research traffic is isolated from production traffic at the gateway
level by one of two mechanisms (selected at deployment time, Phase 11):

**Option 1: Separate provider key.** The research sandbox uses a
different provider API key than production. This gives hard rate-limit
isolation: the provider enforces separate RPM/TPM limits per key.
Research cannot exhaust production's quota and vice versa. This is
the preferred option when the provider supports multiple keys per
account.

**Option 2: Reserved token-bucket partition.** A single provider key
is shared, but the gateway maintains separate token-buckets
(`gateway-admission-control.md` D6-8b): one for `production_live` +
`production_replay` lanes, one for `research` lane. The research
bucket's refill rate is a configurable fraction of the total measured
provider rate (default: 20%). Research calls draw from the research
bucket; production calls draw from the production bucket. Research
cannot borrow from production's bucket.

Both options ensure research traffic is physically bounded. The
choice is a deployment decision (Phase 11), not an architecture
decision — the isolation contract is the same either way.

Research runs also have a separate `research_max_runs` sub-budget in
the orchestrator (`concurrency-budget.md` D7-9c, default 4). This
bounds parallelism independently of the gateway budget.

## (b) Priority lane preemption

The gateway priority lanes (D6-8c) enforce:

```
production_live (highest) > production_replay > research (lowest)
```

When a `production_live` call is waiting and a `research` call is
about to dispatch (or is in-flight at a yieldable point), the
research call yields. The research call returns to the lane queue
with its `idempotency_key` preserved; it resumes when capacity is
available.

Research runs are always preemptable. This is the physical
enforcement of the logical rule "research never blocks production"
(D7-8). Without preemption, a research run holding a gateway slot
could delay a live decision by seconds — unacceptable on the critical
path.

## (c) Research DB write isolation

Research runs produce comparison artifacts, not decisions. Their
writes must not pressure the `lineage_pending` write SLA (p99 < 10ms,
D5-9f) or pollute the `lineage_records` analytical table.

**Option 1: Separate `research` schema.** Research runs write to
`research.lineage_records`, `research.llm_usage`, etc. — a parallel
schema with the same structure but separate physical tables. This
gives complete write isolation: research writes cannot contend with
production writes on `lineage_pending`. The research schema is
droppable/purgeable without affecting production data.

**Option 2: Throttled writes to shared tables.** If a separate schema
is not desired, research writes to `lineage_pending` are throttled by
the orchestrator: the orchestrator enforces a research write rate
that is below the measured `lineage_pending` headroom. Specifically,
research writes are admitted only when `lineage_pending_write_latency
p99 < 8ms` (2ms below the 10ms SLO). If production write latency
rises, research writes pause.

Option 1 is preferred (cleaner isolation, no monitoring overhead).
Option 2 is the fallback for deployments where schema proliferation
is undesirable.

In both cases, research writes are tagged `lane='research'` in
`llm_usage` and any journal entries, so they are filterable in
analytics and cost reports.

## (d) Global research_budget knob

The CIO (human, outside system — governance-and-cross-department.md)
controls a global `research_budget` knob:

```sql
-- policy_versions.orchestration (JSONB)
{
  "research": {
    "budget_pct": 20,        -- 0-100, percentage of research resource pool
    "max_concurrent_runs": 4,
    "throttle_when_live_load_high": true
  }
}
```

Semantics:

| `budget_pct` | Effect |
|--------------|--------|
| 0 | No new research runs may start. In-flight research runs drain (complete current stage, then pause at next checkpoint). |
| 1-100 | Research runs may start, consuming up to `budget_pct`% of the research resource pool (gateway budget, concurrent slots). |

`budget_pct = 0` is the panic control: the CIO cuts research to zero
during high-load periods (e.g., high-volatility market events where
the live pipeline needs all resources). In-flight research runs are
not killed — they drain gracefully at their next checkpoint
(preserving D7-3 resume safety).

The knob is read by the orchestrator before admitting any new
research run. A research run admitted at `budget_pct = 20` is not
aborted if the knob is later cut to 0 — it drains at its next
checkpoint. This prevents mid-stage aborts that would waste already-
spent LLM calls.

## (e) No strongest-tier budget for research

Research runs CANNOT acquire `strongest`-tier gateway budget. This
is enforced at the gateway admission layer:

```
if lane == 'research' AND tier == 'strongest':
    return ADMISSION_REJECTED  (reason: 'research_strongest_blocked')
```

Rationale: the `strongest` tier is escalation-only (model-routing.md
D6-1), reserved for high-stakes live decisions (CIO override of IC,
kill-switch-adjacent context). Research has no legitimate need for
the most expensive tier — comparative re-execution tests candidate
prompts/models at the tier they would run in production, and
production roles default to `cost-efficient` or `context-rich`
(model-routing.md role mapping). If a research scenario requires
`strongest`, it is a manual flag with explicit CIO approval, not an
automated path.

This protects the cost ceiling (D6-4): a research burst cannot
inflate `strongest`-tier spend.

## (f) Physical vs. logical isolation

D7-8 provides LOGICAL isolation: research runs have a separate
`workflow_run_id` prefix, never write to production lineage, and are
not routable to the live decision path. This is necessary but not
sufficient. Logical isolation prevents data corruption but does not
prevent resource starvation.

This document adds PHYSICAL isolation:

| Isolation dimension | Logical (D7-8) | Physical (this doc) |
|---------------------|----------------|---------------------|
| Run identity | Separate `workflow_run_id` prefix | (same) |
| Lineage writes | Never to production lineage | Separate schema OR throttled below SLA |
| Gateway budget | (not addressed) | Separate key OR reserved bucket partition |
| Gateway tier | (not addressed) | Cannot acquire `strongest` |
| Concurrency | (not addressed) | `research_max_runs` sub-budget (D7-9c) |
| Preemption | (not addressed) | Research always preemptable by production |
| Cost ceiling | (not addressed) | CIO `research_budget` knob, cuttable to zero |

Physical isolation is what makes the logical guarantees hold under
load. Without it, a research burst can violate the logical isolation
indirectly: by starving the live pipeline of gateway slots, the
research run causes a production run to miss its stage deadline,
triggering `DEADLINE_EXCEEDED` and a recovery action — effectively
disrupting the live path without ever writing to production lineage.

## What this document does NOT define

- Research sandbox lifecycle (Phase 2/6 — promotion path from
  research to production via CIO gate).
- Research tooling/UI (Phase 10).
- Comparative re-execution API surface (Phase 9).
- Provider key provisioning (Phase 12).
- Specific `research_budget_pct` tuning (Phase 14, from measured
  load).

## Phase boundary

This document amends `checkpoint-and-replay.md` (Phase 7) by adding
resource isolation to the D7-8 comparative re-execution model, and
amends `gateway-admission-control.md` (Phase 6) by constraining
research lane access to `strongest` tier. It does not define the
research promotion lifecycle (Phase 2/6), gateway internals (Phase 6
— this doc constrains, not redefines), or code (Phase 14+).
