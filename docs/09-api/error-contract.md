# Error Contract

## Overview

This document defines the error contract for the Lumine Phase 9 API.
All errors use the common envelope with a structured `error` object and
a mapping to HTTP status codes. The contract is the same for REST and
SSE (SSE surfaces errors as terminal events before closing the
connection).

## Error envelope

On error, the common envelope has `data: null` and a populated `error`:

```json
{
  "meta": {
    "api_version": "v1",
    "timestamp": "2026-08-01T14:30:01Z",
    "request_id": "550e8400-e29b-41d4-a716-446655440000",
    "status": "error"
  },
  "data": null,
  "error": {
    "code": "INVALID_SIGNATURE",
    "message": "HMAC signature does not match body + timestamp",
    "details": {},
    "trace_id": "abc123"
  }
}
```

| Field | Type | Meaning |
|-------|------|---------|
| `code` | string | Stable machine-readable error code (enum below) |
| `message` | string | Human-readable explanation, safe to log and display |
| `details` | object | Optional structured details (field errors, validation failures) |
| `trace_id` | string | Correlates to logs/traces (Phase 7 observability) |

`meta.status` is `"error"` on any error response.

## HTTP status mapping

| HTTP | `error.code` | When |
|------|-------------|------|
| 400 | `INVALID_REQUEST` | Body or query params malformed |
| 400 | `VALIDATION_FAILED` | Schema validation failed (see `details`) |
| 401 | `MISSING_AUTH` | Auth headers absent |
| 401 | `INVALID_SIGNATURE` | HMAC signature does not match |
| 401 | `EXPIRED_TIMESTAMP` | Timestamp outside 5-minute window |
| 401 | `REPLAY_DETECTED` | Exact replay (same key, timestamp, body hash) within the window |
| 401 | `REVOKED_KEY` | API key has been revoked |
| 403 | `INSUFFICIENT_SCOPE` | Key lacks required scope |
| 403 | `KILL_SWITCH_ACTIVE` | Write blocked by platform kill switch (Phase 1/7/8) |
| 404 | `NOT_FOUND` | Resource does not exist |
| 200 | `DUPLICATE_IDEMPOTENCY` | Idempotency key reused with same body — original success response returned with `meta.idempotent_replay: true` |
| 409 | `CONFLICT` | Idempotency key reused with different body |
| 422 | `UNPROCESSABLE` | Request valid but cannot be processed (e.g. invalid state transition) |
| 429 | `RATE_LIMITED` | Rate limit exceeded |
| 500 | `INTERNAL_ERROR` | Unhandled server error |
| 503 | `SERVICE_UNAVAILABLE` | Dependency down (DB, Redis, MT5 bridge) |
| 503 | `DEGRADED_MODE` | Operating in degraded mode (Phase 7 recovery) |
| 504 | `UPSTREAM_TIMEOUT` | Upstream dependency timed out |

## Error code catalog

### Auth errors (401)

```json
{
  "error": {
    "code": "INVALID_SIGNATURE",
    "message": "HMAC signature does not match body + timestamp",
    "details": { "expected_prefix": "a1b2c3" },
    "trace_id": "abc123"
  }
}
```

- `MISSING_AUTH` — one or more of `X-Lumine-API-Key`, `X-Lumine-Timestamp`,
  `X-Lumine-Signature` is absent.
- `INVALID_SIGNATURE` — signature does not match recomputed value.
- `EXPIRED_TIMESTAMP` — `|server_time - timestamp| > 300`.
- `REVOKED_KEY` — key exists in revocation list.

### Authorization errors (403)

- `INSUFFICIENT_SCOPE` — key is valid but lacks the scope required by
  the endpoint. `details.required_scopes` lists what was needed.
- `KILL_SWITCH_ACTIVE` — write endpoint blocked because kill switch is
  engaged. Read endpoints remain available. `details.reason` carries the
  kill-switch reason. Returned as 403 (not 503) because the platform is
  intentionally refusing writes, not unavailable.

### Request errors (400)

```json
{
  "error": {
    "code": "VALIDATION_FAILED",
    "message": "Request body failed validation",
    "details": {
      "fields": [
        { "field": "quantity", "issue": "must be > 0" },
        { "field": "symbol", "issue": "unsupported symbol" }
      ]
    },
    "trace_id": "abc123"
  }
}
```

