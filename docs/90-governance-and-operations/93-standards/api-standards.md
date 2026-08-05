# API Standards

- **Status:** active
- **Owner:** architects
- **Last-reviewed:** 2026-08-02
- **Review-cadence:** 180
- **Source:** promoted from `docs/09-api/`

## Versioning
- URL versioning: `/api/v1/...`. Major version in path.
- Breaking changes require a major bump + parallel `vN+1` support during cutover.
- See `docs/09-api/api-versioning.md` (ADR-0041*).

## OpenAPI
- Generated from FastAPI (`/openapi.json`); committed as
  `docs/09-api/openapi.yaml` on every API PR.
- CI contract test asserts routes match the committed OpenAPI.

## Error contract
- Uniform error envelope (see `docs/09-api/error-contract.md`).
- HTTP status reflects the category; the body carries machine-readable code.
- Idempotency: mutating endpoints accept `Idempotency-Key` header.

## Streaming (SSE)
- Per `docs/09-api/sse-api.md`: reconnect with `Last-Event-ID`; bounded
  replay window; heartbeats.
- WebSocket only where SSE is insufficient (justified in Phase 9).

## Auth
- HMAC-SHA256 request signing (Phase 9) for backend; short-lived tokens for
  frontend. Never pass secrets in URLs.

## Naming
- `snake_case` in JSON bodies (matches Python + DB); frontend adapts.
- ISO-8601 UTC timestamps everywhere; never local time.
