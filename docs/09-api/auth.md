# Authentication & Authorization

## Overview

This document defines the authentication and authorization contract for
the Lumine Phase 9 API. Two authentication paths are supported:

1. **HMAC-SHA256 API Key** — for service-to-service calls (AutoGen engine,
   MT5 bridge, backtest engine, CLI tools). Decision D9-4.
2. **Session-based (JWT cookie)** — for browser-based dashboard operator
   access. The standard `EventSource` API does not support custom headers,
   so the dashboard operator authenticates via a login endpoint and receives
   a short-lived JWT stored in an httpOnly cookie. SSE endpoints accept
   this cookie alongside the HMAC header.

Phase 9 defines the contract surface: key format, signature scheme,
scopes, and key management. Implementation (middleware, key storage,
signature verification) lives in Phase 14+.

## Authentication scheme: HMAC-SHA256 API Key

Every request must carry three headers:

```
X-Lumine-API-Key: lk_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
X-Lumine-Timestamp: 1722501000
X-Lumine-Signature: a1b2c3d4e5f6...
```

| Header | Format | Purpose |
|--------|--------|---------|
| `X-Lumine-API-Key` | `lk_` + 32 hex chars | Identifies the key |
| `X-Lumine-Timestamp` | Unix seconds (UTC) | Replay protection |
| `X-Lumine-Signature` | Hex-encoded HMAC-SHA256 | Request integrity |

## Signature construction

```
payload = HTTP_METHOD + "\n" + request_path + "\n" + timestamp + "\n" + body_sha256
signature = HMAC-SHA256(api_secret, payload)
```

Where:
- `HTTP_METHOD` = uppercase (`GET`, `POST`, `DELETE`)
- `request_path` = path with query string (e.g. `/api/v1/orders?symbol=XAUUSD`)
- `timestamp` = same value as `X-Lumine-Timestamp` header
- `body_sha256` = hex SHA-256 of the request body (empty string for GET/DELETE)

The signature is hex-encoded lowercase.

### Example

```
POST /api/v1/orders
X-Lumine-API-Key: lk_a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4
X-Lumine-Timestamp: 1722501000
X-Lumine-Signature: 9f8e7d6c...
Content-Type: application/json

{"portfolio_id":"p1","symbol":"XAUUSD","side":"BUY","quantity":0.1}
```

```
payload = "POST\n/api/v1/orders\n1722501000\n" + sha256("{\"portfolio_id\":\"p1\",...}")
signature = hmac_sha256(api_secret, payload)
```

## Replay protection

- Server rejects requests where `|server_time - timestamp| > 300` (5 minutes).
- Server maintains a short-lived cache of seen `(api_key, timestamp, body_hash)`
  tuples within the valid window to reject exact replays.
- `EXPIRED_TIMESTAMP` error on stale requests (see `error-contract.md`).

This mirrors the idempotency and replay pattern from Phase 8
(`execution-engine.md`).

## API key format

```
lk_ + 32 hex chars
```

Example: `lk_a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4`

- Prefix `lk_` = "Lumine Key", makes keys greppable and identifiable in logs.
- 32 hex chars = 128 bits of entropy.
- Secret is a separate 64 hex char (256-bit) value shown once at creation.

## Scopes

Each key carries a scope set. Scopes are additive; a key can hold
multiple scopes.

| Scope | Grants |
|-------|--------|
| `read:market` | Market data REST + SSE |
| `read:portfolio` | Portfolio, positions, exposure, orders (read) |
| `read:workflows` | Workflow status, runs, journal |
| `read:lineage` | Lineage records |
| `read:journal` | Trade journal |
| `write:orders` | Create / cancel orders |
| `write:workflows` | Trigger workflow runs |
| `admin:kill_switch` | Engage kill switch, override proposals |
| `admin:keys` | Manage API keys |

Scopes are checked per-endpoint (see `rest-api.md` and `sse-api.md` for
the scope required by each endpoint). Missing scope returns
`403 INSUFFICIENT_SCOPE`.

## Principal-to-scope mapping

The following principals are defined for V1. Each principal gets a key
with the listed scopes.

| Principal | Scopes |
|-----------|--------|
| AutoGen workflow engine | `read:market`, `read:portfolio`, `read:workflows`, `write:workflows` |
| MT5 bridge | `read:market`, `write:orders`, `read:lineage` |
| Risk engine | `read:portfolio`, `read:lineage`, `admin:kill_switch` |
| Dashboard operator | `read:market`, `read:portfolio`, `read:workflows`, `read:lineage`, `read:journal`, `admin:kill_switch` |
| Backtest engine | `read:market`, `read:lineage`, `read:journal` |

New principals can be added in future phases without changing the
contract surface; the scope set is the contract, not the principal list.

## Dashboard operator session auth (browser `EventSource`)

The browser `EventSource` API used for SSE streams does not support
custom HTTP headers. The dashboard operator cannot send
`X-Lumine-API-Key`, `X-Lumine-Timestamp`, or `X-Lumine-Signature` on
an `EventSource` connection.