- `INVALID_REQUEST` — malformed JSON, missing required fields, type errors.
- `VALIDATION_FAILED` — schema validation failed; `details.fields` lists
  per-field issues.

### State errors (404, 409, 422)

- `NOT_FOUND` — resource ID does not exist.
- `CONFLICT` — idempotency key reused with a different request body.
  The original response is NOT returned; the client must use a new key.
- `DUPLICATE_IDEMPOTENCY` — idempotency key reused with the same body.
  The server returns HTTP 200 with the original success envelope plus
  `meta.idempotent_replay: true`. This is a success replay, not an
  error; the client should treat it as success.
- `UNPROCESSABLE` — request is valid but cannot be applied (e.g.
  cancelling an already-filled order, triggering a workflow for a symbol
  with an active run). `details.reason` explains.

### Rate limit (429)

```json
{
  "error": {
    "code": "RATE_LIMITED",
    "message": "Rate limit exceeded",
    "details": { "limit": 100, "window": "1m", "retry_after": 12 },
    "trace_id": "abc123"
  }
}
```

- `Retry-After` header set to seconds until reset.
- `details.retry_after` mirrors the header for programmatic access.

### Server errors (500, 503, 504)

- `INTERNAL_ERROR` — unhandled exception. `trace_id` is the primary
  debugging handle. `message` is generic ("Internal server error") to
  avoid leaking internals; details go to logs (Phase 7 observability).
- `SERVICE_UNAVAILABLE` — required dependency is down (PostgreSQL,
  Redis, MT5 bridge). `details.dependency` names the failed component.
- `DEGRADED_MODE` — platform is running in degraded mode per Phase 7
  recovery (e.g. cost breaker engaged, debate discarded). The request
  may succeed on retry; `details.degrade_kind` explains.
- `UPSTREAM_TIMEOUT` — upstream dependency exceeded its deadline
  (Phase 8 timeout table, Phase 7 deadline).

## SSE error events

SSE endpoints surface errors as terminal events before closing the
connection:

```
event: stream_error
data: {"meta": {..., "status": "error"}, "data": null, "error": {"code": "KILL_SWITCH_ACTIVE", ...}}

```

After a `stream_error` event, the server closes the connection. Client
reconnect behavior follows `sse-api.md`:

- `404` / `401` / `403` codes → do not reconnect.
- `429` → honor `Retry-After`.
- `5xx` codes → reconnect with backoff.
- `DEGRADED_MODE` → reconnect with backoff (may recover).

## Idempotency conflict handling

| Scenario | HTTP | Behavior |
|----------|------|----------|
| Same key, same body, within 1h | 200 | Return original success envelope with `meta.idempotent_replay: true` |
| Same key, different body | 409 | Reject with `CONFLICT`; client must use new key |

The duplicate-key-same-body case is a success: the original operation
already completed, so the server returns the original success envelope
(`meta.status: "ok"`, `data` populated) with an added marker
`meta.idempotent_replay: true` so the client can distinguish "new
operation" from "replayed response".

## Error traceability

Every error carries a `trace_id`. This ID is:

- Returned in the `error.trace_id` field.
- Logged with the request (Phase 7 structured logs).
- Emitted as a span attribute on the trace (Phase 7 traces).
- Stable across the request lifecycle.

Operators can grep logs/traces by `trace_id` to find the full context
of any failure. This closes the loop with Phase 7 observability:
telemetry and the journal agree (journal wins), and the API error is a
projection of the same underlying event.

## Kill switch interaction

When the kill switch is engaged (Phase 1/7/8):

- All write endpoints return `403 KILL_SWITCH_ACTIVE`.
- All read endpoints remain available.
- SSE `execution-orders` stream continues (orders may still transition
  to terminal states from the kill switch).
- `POST /api/v1/rpc/kill-switch` itself returns 200 (it is the command
  that engages the switch, not blocked by it).

This aligns with Phase 7: kill switch terminates active runs at the
next LLM call boundary and blocks new writes.

## What this document does NOT define

- Exact validation rules per endpoint (owned by producing phases).
- Rate limit thresholds (Phase 11).
- Log/trace backend storage (Phase 11).
- Client retry policy beyond SSE (Phase 10 frontend concern).

## Phase boundary

This document fixes the error contract: envelope, code catalog, HTTP
mapping, SSE error events, idempotency conflict handling, and
traceability. It does not define validation rules, rate limits, or
telemetry infrastructure.