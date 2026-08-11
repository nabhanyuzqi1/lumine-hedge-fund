# ADR-0070 — OpenAPI contract: generated from FastAPI, checked in, CI-diffed

- **Status:** Accepted
- **Phase:** 15-implementation
- **Date:** 2026-08-11
- **Owner:** Chief AI Architect
- **Supersedes:** —
- **Superseded by:** —

## Context

`docs/09-api/api-versioning.md` requires a public OpenAPI contract, but
until Sprint 5 none existed. Two options were on the table:

1. **Hand-written `openapi.yaml`** — a curated, human-maintained document
   that may diverge from the actual FastAPI surface.
2. **Generated from `app.openapi()`** — a single source of truth derived
   from the router wiring itself.

Given the Phase 15 drift policy (`spec-reconciliation.md`: "docs that lie
destroy trust in the whole KB") and the CI gate on that reconciliation,
a hand-written contract would be the most dangerous documentation failure
mode: it would drift the moment a router changes.

## Decision

The OpenAPI document at `docs/09-api/openapi.yaml` is **generated** from
the FastAPI application factory (`backend/src/lumine/api/app.py`) via
`backend/scripts/generate_openapi.py`, which:

- builds the app with `create_app()`,
- dumps `app.openapi()` with `yaml.safe_dump(sort_keys=False, allow_unicode=True)`,
- writes the result to `docs/09-api/openapi.yaml`.

The artifact is **checked in** and a CI job (`openapi-diff`) regenerates
it and fails on any `git diff` (`--exit-code`), so the checked-in contract
and the running API cannot drift. `make openapi` regenerates locally; the
contract test `tests/contract/test_openapi_contract.py` pins the shape
(3.1.0, `/api/v1/` paths, all 9 routers, HMAC headers, envelope-shaped
error schemas) and additionally asserts the checked-in YAML is
byte-identical to a fresh generation.

## Alternatives considered

- **Hand-written contract** — rejected: guaranteed drift, violates the
  Phase 15 drift policy.
- **Generate at publish time only (no check-in)** — rejected: `docs/`
  is the contract store; consumers (CI, docs readers) must see the exact
  artifact that shipped.
- **OpenAPI 3.0.3 instead of 3.1** — FastAPI emits 3.1 natively; downgrade
  would add a transform with no consumer requirement.

## Consequences

- Every API change PR must include the regenerated YAML (CI enforces).
- The HMAC scheme appears as per-operation header parameters, not a
  `securitySchemes` entry, because auth is a dependency-based check
  (`authenticate_request`), not FastAPI `Security()` — documented in the
  contract test and accepted as the honest representation.
- Future OpenAPI consumers (SDK generation, mock servers) can consume the
  checked-in artifact without booting the app.
