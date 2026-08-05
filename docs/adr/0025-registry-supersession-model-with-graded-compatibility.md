# ADR-0025 — Registry supersession model with graded compatibility

- **Status:** Accepted
- **Phase:** 03-agents-and-contracts
- **Date:** 2026-08-02
- **Owner:** architects
- **Supersedes:** —
- **Superseded by:** —

## Context

The registry schema models version supersession as binary — a version is
either `production` or `retired`. Reality is graded: a new prompt version
may be a drop-in replacement (output schema unchanged), a
backward-compatible tweak (added fields, old consumers still work), or a
breaking change (schema reshape, requires remapping). Treating all
supersessions as equal forces either over-cautious hard aborts on every
resume or unsafe silent remaps.

## Decision

Each registry version row gains `superseded_by` (UUID, nullable),
`compatibility` enum (`exact` | `backward_compatible` | `breaking`), and
`migration_notes` (TEXT). Resume gate semantics (D7-8): `exact` mismatch →
hard abort; `backward_compatible` → may remap to successor with a journal
entry; `breaking` → hard abort. Supersession chains form a DAG;
`resolve_compatible()` walks the chain via `backward_compatible` edges. CI
checks no two `production` versions coexist without an explicit
compatibility edge. A `breaking` supersession requires graceful cutover
(old version stays `production` until in-flight runs drain).

## Rationale

- Graded compatibility avoids over-cautious aborts on safe remaps.
- The DAG + `resolve_compatible()` makes the remap path deterministic and
  auditable.
- CI check prevents ambiguous dual-production states.
- Graceful cutover for breaking changes does not abort in-flight runs.

## Consequences

- Positive: backward-compatible version bumps can remap without losing the
  run.
- Positive: breaking changes are explicit and staged.
- Negative: the CIO must declare compatibility at promotion time (human
  judgment, principle #7).
- Reversibility: the compatibility enum is extensible; existing edges are
  immutable.

## Cross-references

- Related ADRs: ADR-0006, ADR-0007
- Implements principle(s): #6, #7, #9
- Affects phases: 03, 07
- Source document: `../03-agents-and-contracts/registry-supersession-model.md` (S17)
