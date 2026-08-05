# ADR-0038 — Inter-agent message schema versioning

- **Status:** Accepted
- **Phase:** 04-communication-and-prompts
- **Date:** 2026-08-02
- **Owner:** architects
- **Supersedes:** —
- **Superseded by:** —

## Context

`proposal-schema.md` defines the CIO Proposer's output schema and marks
it `version: "v1"`. But every other inter-agent message — analyst-to-IC,
IC-to-CIO, RiskValidator verdict envelope — has no versioning contract. A
producer that adds a field or changes a type breaks consumers silently.
The pattern in `proposal-schema.md` must be generalized to all
inter-agent messages.

## Decision

Every inter-agent message carries `message_schema_version` (semver) and
`message_schema_name`. A `message_schema_versions` registry table pins each
schema (JSON Schema draft-07, `code_hash`, `compatibility` enum:
`backward` | `forward` | `full` | `none`). Compatibility policy: new
optional field = minor (backward-compatible); new required field, removed
field, or type change = major (breaking). Two CI checks guard: consumer
declaration (a consumer must declare the schema it expects) and producer
compatibility test (a producer emitting vN+1 must demonstrate vN consumers
still parse it, for minor bumps). Each stage's output pins the
`message_schema_version` in the reasoning trace and/or
`lineage_records.proposal`.

## Rationale

- Generalizing the `proposal-schema.md` pattern prevents silent consumer
  breakage across all inter-agent messages.
- Semver + compatibility enum makes the cutover path explicit: minor bumps
  are transparent; major bumps require staged, audited cutover.
- CI checks enforce that producers demonstrate backward compatibility
  before promotion.
- Pinning `message_schema_version` in lineage makes replay revalidate
  against the exact schema (principle #6).

## Consequences

- Positive: no silent consumer breakage on schema changes.
- Positive: replay revalidates messages against the pinned schema version.
- Negative: schema changes require a registry row and CI pass (intentional
  friction).
- Reversibility: schemas follow the standard supersession model.

## Cross-references

- Related ADRs: ADR-0015, ADR-0025, ADR-0044
- Implements principle(s): #6, #10
- Affects phases: 04, 03
- Source document: `../04-communication-and-prompts/inter-agent-message-versioning.md` (S23)
