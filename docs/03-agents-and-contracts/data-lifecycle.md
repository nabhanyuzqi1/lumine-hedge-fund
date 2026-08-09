# Data Lifecycle

## Overview

Three lifecycle jobs keep the data layer healthy: partition management
(rolling creation), retention enforcement (tiered DROP PARTITION), and
registry archival (never — retired rows kept forever). This document
defines each job and the invariants that govern them. It does not
define job scheduling infrastructure, aggregation code, or remediation
policy.

## Job 1: Partition management (rolling creation)

```
Daily:   create next day's ticks partition
Monthly: create next month's bars_1m / bars_5m partition
```

Partitions are pre-created ahead of need so inserts never hit a
missing-partition error. Idempotent (`CREATE TABLE IF NOT EXISTS`).
Failure to create a future partition is a drift flag — never silently
ignored — because the next insert would fail.

## Job 2: Retention enforcement (Decision 6)

```
Daily:   DROP ticks partitions older than 7 days
Monthly: DROP bars_1m / bars_5m partitions older than 90 days
Never:   bars_1h / bars_4h / bars_1d (permanent)
```

DROP PARTITION is instantaneous and non-blocking versus DELETE. No
row-level DELETE anywhere. Old lineage records still resolve their
features from surviving permanent tables; tick-level detail ages out
per policy.

| Table | Retention | Action |
|-------|-----------|--------|
| `ticks` | 7 days | DROP daily partition after 7d |
| `bars_1m`, `bars_5m` | 90 days | DROP monthly partition after 90d |
| `bars_1h`, `bars_4h`, `bars_1d` | permanent | no action |

Retention never touches append-only decision tables (`lineage_records`,
`fills`) or registry tables. Those survive forever for reproducibility
(principle #6).

## Job 3: Registry archival (reproducibility)

```
Never:   model_versions, prompt_versions, strategy_versions, policy_versions
Never:   lineage_records, fills (append-only, forever)
```

Retired registry rows stay forever. They are pinned by old
`lineage_records` and needed for replay. No archival, no deletion. This
is the reproducibility invariant made concrete: a decision recorded last
month can be replayed against the same registry versions it was pinned
to.

## Lifecycle invariants

- **No row-level DELETE on append-only tables.** `fills`,
  `lineage_records`, registry tables — INSERT only.
- **No silent auto-correction.** Drift flagged, not masked (principle
  #10).
- **Partitions pre-created.** No runtime partition-missing failures.
- **Retention via DROP PARTITION only.** No DELETE sweeps.
- **Permanent tables never aged.** `bars_1h`/`bars_4h`/`bars_1d` and
  all registry/decision tables survive forever.

## Separation guarantees

- **Append-only is never mutated.** INSERT only on `fills`,
  `lineage_records`, registry.
- **Retention is structural.** DROP PARTITION, not row DELETE.
- **Reproducibility is preserved.** Permanent market data + never-deleted
  registry rows + immutable lineage = replayable decisions.

## What this document does NOT define

- Aggregation logic (tick -> bar rollup) (Phase 14+).
- Lifecycle job scheduling (cron / worker) (Phase 12 + Phase 14+).
- Reconciliation remediation policy (Phase 7).
- Code (Phase 14+).

## Phase boundary

This document fixes the three lifecycle jobs and their invariants. It
does not define aggregation logic (Phase 14+), job scheduling (Phase 12
and Phase 14+), remediation policy (Phase 7), or code (Phase 14+).
