# API Versioning

- **Status:** active
- **Owner:** architects
- **Last-reviewed:** 2026-08-02
- **Review-cadence:** 180

## Decision (D9-V1)
URL versioning: `/api/v1/...`. The major version is in the path and is the
only versioning surface clients depend on. Minor/patch changes are
backward-compatible and do not change the path.

## Breaking vs non-breaking
| Change | Breaking? | Version bump |
|--------|-----------|--------------|
| Add optional field to response | no | none |
| Add new endpoint | no | none |
| Remove a field | yes | major |
| Change field type | yes | major |
| Change semantics of existing field | yes | major |
| Change error code | yes | major |
| Add required request field | yes | major |

## Deprecation policy
- A deprecated `vN` runs in parallel with `vN+1` for at least 6 months.
- Deprecated endpoints emit a `Deprecation` and `Sunset` header (RFC 8594/7234 spirit).
- Removal requires: (a) Sunset date passed, (b) telemetry shows <1% traffic
  on the deprecated version, (c) ADR recording the removal.

## OpenAPI source of truth
- Generated from FastAPI: `/openapi.json` live; `docs/09-api/openapi.yaml`
  committed on every API PR.
- CI contract test: the committed `openapi.yaml` must match the live
  `/openapi.json` (drift = CI failure).
- Breaking-change detection: a CI job diffs the new OpenAPI against the
  committed one and flags removed/changed fields (openapi-diff or equivalent).

## SSE / streaming versioning
- SSE event payloads carry their own `schema_version` field (per
  `inter-agent-message-versioning.md` ADR-0038). The transport (`/api/v1/streams/...`)
  is URL-versioned like REST.

## Anti-patterns
- Header-based versioning for the URL surface (opaque to clients/tooling).
- "Just add a field, it's backward compatible" without OpenAPI diff review.
- Maintaining >2 major versions simultaneously (sunset aggressively).

## Phase boundary
This fixes the versioning contract. Endpoint details live in
`docs/09-api/rest-api.md` and `sse-api.md`; error envelope in `error-contract.md`.
