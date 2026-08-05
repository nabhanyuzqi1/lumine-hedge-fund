# Lineage Schema

## Overview

The `lineage_records` table is the single most important invariant in
the system (Phase 1). Every decision writes exactly one record,
synchronously, ACID, before dispatch. Phase 3 fixes its structure.

This document defines the table, the hybrid scalar + JSONB split, the
version pinning contract, and the blocking ACID write gate on the
critical path. It does not define risk math, idempotency code, or
partitioning of the table itself.

## Table: `lineage_records`

```sql
CREATE TABLE lineage_records (
  -- Identity (immutable)
  lineage_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  decision_ts         TIMESTAMPTZ NOT NULL,

  -- Scalar queryable fields (indexed, immutable)
  book                TEXT NOT NULL,              -- 'intraday' | 'swing'
  strategy_id         UUID NOT NULL,              -- FK strategy_versions
  symbol              TEXT NOT NULL,              -- 'XAUUSD'
  side                TEXT NOT NULL,              -- 'BUY' | 'SELL'
  verdict             TEXT NOT NULL,              -- 'APPROVE' | 'REJECT' | 'MODIFY'
  size                NUMERIC(20,4),
  fill_price          NUMERIC(20,5),

  -- Version pins (reproducibility — principle #6)
  model_version_id    UUID NOT NULL,              -- FK model_versions
  prompt_version_id   UUID NOT NULL,              -- FK prompt_versions
  policy_version_id   UUID NOT NULL,              -- FK policy_versions
  strategy_version_id UUID NOT NULL,              -- FK strategy_versions (denormalized for query)

  -- JSONB payload (the full decision context, immutable)
  trigger             JSONB NOT NULL,             -- what fired this decision (scheduler event, tick)
  features            JSONB,                      -- ATR/EMA/RSI/OHLC snapshot at decision time
  proposal            JSONB NOT NULL,             -- LLM committee output (4 analysts + IC + CIO)
  risk_context        JSONB NOT NULL,             -- exposure, kill-switch flags, policy snapshot

  -- Audit (immutable)
  created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_lineage_decision_ts ON lineage_records (decision_ts);
CREATE INDEX idx_lineage_book_ts     ON lineage_records (book, decision_ts);
CREATE INDEX idx_lineage_strategy    ON lineage_records (strategy_id);
CREATE INDEX idx_lineage_verdict     ON lineage_records (verdict);
```

## Design rationale

### Hybrid split (Decision 1)

Scalar columns hold what we query and index: `book`, `strategy_id`,
`symbol`, `verdict`, `decision_ts`, `size`, `fill_price`. These power
analytical queries (P&L by book, verdict counts by strategy, decisions
in a time range) without touching JSONB.

JSONB holds what we preserve for reproducibility: the full `trigger`,
`features`, `proposal`, and `risk_context`. This is the rich context
needed to replay a decision. Querying into JSONB is possible but not
the hot path — the scalar columns cover the common analytical queries.

### Immutability

`lineage_records` is append-only. No UPDATE, no DELETE. Every column is
fixed at insert. This is what makes a decision reproducible: the same
`lineage_id` always returns the same state, forever.

### Version pins (principle #6)

Every record pins four version UUIDs:

- `model_version_id` — which model produced the proposal.
- `prompt_version_id` — which prompt was used.
- `policy_version_id` — which risk / debate / sizing policy was active.
- `strategy_version_id` — which strategy version fired.

To replay a decision, resolve these four versions from their registry
tables (see `registry-schema.md`). Old versions stay pinned forever —
no hardcoding (principle #9), no deletion.

`strategy_version_id` is denormalized alongside `strategy_id` so the
exact version is queryable without a join against the registry. The
registry row is the source of truth; the denormalized column is a
query convenience.

### Idempotency (Decision 7)

`lineage_id` is the primary key. The ExecutionRouter generates it
before dispatch and writes the lineage record. If the bridge replays a
command (stream offset rewind, crash recovery), the listener matches
the fill back to `lineage_id`. The `processed_commands` table (see
`positions-fills-schema.md`) uses
`INSERT ... ON CONFLICT (lineage_id) DO UPDATE` (bumping `replay_count`,
stamping `last_replay_at`, flipping `result` to `duplicate_ignored`) to
prevent duplicate orders while recording the replay.

## Critical path contract (Phase 1, reaffirmed)

```
1. trade-core computes proposal (LLM committee)
2. RiskValidator verdict (APPROVE / REJECT / MODIFY)
3. PortfolioSizer sizes order (if APPROVE)
4. ExecutionRouter:
   a. BEGIN TRANSACTION
   b. INSERT INTO lineage_records (...)   <- blocking ACID write
   c. COMMIT                              <- must succeed
   d. if commit fails -> safe state, NO dispatch
   e. if commit succeeds -> publish to mt5.commands stream
5. Listener matches fill -> lineage_id -> UPDATE positions, INSERT fills
```

Step 4b-4c is the blocking ACID gate. No batching. One write per
decision. If it fails, the order never leaves the system (principle
#10: safe state by default).

## Column semantics

| Column | Type | Notes |
|--------|------|-------|
| `lineage_id` | UUID PK | Generated by ExecutionRouter before dispatch |
| `decision_ts` | TIMESTAMPTZ | When the decision was made (not when written) |
| `book` | TEXT | `intraday` or `swing` (principle #5: books never blend) |
| `strategy_id` | UUID | FK to `strategy_versions.id` |
| `symbol` | TEXT | `XAUUSD` (Phase 0 scope) |
| `side` | TEXT | `BUY` or `SELL` |
| `verdict` | TEXT | `APPROVE`, `REJECT`, or `MODIFY` (RiskValidator output) |
| `size` | NUMERIC(20,4) | Sized order; NULL if REJECT |
| `fill_price` | NUMERIC(20,5) | Filled later; NULL until fill arrives |
| `model_version_id` | UUID | FK to `model_versions.id` |
| `prompt_version_id` | UUID | FK to `prompt_versions.id` |
| `policy_version_id` | UUID | FK to `policy_versions.id` |
| `strategy_version_id` | UUID | FK to `strategy_versions.id` (denormalized) |
| `trigger` | JSONB | Scheduler event or tick that fired this decision |
| `features` | JSONB | Feature snapshot at decision time (ATR/EMA/RSI/OHLC) |
| `proposal` | JSONB | LLM committee output (4 analysts + IC + CIO Proposer) |
| `risk_context` | JSONB | Exposure, kill-switch flags, policy snapshot |
| `created_at` | TIMESTAMPTZ | When the row was inserted |

## What this schema does NOT define

- Risk math formulas / envelope calculations (Phase 7).
- LLM proposal field internals — `proposal` is JSONB; its sub-structure
  is finalized in Phase 4 (prompt design). `stream-payloads.md` defines
  the *envelope*, not the prompt body.
- Idempotency key implementation code (Phase 14+).
- Partitioning of `lineage_records` itself — decision: single table.
  Volume is low (one row per decision, not per tick); no partitioning
  needed.

## Phase boundary

This document fixes the `lineage_records` schema, the hybrid split, the
version pinning contract, and the blocking ACID gate. It does not
define risk math (Phase 7), prompt internals (Phase 4), or code
(Phase 14+).