### Session flow

1. **Login**: `POST /api/v1/auth/login` accepts `{api_key, api_secret}` in
   the request body (over HTTPS). The server validates the HMAC key pair
   and returns a short-lived JWT (15-minute expiry) in an httpOnly,
   Secure, SameSite=Strict cookie named `lumine_session`.
2. **SSE connection**: The browser opens `EventSource` to the SSE endpoint.
   The `lumine_session` cookie is automatically sent by the browser.
   The SSE auth middleware validates the JWT and resolves scopes from the
   embedded principal.
3. **REST calls**: Dashboard REST calls (TanStack Query) send the same
   cookie. No HMAC signature computation in the browser.
4. **Refresh**: `POST /api/v1/auth/refresh` extends the session (cookie
   only, no body). The server issues a new JWT with a new expiry.

### JWT payload

```json
{
  "sub": "dashboard_operator",
  "scopes": ["read:market", "read:portfolio", "read:workflows", "read:lineage", "read:journal", "admin:kill_switch"],
  "iat": 1722501000,
  "exp": 1722501900,
  "jti": "uuid"
}
```

### Security constraints

- The JWT is signed with the same `HMAC_SECRET_KEY` as the API key HMAC
  secret derivation (configurable independently in production).
- The cookie is httpOnly (not accessible to JavaScript), Secure (HTTPS
  only), and SameSite=Strict.
- The login endpoint is rate-limited to 5 attempts per minute per IP.
- The `api_key` and `api_secret` never leave the browser's memory after
  login — they are not stored in localStorage, sessionStorage, or
  IndexedDB.
- The JWT is short-lived (15 min). If the session expires during an SSE
  connection, the stream is closed with a 401 event. The browser
  re-authenticates via the refresh endpoint.

### Service-to-service path unchanged

The HMAC-SHA256 header-based auth remains the sole path for all
non-browser principals: AutoGen engine, MT5 bridge, risk engine,
backtest engine, and CLI tools. The session cookie path is an
**additional** auth mechanism for the dashboard operator only.

## Key management

API keys are managed via admin REST endpoints:

```
POST   /api/v1/admin/keys        # Create key
GET    /api/v1/admin/keys        # List keys (masked)
DELETE /api/v1/admin/keys/{id}   # Revoke key
```

### Create key

```
POST /api/v1/admin/keys
X-Lumine-API-Key: lk_...  (caller must have admin:keys)
Content-Type: application/json

{
  "name": "autogen-engine-prod",
  "principal": "autogen_engine",
  "scopes": ["read:market", "read:portfolio", "read:workflows", "write:workflows"]
}
```

Response (secret shown once):

```json
{
  "meta": { "api_version": "v1", "timestamp": "...", "request_id": "...", "status": "ok" },
  "data": {
    "key_id": "k_8c2f4a1e",
    "api_key": "lk_a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4",
    "api_secret": "s_9f8e7d6c5b4a39281706f5e4d3c2b1a09f8e7d6c5b4a39281706f5e4d3c2b1a0",
    "name": "autogen-engine-prod",
    "principal": "autogen_engine",
    "scopes": ["read:market", "read:portfolio", "read:workflows", "write:workflows"],
    "created_at": "2026-08-01T14:30:00Z"
  },
  "error": null
}
```

- `api_secret` is returned exactly once. The server stores only a hash.
- Loss of the secret requires key revocation and re-creation.

### List keys

```
GET /api/v1/admin/keys
```

Returns keys with masked `api_key` (last 4 chars only) and no secret.

### Revoke key

```
DELETE /api/v1/admin/keys/{key_id}
```

Revocation is immediate. In-flight requests with the revoked key
continue (already validated); new requests return `401 INVALID_SIGNATURE`
on the next signature check (the key lookup fails).

## Key storage

- Server stores: `key_id`, `api_key` (for lookup), `secret_hash`
  (Argon2id), `scopes`, `principal`, `name`, `created_at`, `revoked_at`.
- Server never stores the plaintext secret.
- Physical schema is owned by Phase 5.

## Clock skew

Clients must sync their clock to a reliable source (NTP). The 5-minute
timestamp window tolerates moderate skew. Persistent skew is a client
bug, not a server concern.

The server exposes a time endpoint for skew calibration:

```
GET /api/v1/admin/time
```

Returns `{ "server_time": 1722501000, "iso": "2026-08-01T14:30:00Z" }`.
No auth required.

## What this document does NOT define

- Middleware implementation (Phase 14+).
- Key storage physical schema (Phase 5).
- OAuth2 / third-party integration (future, via Port/Adapter).
- Rate limit per key (Phase 11).
- mTLS for service-to-service (Phase 11/12 infrastructure decision).

## Phase boundary

This document fixes the authentication contract: key format, HMAC-SHA256
signature scheme, scope set, principal mapping, and key management
endpoints. It does not define implementation, storage schema, or
infrastructure-level transport security.