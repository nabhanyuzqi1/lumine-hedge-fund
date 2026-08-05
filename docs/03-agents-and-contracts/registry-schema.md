# Registry Schema

## Overview

The registry is the replaceability backbone (principle #9). Four
separate tables, one per versioned artifact: models, prompts,
strategies, policies. No value may be hardcoded in code — all are
resolved at decision time and pinned to `lineage_records`.

This document defines the shared column contract, the four tables, the
status lifecycle, the replaceability contract, and the promotion gate.
It does not define prompt text content, AutoGen configuration, risk
math, or migration code.

## Shared column contract (all 4 tables)

```sql
-- Common to every registry table:
id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
version     SEMVER NOT NULL,                 -- e.g. '1.4.2'
status      registry_status NOT NULL,        -- 'sandbox' | 'staging' | 'production' | 'retired'
created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
retired_at  TIMESTAMPTZ,

-- ENUM:
CREATE TYPE registry_status AS ENUM
  ('sandbox', 'staging', 'production', 'retired');

-- Uniqueness: one version string per table, no duplicates
UNIQUE (version)
```

## Status lifecycle

```
sandbox   -> staging    : Review worker recommends
staging   -> production : CIO (human) approves — NO automated path
production-> retired    : CIO (human) supersedes — old row kept, never deleted
```

- Only `production` rows may be pinned to `lineage_records`.
- `retired` rows are immutable and never deleted (principle #6:
  reproducibility — old lineage records still resolve them).
- The system cannot promote itself. Promotion is a human gate,
  recorded as a status transition with audit columns (principle #7).

## Table 1: `model_versions`

```sql
CREATE TABLE model_versions (
  -- shared columns (id, version, status, created_at, retired_at) ...
  provider       TEXT NOT NULL,             -- 'anthropic' | 'openai' | 'vertex' | ...
  model_id       TEXT NOT NULL,             -- provider-specific ID
  tier           TEXT NOT NULL,             -- 'cost-efficient' | 'context-rich' | 'strongest'
  context_window INT NOT NULL,              -- tokens
  config         JSONB NOT NULL             -- temperature, maxTokens, provider-specific params
);
```

Per-role allocation lives in Phase 2 docs (Technical = cost-efficient,
Macro = context-rich, CIO Proposer = strongest). Phase 3 stores the
catalog; the allocation is policy, resolved at runtime via the registry
lookup below.

## Table 2: `prompt_versions`

```sql
CREATE TABLE prompt_versions (
  -- shared columns ...
  sub_role      TEXT NOT NULL,               -- 'technical_analyst' | 'macro_analyst' | 'news_analyst'
                                            -- | 'smc_analyst' | 'ic_forum' | 'cio_proposer'
                                            -- | 'research' | 'review'
  prompt_hash   TEXT NOT NULL,               -- SHA-256 of canonical prompt text
  prompt_ref    TEXT NOT NULL,               -- path or content address (Phase 4 defines storage)
  variables     JSONB NOT NULL,              -- declared input variables + types
  output_schema JSONB NOT NULL               -- expected structured output shape
);
```

`prompt_hash` makes prompt changes auditable: two prompts with the same
text produce the same hash. Phase 4 owns prompt text; Phase 3 owns only
the catalog envelope.

## Table 3: `strategy_versions`

```sql
CREATE TABLE strategy_versions (
  -- shared columns ...
  name          TEXT NOT NULL,               -- 'smc_liquidity_sweep_v1'
  book          TEXT NOT NULL,               -- 'intraday' | 'swing'
  description   TEXT,
  params        JSONB NOT NULL,              -- strategy parameters (thresholds, windows)
  entry_rules   JSONB NOT NULL,              -- deterministic entry conditions
  exit_rules    JSONB NOT NULL,              -- deterministic exit / SL / TP rules
  source        TEXT NOT NULL,               -- 'research' (promoted) | 'manual'
  parent_id     UUID REFERENCES strategy_versions(id)  -- lineage of strategy evolution
);
```

`parent_id` traces strategy evolution (Research -> Sandbox -> CIO ->
production). Promotion is a CIO human gate (principle #7) — Phase 3
stores the chain, does not automate the gate.

## Table 4: `policy_versions`

```sql
CREATE TABLE policy_versions (
  -- shared columns ...
  scope          TEXT NOT NULL,              -- 'risk' | 'sizing' | 'kill_switch' | 'debate'
  policy_hash    TEXT NOT NULL,              -- SHA-256 of canonical policy doc
  policy         JSONB NOT NULL,             -- thresholds, envelopes, kill-switch levels
  effective_from TIMESTAMPTZ NOT NULL,
  effective_to   TIMESTAMPTZ                 -- NULL = currently active
);
```

This is where debate-trigger thresholds, risk envelopes, and kill-switch
tier levels live — all the values Phase 2 refused to hardcode.
`policy_hash` makes policy drift auditable.

## Replaceability contract (principle #9)

```
At decision time, trade-core resolves:
  - model_version_id    <- model_versions    WHERE status='production' AND tier=?
  - prompt_version_id   <- prompt_versions   WHERE status='production' AND sub_role=?
  - strategy_version_id <- strategy_versions WHERE status='production' AND id=?
  - policy_version_id   <- policy_versions   WHERE status='production' AND scope=?
                                              AND effective_to IS NULL

All four UUIDs pinned to lineage_records.
```

No model ID, prompt text, strategy parameter, or threshold value is
ever hardcoded in code or docs. Every value is a registry lookup. To
swap a model: insert a new `model_versions` row, flip statuses, old
rows stay pinned in lineage forever.

## Promotion gate (principle #7)

```
sandbox   -> staging    : Review worker recommends
staging   -> production : CIO (human) approves — NO automated path
production-> retired    : CIO (human) supersedes — old row kept, never deleted
```

The system cannot promote itself. Promotion is a human gate, recorded
as a status transition with audit columns (`created_at`, `retired_at`).

## Separation guarantees

- **No hardcoding.** Every versioned value is a registry lookup.
- **No deletion.** Retired rows stay forever, pinned by old lineage
  records.
- **No auto-promotion.** All `sandbox -> production` transitions require
  the CIO human gate.
- **Hash auditability.** Prompts and policies carry a SHA-256 hash;
  drift is detectable.

## What this schema does NOT define

- Prompt text content (Phase 4).
- AutoGen agent configuration (Phase 4).
- Risk math formulas behind `policy` JSONB (Phase 7).
- Backtest metric schemas (Phase 9).
- Registry API / migration code (Phase 14+).

## Phase boundary

This document fixes the four registry tables, the status lifecycle, the
replaceability contract, and the promotion gate. It does not define
prompt text (Phase 4), risk math (Phase 7), or code (Phase 14+).
