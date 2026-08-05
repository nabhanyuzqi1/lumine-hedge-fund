# Inter-Agent Message Versioning

## Overview

`proposal-schema.md` defines the CIO Proposer's output schema and
marks it `version: "v1"`. But every other inter-agent message —
analyst-to-IC, IC-to-CIO, RiskValidator verdict envelope — has no
versioning contract. A producer that adds a field or changes a type
breaks consumers silently. This document generalizes the
`proposal-schema.md` pattern to ALL inter-agent messages: every
message carries a semver, schemas live in a versioned registry,
compatibility policy governs breaking changes, CI enforces
compatibility, and lineage pins the schema version per stage.

It amends `proposal-schema.md` (Phase 4) and the registry (Phase 3).

## Decision: D4-5 — Every inter-agent message carries `message_schema_version`

### Version field on every message

Every inter-agent message (analyst output, IC output, CIO proposal,
RiskValidator verdict, PortfolioSizer sized-order, ExecutionRouter
command envelope) carries:

```json
{ "message_schema_version": "1.2.0", "message_schema_name": "analyst_output", ... }
```

`message_schema_version` is semver. `message_schema_name` identifies
which schema family. The producer MUST emit both; the consumer MUST
validate against the declared version before processing.

### Registry table: `message_schema_versions`

```sql
CREATE TABLE message_schema_versions (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name          TEXT NOT NULL,                  -- 'analyst_output' | 'ic_output' | 'proposal' | 'risk_verdict' | ...
  version       SEMVER NOT NULL,
  schema        JSONB NOT NULL,                 -- JSON Schema (draft-07) for this message version
  compatibility TEXT NOT NULL,                  -- 'backward' | 'forward' | 'full' | 'none'
  code_hash     TEXT NOT NULL,                  -- SHA-256 of canonical schema text
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  status        registry_status NOT NULL,       -- sandbox | staging | production | retired
  superseded_by UUID REFERENCES message_schema_versions(id),
  UNIQUE (name, version)
);
```

Same supersession model as other registry tables
(`registry-schema.md`). Only `production` rows are emitted at
runtime; retired rows stay pinned in lineage forever.

`proposal-schema.md`'s `v1` becomes `proposal` name, version
`1.0.0` in this registry — the first instance of the generalized
pattern.

### Compatibility policy

| Change type | Bump | Policy |
|-------------|------|--------|
| New optional field | minor | backward-compatible; existing consumers parse unchanged |
| New required field | major | breaking; requires parallel consumer support during cutover |
| Removed field | major | breaking |
| Type change on existing field | major | breaking |
| Enum value added | minor | backward-compatible (consumers must tolerate unknown enum values) |
| Enum value removed | major | breaking |

Within a minor bump, a v1.0 consumer MUST parse a v1.2 message
ignoring unknown fields. Within a major bump (1.x -> 2.x), the
producer MUST support parallel emission or the consumer MUST be
upgraded before the producer switches — the cutover is a staged,
audited event, not a silent swap.

### CI compatibility enforcement

Two CI checks guard the contract:

1. **Consumer declaration.** A prompt or stage consuming schema
   `name@vN` must declare that compatibility in its config
   (`prompt_versions.variables` or stage manifest). CI fails if a
   consumer does not declare the schema it expects.

2. **Producer compatibility test.** A producer emitting
   `name@vN+1` must demonstrate that all `production` consumers
   declaring `name@vN` still parse the vN+1 output (for minor bumps)
   or that a cutover plan exists (for major bumps). The test feeds
   vN+1 sample output to the vN consumer's parser and asserts no
   validation failure on backward-compatible changes.

These checks run in CI before a schema version can move from
`staging` to `production`.

### Lineage pins `message_schema_version` per stage

Each stage's output, recorded in the reasoning trace and/or
`lineage_records.proposal`, pins the `message_schema_version` that
produced it. For the CIO proposal, this is the existing
`proposal.version` field, now backed by a registry row. For
analyst/IC outputs, the schema version is pinned in the
`analyst_inputs` and `ic_output` sub-objects.

Replay resolves the pinned schema version from the registry to
revalidate the message — reproducibility (#6) holds because the
schema is immutable and never deleted.

### Generalization of proposal-schema.md

`proposal-schema.md` is the FIRST inter-agent message schema. This
document generalizes the pattern:

- `proposal` becomes a row in `message_schema_versions` (name=
  `proposal`, version=`1.0.0`).
- The `version: "v1"` field in the proposal JSON is retained as a
  payload marker but is now backed by the registry row.
- All other inter-agent messages (analyst_output, ic_output,
  risk_verdict, sized_order, execution_command) follow the same
  pattern: registry row, semver, compatibility policy, CI check,
  lineage pin.

No change to the proposal schema's field semantics — only the
versioning envelope is generalized.

## What this document does NOT define

- Schema content for messages other than `proposal` (those are
  defined per-stage in Phase 4 sub-documents as stages are
  specified).
- CI pipeline implementation (Phase 13/14).
- Runtime parser code (Phase 14+).

## Phase boundary

This document amends `proposal-schema.md` (Phase 4) by backing its
`version` field with a registry row and generalizing the pattern to
all inter-agent messages. It amends the registry (Phase 3) by adding
`message_schema_versions`. It does not define individual message
schemas beyond `proposal`, CI implementation, or parser code.
