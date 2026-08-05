# LLM Cost Control

## Overview

Decision **D6-4**: cost is bounded by a deterministic daily budget with
a circuit breaker, enforced *before* calls reach the gateway. Cost
incidents degrade the system deliberately and audibly — they never hide.

## Budget model

Stored in `policy_versions.cost` (JSONB):

| Field | Meaning |
|-------|---------|
| `daily_cap_usd.cost-efficient/context-rich/strongest` | per-tier daily spend ceiling (Phase 3 tier enum) |
| `daily_cap_usd.global` | total daily ceiling across tiers |
| `degrade_order` | which roles degrade first when a cap is hit |
| `protected_roles` | roles that may not be blocked (live decision pipeline minimum) |
| `soft_warn_pct` | % of cap at which a warning event is emitted |

Caps reset at UTC midnight (same clock as the trading day boundary).

V1 numbers are placeholders to be set at Phase 14 from measured
cycle cost; the *structure* is fixed here.

## Pre-call budget check (deterministic)

Before every LLM call, system code:

1. Reads today's accumulated spend per tier from `llm_usage`
   (materialized by a cheap running-sum view or cache counter).
2. If tier spend ≥ cap → apply degrade policy (below).
3. If global spend ≥ cap → block all non-protected roles.

The check is code, not an LLM judgment — reproducible and testable.

## Degrade policy (ordered)

On tier cap breach, degrade in this order until spend is back under cap:

1. **Journal / narrative jobs** → drop to cost-efficient or skip this
   cycle (next cycle resummarizes).
2. **Research sandbox** → pause entirely; it is non-production by
   definition.
3. **Analyst re-runs / escalations** → skip escalation, keep the
   original tier output, flag `degraded=true` in lineage.
4. **Debate round** → skip; IC proceeds on raw analyst outputs,
   `debate_held=false`, reason recorded.

**Never degraded/blocked** (protected): the primary pass of the live
decision pipeline at its *default* tier — analysts cost-efficient,
IC/CIO context-rich.
A hedge fund that cannot afford its minimum reasoning loop has a
business problem, not a software problem; the breaker surfaces that
rather than silently trading blind.

On global cap breach: only the protected minimum pipeline runs;
everything else blocks until reset.

## Accounting (D6-7)

Every call writes an `llm_usage` row. **This table is introduced by
Phase 6** — Phase 3 did not define it (only `model_versions.context_window`
exists there). It is a new append-only accounting table that joins to
the existing decision tables:

```sql
CREATE TABLE llm_usage (
  id                UUID PK,
  ts                TIMESTAMPTZ NOT NULL,
  lineage_id        UUID NULL,          -- FK lineage_records; NULL for non-decision jobs
  role              TEXT NOT NULL,      -- analyst/ic/cio/journal/research/...
  tier              TEXT NOT NULL,      -- cost-efficient|context-rich|strongest (Phase 3 enum)
  model_version_id  UUID NOT NULL,      -- FK model_versions (actual model used, post-fallback)
  prompt_version_id UUID NULL,          -- FK prompt_versions when applicable
  tokens_in         INT NOT NULL,
  tokens_out        INT NOT NULL,
  cost_usd          NUMERIC NOT NULL,
  fallback_hops     INT NOT NULL DEFAULT 0,
  degraded          BOOLEAN NOT NULL DEFAULT FALSE
);
```

Indexes: `(ts)` for daily budget sums, `(lineage_id)` for per-decision
cost, `(role, ts)` for per-role analytics. Append-only; permanent
retention (auditable cost history). Physical sizing joins the Phase 5
decision-table class (low rate, grows forever, no partitioning needed
in V1).

| Column | Content |
|--------|---------|
| `lineage_id` | decision this call served (nullable for non-decision jobs) |
| `role`, `tier` | routing context |
| `model_version_id` | actual model used (post-fallback) |
| `tokens_in/out`, `cost_usd` | from gateway meter |
| `fallback_hops`, `degraded` | incident context |
| `ts` | UTC |

Budget counters derive from this table — one source of truth, no
parallel accounting system.

## Alerting & audit

- `soft_warn_pct` breach → warning event (Phase 11 routing to ops).
- Any degrade/block event → written into the cycle's
  `lineage_records` context (`verdict` stays the trading verdict; the
  degrade fact rides in the proposal/risk context JSONB).
- Daily cost summary job → per-tier, per-role, per-strategy totals;
  feeds the Phase 10 cost dashboard later.

## Anti-patterns (rejected)

- **Monthly-only budget**: overspend discovered too late.
- **Monitor-only**: an unbounded LLM bill is an operational incident;
  observation without a breaker is not control.
- **Hidden downgrade of the decision pipeline**: violates "evidence
  before capital" — if the pipeline ran degraded, the record must
  say so.

## What this document does NOT define

- Concrete dollar caps (Phase 14, from measured cycle cost).
- Alert delivery channels (Phase 11).
- Dashboard UI (Phase 10).

## Phase boundary

This document fixes budget structure, the pre-call check, degrade
order, and accounting schema. It does not set numbers or build UI.
