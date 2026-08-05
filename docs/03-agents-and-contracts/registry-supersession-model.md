# Registry Supersession Model

## Overview

Decision **D3-4**: the registry schema (`registry-schema.md`) models
version supersession as binary — a version is either `production` or
`retired`. Reality is graded: a new prompt version may be a drop-in
replacement (output schema unchanged), a backward-compatible tweak
(added fields, old consumers still work), or a breaking change
(schema reshape, requires remapping). Treating all supersessions as
equal forces either over-cautious hard aborts on every resume or
unsafe silent remaps.

This document amends `registry-schema.md` (Phase 3) and
`checkpoint-and-replay.md` (Phase 7) to introduce a graded
compatibility model on the supersession edge.

## Decision(s)

- **D3-4a** — Each version row gains `superseded_by` (UUID, nullable),
  `compatibility` enum (`exact` | `backward_compatible` |
  `breaking`), and `migration_notes` (TEXT).
- **D3-4b** — Resume gate semantics (D7-8): `exact` mismatch → hard
  abort (`ABORTED_STALE`); `backward_compatible` → may remap to
  successor with a journal entry; `breaking` → hard abort.
- **D3-4c** — Supersession chains form a DAG;
  `resolve_compatible(version_id)` walks the chain to find the
  current production version reachable via `backward_compatible`
  edges.
- **D3-4d** — CI check: no two `production` versions of the same
  artifact coexist without an explicit compatibility edge.
- **D3-4e** — Promotion rule: a `breaking` supersession requires the
  old version to remain `production` until all in-flight runs pinning
  it terminate (graceful cutover).
- **D3-4f** — Deprecation: a version with no in-flight pins and
  `breaking`-superseded may be retired after 90 days.

## (a) Schema amendment

All four registry tables (`model_versions`, `prompt_versions`,
`strategy_versions`, `policy_versions`) gain three columns:

```sql
-- Amend each registry table (shared column contract extension)
ALTER TABLE model_versions
  ADD COLUMN superseded_by  UUID REFERENCES model_versions(id),
  ADD COLUMN compatibility  supersession_compatibility,
  ADD COLUMN migration_notes TEXT;

ALTER TABLE prompt_versions
  ADD COLUMN superseded_by  UUID REFERENCES prompt_versions(id),
  ADD COLUMN compatibility  supersession_compatibility,
  ADD COLUMN migration_notes TEXT;

ALTER TABLE strategy_versions
  ADD COLUMN superseded_by  UUID REFERENCES strategy_versions(id),
  ADD COLUMN compatibility  supersession_compatibility,
  ADD COLUMN migration_notes TEXT;

ALTER TABLE policy_versions
  ADD COLUMN superseded_by  UUID REFERENCES policy_versions(id),
  ADD COLUMN compatibility  supersession_compatibility,
  ADD COLUMN migration_notes TEXT;

CREATE TYPE supersession_compatibility AS ENUM
  ('exact', 'backward_compatible', 'breaking');
```

Column semantics:

