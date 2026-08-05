# Feature Store Contract

## Overview

Finding S11: features are currently an unversioned JSONB blob in
`lineage_records.features`. That blob is a snapshot at decision time,
but the feature *definition* (which indicators, which parameters,
which code) is not pinned. Two runs with the "same" `features` JSONB
can have been computed by different feature code. This violates
reproducibility (principle #6): replaying a decision cannot guarantee
the same feature vector, because the code that produced the features
is not identified.

This document fixes the feature store contract: every feature has a
`feature_version_id` pinned in lineage, features are computed once and
stored point-in-time correct, and a backtest reads from the store
rather than recomputing.

Decision **D3-9**: features are versioned, registry-pinned,
point-in-time correct, and compute-once. This adds a fifth version
pin alongside the existing four (`model`, `prompt`, `policy`,
`strategy`).

## Decision D3-9 — Versioned, point-in-time feature store

### Feature version registry

A new registry table `feature_versions` (alongside `model_versions`,
`prompt_versions`, `strategy_versions`, `policy_versions`) pins the
definition of a feature.

```sql
CREATE TABLE feature_versions (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name            TEXT NOT NULL,                 -- 'atr_14' | 'ema_50' | 'rsi_14' | 'realized_vol_1h' | ...
  version         SEMVER NOT NULL,               -- '1.0.0'
  params          JSONB NOT NULL,                -- e.g. {"period": 14, "smoothing": "rma"} for atr_14
  code_hash       TEXT NOT NULL,                 -- SHA-256 of the feature computation code
  warmup_required INT NOT NULL,                  -- min bars before feature is valid (e.g. 14 for atr_14)
  status          registry_status NOT NULL,      -- 'sandbox' | 'staging' | 'production' | 'retired'
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  retired_at      TIMESTAMPTZ,
  superseded_by   UUID REFERENCES feature_versions(id),
  UNIQUE (name, version)
);
```

- `name` + `version` uniquely identify a feature definition.
- `params` fixes the parameters (period, smoothing, window). Two
  `atr_14` rows with different `params` are different versions.
- `code_hash` pins the computation code. A change to the code is a new
  version. This is the load-bearing field: same `code_hash` + same
  `params` + same input data = same output, forever.
- `warmup_required` declares how many bars of history the feature
  needs before its value is valid. A feature requested before warmup
  is a hard error, not a zero or null.
- The table follows the same status lifecycle as the other registries
  (`registry-schema.md`): `sandbox -> staging -> production -> retired`,
  no auto-promotion, retired rows never deleted.

### Feature values (compute-once, point-in-time)

Features are computed once and stored with two timestamps:

- `computed_ts` — when the feature was computed (wall-clock).
- `as_of_ts` — the timestamp of the latest data point used to compute
  the feature. This is the point-in-time marker.

```sql
CREATE TABLE feature_values (
  feature_version_id UUID NOT NULL REFERENCES feature_versions(id),
  symbol             TEXT NOT NULL,              -- 'XAUUSD'
  as_of_ts           TIMESTAMPTZ NOT NULL,       -- point-in-time marker
  computed_ts        TIMESTAMPTZ NOT NULL,       -- when computed
  value              JSONB NOT NULL,             -- the feature value (scalar or vector)
  PRIMARY KEY (feature_version_id, symbol, as_of_ts)
) PARTITION BY RANGE (as_of_ts);
```

- Partitioned by `as_of_ts` (e.g. monthly) to keep range scans fast
  and retention manageable.
- The PK `(feature_version_id, symbol, as_of_ts)` enforces
  compute-once: a second compute for the same key is a conflict, not
  an overwrite. Late-arriving corrections require a new
  `feature_version_id` (a new version), never an UPDATE.
- `value` is JSONB to support scalar features (`atr_14: 2.34`) and
  vector features (`ema_stack: {ema_20: 1920.1, ema_50: 1915.3}`).
- Retention: feature values are kept for the life of the system
  (they are the reproducibility substrate, same class as
  `lineage_records`). Partitioning is for query performance, not
  retention drops.

### Lineage pinning

`lineage_records.features` (JSONB, already defined in
`lineage-schema.md`) gains a required `feature_versions` array:

```jsonc
// lineage_records.features (addition)
{
  "feature_versions": [
    {"name": "atr_14",        "feature_version_id": "<uuid>"},
    {"name": "ema_50",        "feature_version_id": "<uuid>"},
    {"name": "rsi_14",        "feature_version_id": "<uuid>"},
    {"name": "realized_vol_1h", "feature_version_id": "<uuid>"}
  ],
  "as_of_ts": "<decision_ts>",
  "values": { "atr_14": 2.34, "ema_50": 1915.3, ... }
}
```

- The `feature_versions` array is the fifth pin. The blocking ACID
  write (`lineage-schema.md` step 4b) must include it. A lineage row
  missing the array fails the gate.
- `as_of_ts` is pinned to the decision timestamp. Replay reads feature
  values for this `as_of_ts` and these `feature_version_id`s from the
  store.
- `values` is the snapshot for convenience; the store is the source of
  truth. If `values` and the store disagree, the store wins (the
  snapshot is a cache).

### Point-in-time correctness

- A feature at decision `T` uses only data with `as_of_ts <= T`. This
  is enforced at feature-store read time: queries are
  `WHERE feature_version_id = ? AND symbol = ? AND as_of_ts <= T`.
- Lookahead (reading a feature with `as_of_ts > T` for a decision at
  `T`) is a hard error. In production it aborts the cycle with
  `lookahead_violation`. In backtest it aborts the run
  (`backtest-parity-contract.md`).
- This is the property that makes features safe for backtest: the
  backtest cannot accidentally read the future, because the store
  refuses to serve it.

### Reproducibility

- Same `feature_version_id` + same `as_of_ts` + same `symbol` =
  identical feature vector, forever. The PK guarantees the row is
  immutable; `code_hash` + `params` guarantee the definition is
  immutable; retired versions are never deleted.
- Replay of a decision reads the pinned `feature_version_id`s and
  `as_of_ts` from lineage, fetches the rows from `feature_values`, and
  reconstructs the exact feature vector the decision used. No
  recomputation, no divergence.

### Backtest reads from the store

- A backtest MUST read features from `feature_values`, never
  recompute them (`backtest-parity-contract.md`). This is the parity
  contract's feature corollary.
- Recomputing features in the backtest harness is prohibited because
  it risks divergence (float order, warmup boundary, lookahead). The
  store is the single source of truth.
- The feature store is populated by a deterministic compute job
  (Phase 14+) that reads `bars_*` and writes `feature_values`. The
  compute job's code hash is what `feature_versions.code_hash`
  records. Production and backtest read the same rows.

## Interaction with existing decisions

- **Lineage gate (Phase 3):** the blocking ACID write now includes
  `feature_versions` in `features` JSONB. The gate enforces its
  presence.
- **D6-5 (stateless V1):** unchanged. Features are fetched per-cycle
  from the store; no memory.
- **D7-5 (journal is truth):** the journal records the pinned
  `feature_version_id`s and `as_of_ts`. The journal remains truth.
- **D7-8 (replay never mutates):** replay reads feature values; it
  never overwrites them. Late corrections are new versions, not
  in-place edits.
- **Backtest parity (`backtest-parity-contract.md`):** depends on
  `feature_version_id` being pinned and `as_of_ts` being enforced.
  This document is the contract that makes parity checkable.
- **Risk engine determinism (`risk-engine-determinism.md`):** the
  `volatility_band` classification uses the feature-store ATR/realized
  vol feature, so the band is reproducible.

## Phase boundary

- Physical DDL for `feature_versions` and `feature_values`
  (partitioning scheme, indexes, retention) is Phase 5. This document
  fixes the contract and the table shape.
- The feature compute job code is Phase 14+. `code_hash` pins it; this
  document does not write the code.
- Feature definitions (which indicators, which params) are strategy
  data, owned by the strategy author. This document fixes the
  envelope, not the contents.

## What this document does NOT define

- The specific feature names/params for V1 strategies (strategy data).
- The compute job implementation (Phase 14+).
- Physical partitioning and index choices beyond the PK (Phase 5).
- A feature-serving API surface (Phase 9, if needed; V1 reads directly
  from the table).

## Phase boundary

This document fixes the `feature_versions` registry, the
`feature_values` compute-once point-in-time store, the fifth lineage
pin, the lookahead prohibition, and the reproducibility guarantee. It
does not define physical DDL beyond the table shape (Phase 5), compute
code (Phase 14+), or an API surface (Phase 9).