| Column | Type | Meaning |
|--------|------|---------|
| `superseded_by` | UUID, nullable | The successor version that replaced this one. NULL = current (not yet superseded). |
| `compatibility` | enum, nullable | The compatibility class of the supersession edge TO `superseded_by`. NULL when `superseded_by` is NULL. Set by the CIO at promotion time (principle #7). |
| `migration_notes` | TEXT, nullable | Human-readable notes on what changed and how to migrate. Required when `compatibility = 'backward_compatible'` (the remap logic may need guidance); optional otherwise. |

The `compatibility` value lives on the OLD version (the one being
superseded), describing the edge to the NEW version. This means:
"version 1.4.2 was superseded by 1.5.0 with backward_compatible
compatibility."

## (b) Resume gate semantics

`checkpoint-and-replay.md` D7-8 resume gate #2 ("Version match")
currently reads:

> Pinned `model_version_id`s / `prompt_version_id`s /
> `policy_version_id` still resolve to the same registry rows (not
> retired/superseded). Mismatch → `ABORTED_STALE`.

This is amended to graded semantics:

| Pinned version state | `compatibility` of supersession edge | Resume action |
|----------------------|--------------------------------------|---------------|
| Still `production` (not superseded) | N/A | Resume normally |
| Superseded, edge = `exact` | `exact` | Hard abort: `ABORTED_STALE`. `exact` means "the successor is byte-identical" — if the pinned version is superseded, something is wrong. |
| Superseded, edge = `backward_compatible` | `backward_compatible` | May remap: resolve successor via `resolve_compatible()`, re-pin to successor, record journal entry `recovery_action=version_remapped` with old and new version IDs. Resume from checkpoint. |
| Superseded, edge = `breaking` | `breaking` | Hard abort: `ABORTED_STALE`. Breaking means the successor's output/behavior differs; resuming on it would silently change the decision basis. |

The `backward_compatible` remap is the only non-abort path. It
requires:

1. The successor is `production` (D3-4d).
2. The successor is reachable via a chain of `backward_compatible`
   edges from the pinned version (D3-4c).
3. The journal records the remap: `recovery_action=version_remapped`,
   `pins_before`, `pins_after`. This is auditable (principle #4).

The remap is OPTIONAL, not mandatory. The orchestrator may choose to
abort even on `backward_compatible` if the run is safety-critical
(e.g., a `production_live` run near a kill-switch threshold). The
decision is policy: `policy_versions.orchestration.remap_on_backward_compatible`
(default: `true` for `production_replay` and `research`, `false` for
`production_live`).

## (c) Supersession DAG and resolve_compatible

Supersession chains form a directed acyclic graph (DAG). A version may
be superseded by at most one version (`superseded_by` is a single
UUID), but a version may supersede multiple predecessors (multiple old
versions point to the same successor). This handles the case where
two parallel strategy branches are merged into one.

```
resolve_compatible(version_id):
  current = version_id
  while current.superseded_by IS NOT NULL
      AND current.compatibility == 'backward_compatible':
    current = current.superseded_by
  return current
```

The walk stops at:

- A version with `superseded_by IS NULL` (the current production
  version) — return it.
- A version with `compatibility != 'backward_compatible'` (a `breaking`
  or `exact` edge) — return the version BEFORE the break. The walk
  cannot cross a breaking edge.

If `resolve_compatible(pinned_version)` returns a version that is
`production`, the remap is allowed. If it returns the pinned version
itself (no `backward_compatible` path to a production version), the
remap fails and the resume gate hard-aborts.

Example:

```
v1.0 (production, superseded_by=v1.1, compatibility=backward_compatible)
  └── v1.1 (production, superseded_by=v2.0, compatibility=breaking)
        └── v2.0 (production, superseded_by=NULL)

resolve_compatible(v1.0) → v1.1  (stops at the breaking edge to v2.0)
resolve_compatible(v1.1) → v1.1  (cannot cross breaking edge to v2.0)
resolve_compatible(v2.0) → v2.0  (current)
```

A run pinned to v1.0 may remap to v1.1 (backward_compatible). A run
pinned to v1.1 cannot remap to v2.0 (breaking) — it hard-aborts.

## (d) CI check: no two production versions without an edge

A CI check (run on every registry mutation) enforces:

```
For each (table, artifact_identity):
  production_versions = SELECT * FROM <table>
    WHERE status = 'production'
    AND <identity columns match>  -- e.g., same sub_role for prompts,
                                   -- same name+book for strategies

  IF COUNT(production_versions) > 1:
    REQUIRE: every pair has a supersession edge
             (one supersedes the other via superseded_by)
    AND: the edge has a compatibility value
```

This prevents the ambiguous state where two `production` versions
exist with no declared relationship. If the CIO promotes v2.0 while
v1.0 is still `production` (graceful cutover, line e), the
supersession edge MUST be declared at promotion time. The CI check
fails the promotion if the edge is missing.

"Artifact identity" per table:

| Table | Identity columns |
|-------|-----------------|
| `model_versions` | `(provider, tier)` |
| `prompt_versions` | `(sub_role)` |
| `strategy_versions` | `(name, book)` |
| `policy_versions` | `(scope)` |

## (e) Promotion rule: graceful cutover for breaking supersessions

When a new version supersedes an old one with `breaking` compatibility:

1. The new version is promoted to `production`.
2. The old version REMAINS `production` (not retired).
3. Both are `production` simultaneously — allowed because the
   supersession edge is declared (D3-4d).
4. New runs pin the new version (the orchestrator resolves
   `production` + not-yet-superseded).
5. In-flight runs pinned to the old version continue on it (their
   pin is immutable — checkpoint-and-replay.md D7-3).
6. The old version is retired only when:
   - no in-flight runs pin it (query: `workflow_runs` where
     `pins @> old_version_id` AND state is a progress state), AND
   - the 90-day deprecation window (line f) has elapsed.

This is graceful cutover: breaking changes do not abort in-flight
runs, and new runs use the new version. The overlap window is bounded
by the longest possible run duration (stage deadlines from
workflow-lifecycle.md, typically minutes) plus the 90-day
deprecation window.

## (f) Deprecation rule

A version may be retired (`status` → `retired`) when ALL of:

1. `superseded_by IS NOT NULL` (it has a successor).
2. `compatibility = 'breaking'` (the successor is not a drop-in).
3. No in-flight runs pin it (no `workflow_runs` in a progress state
   reference it in `pins`).
4. At least 90 days have elapsed since `superseded_by` was set.

The 90-day window is a safety margin: it ensures that any long-running
or paused research runs (which may pin a version for weeks) have
drained. After 90 days with no in-flight pins, the version is
retired. Retired versions are never deleted (principle #6) — they
remain queryable for audit/replay.

A version with `compatibility = 'backward_compatible'` or `exact` may
be retired immediately when no in-flight runs pin it — there is no
need for a deprecation window because the successor is compatible.

## What this document does NOT define

- Automated compatibility detection (the CIO declares compatibility
  at promotion time — this is a human judgment, principle #7).
- Migration code execution (Phase 14+).
- Registry API surface (Phase 9).
- UI for supersession chain visualization (Phase 10).
- How `migration_notes` is consumed by automated tooling (future; for
  now it is human-readable guidance).

## Phase boundary

This document amends `registry-schema.md` (Phase 3) by adding
`superseded_by`, `compatibility`, and `migration_notes` to all four
registry tables, and amends `checkpoint-and-replay.md` (Phase 7) by
grading the version-match resume gate. It does not define prompt
content (Phase 4), risk math (Phase 8), migration code (Phase 14+),
or the registry API (Phase 9).
