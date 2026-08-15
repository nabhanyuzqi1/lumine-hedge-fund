# REST API Reference

## Overview

This document defines the REST endpoint surface for Lumine Phase 9.
All endpoints use the common envelope, URL-prefix versioning (`/api/v1/`),
and HMAC-SHA256 API key authentication (see `auth.md`).

## Base URL

```
https://{host}/api/v1
```

Concrete host and TLS termination are Phase 11 infrastructure decisions.

## Common envelope

Every JSON response uses the same envelope. This envelope is defined by
Phase 9 for the external API; it is distinct from the Phase 3 internal
stream envelope (`stream-payloads.md`) which carries events between
internal services:

```json
{
  "meta": {
    "api_version": "v1",
    "timestamp": "2026-08-01T14:30:00Z",
    "request_id": "550e8400-e29b-41d4-a716-446655440000",
    "status": "ok"
  },
  "data": { },
  "error": null
}
```

On error, `data` is `null` and `error` is populated (see
`error-contract.md`).

## Domain hierarchy

Endpoints are grouped by business domain. Each domain maps to one
FastAPI router and one OpenAPI tag group.

| Domain | Base path | Purpose |
|--------|-----------|---------|
| portfolio | `/api/v1/portfolio` | Portfolios, positions, exposure |
| orders | `/api/v1/orders` | Order lifecycle, history |
| workflows | `/api/v1/workflows` | Workflow runs, status, history |
| lineage | `/api/v1/lineage` | Decision lineage records |
| market | `/api/v1/market` | Market data, features, signals |
| journal | `/api/v1/journal` | Trade journal entries |
| streams | `/api/v1/streams` | SSE endpoints (see `sse-api.md`) |
| admin | `/api/v1/admin` | API key management |
| rpc | `/api/v1/rpc` | Commands: trigger-workflow, kill-switch |

## Portfolio domain

```
GET    /api/v1/portfolio
GET    /api/v1/portfolio/{portfolio_id}
GET    /api/v1/portfolio/{portfolio_id}/positions
GET    /api/v1/portfolio/{portfolio_id}/exposure
```

| Endpoint | Scope | Returns |
|----------|-------|---------|
| `GET /portfolio` | `read:portfolio` | List of portfolios |
| `GET /portfolio/{id}` | `read:portfolio` | Single portfolio with metrics |
| `GET /portfolio/{id}/positions` | `read:portfolio` | Open positions |
| `GET /portfolio/{id}/exposure` | `read:portfolio` | Exposure breakdown by symbol/asset class |

## Orders domain

```
GET    /api/v1/orders
POST   /api/v1/orders
GET    /api/v1/orders/{order_id}
DELETE /api/v1/orders/{order_id}
```

| Endpoint | Scope | Body / Returns |
|----------|-------|----------------|
| `GET /orders` | `read:portfolio` | List orders (filterable by `symbol`, `status`, `portfolio_id`) |
| `POST /orders` | `write:orders` | Create order. Body: `{portfolio_id, symbol, side, quantity, type, ...}`. Idempotency via `Idempotency-Key` header. |
| `GET /orders/{id}` | `read:portfolio` | Single order with full lifecycle |
| `DELETE /orders/{id}` | `write:orders` | Cancel pending order (Phase 8 order lifecycle) |

Order lifecycle states and transition authority are owned by Phase 8
(`order-lifecycle.md`); this API only exposes them.

## Workflows domain

```
GET    /api/v1/workflows
GET    /api/v1/workflows/{workflow_id}/runs
POST   /api/v1/workflows/{workflow_id}/runs
GET    /api/v1/workflows/{workflow_id}/runs/{run_id}
GET    /api/v1/workflows/runs/{run_id}/journal
```

| Endpoint | Scope | Returns |
|----------|-------|---------|
| `GET /workflows` | `read:workflows` | Registered workflow definitions |
| `GET /workflows/{id}/runs` | `read:workflows` | Run history (paginated) |
| `POST /workflows/{id}/runs` | `write:workflows` | Trigger new run. Body: `{symbol, context_ref?}` |
| `GET /workflows/{id}/runs/{run_id}` | `read:workflows` | Run status, current state, terminal state |
| `GET /workflows/runs/{run_id}/journal` | `read:workflows` | Workflow journal events (Phase 7 durable journal) |

Workflow states (12 progress + 4 terminal) are owned by Phase 7
(`workflow-lifecycle.md`); this API exposes them read-only.

## Lineage domain

```
GET    /api/v1/lineage
GET    /api/v1/lineage/{lineage_id}
```

| Endpoint | Scope | Returns |
|----------|-------|---------|
| `GET /lineage` | `read:lineage` | List lineage records (filterable by `symbol`, `portfolio_id`, date range) |
| `GET /lineage/{id}` | `read:lineage` | Single lineage record with full `proposal` JSONB (Phase 4 schema) |

Lineage records are the audit trail for every trade decision (Phase 3
`lineage_records` table).

## Market domain

```
GET    /api/v1/market/quotes/{symbol}
GET    /api/v1/market/features/{symbol}
GET    /api/v1/market/signals/{symbol}
```

| Endpoint | Scope | Returns |
|----------|-------|---------|
| `GET /market/quotes/{symbol}` | `read:market` | Latest quote snapshot (bid/ask/spread) |
| `GET /market/features/{symbol}` | `read:market` | Latest computed features (Phase 2 feature engineering output) |
| `GET /market/signals/{symbol}` | `read:market` | Latest signals for the symbol |

These are REST-polling endpoints. For realtime market data, use the
SSE endpoint (`sse-api.md`).

## Journal domain

```
GET    /api/v1/journal
GET    /api/v1/journal/{entry_id}
```

| Endpoint | Scope | Returns |
|----------|-------|---------|
| `GET /journal` | `read:journal` | Journal entries (filterable by `symbol`, `portfolio_id`, date range) |
| `GET /journal/{id}` | `read:journal` | Single journal entry |

The trade journal is owned by Phase 8; this API exposes it read-only.
Realtime journal updates are not exposed via SSE in V1.

## Admin domain

```
POST   /api/v1/admin/keys
GET    /api/v1/admin/keys
DELETE /api/v1/admin/keys/{key_id}
```

| Endpoint | Scope | Returns |
|----------|-------|---------|
| `POST /admin/keys` | `admin:keys` | Create key. Returns `{key_id, api_key, api_secret}` — secret shown once. |
| `GET /admin/keys` | `admin:keys` | List keys (masked, no secrets) |
| `DELETE /admin/keys/{id}` | `admin:keys` | Revoke key immediately |

See `auth.md` for key format, scopes, and signature scheme.

## RPC domain

```
POST   /api/v1/rpc/trigger-workflow
POST   /api/v1/rpc/kill-switch
POST   /api/v1/rpc/override-proposal
```

| Endpoint | Scope | Body / Returns |
|----------|-------|----------------|
| `POST /rpc/trigger-workflow` | `write:workflows` | `{workflow_id, symbol, context_ref?}`. Same effect as `POST /workflows/{id}/runs`, exposed under rpc for command clarity. |
| `POST /rpc/kill-switch` | `admin:kill_switch` | `{reason, tier: "global"\|"book"\|"strategy", target?: {book, strategy}}`. Engages the tiered kill switch defined in Phase 2 (D2-5: global + book + strategy). Tier-appropriate termination semantics are owned by Phase 7 (D7-9). Returns `{engaged: true, tier, timestamp}`. |
| `POST /rpc/override-proposal` | `admin:kill_switch` | `{lineage_id, override_reason}`. Manual CIO override on an existing proposal (Phase 4 override authority). |

RPC endpoints are commands, not resources. They return the common
envelope but do not represent a RESTful resource.

## Pagination

List endpoints support cursor-based pagination:

```
GET /api/v1/orders?limit=50&cursor=eyJpZCI6...
```

Response envelope for paginated lists:

```json
{
  "meta": { "api_version": "v1", "timestamp": "...", "request_id": "...", "status": "ok" },
  "data": {
    "items": [ ],
    "cursor": "eyJpZCI6...", 
    "has_more": true
  },
  "error": null
}
```

- `limit`: 1–200, default 50
- `cursor`: opaque base64 token; pass back to fetch next page
- `has_more`: `false` on last page

## Idempotency

Write endpoints (`POST`, `DELETE`) accept an `Idempotency-Key` header.
If the same key is reused within the dedup window (1 hour, matching
Phase 8 `execution-engine.md` Redis TTL), the original response is
returned without re-executing the operation. Duplicate keys on different
request bodies return `409 CONFLICT`.

```
POST /api/v1/orders
Idempotency-Key: 8c2f4a1e-...
Content-Type: application/json
X-Lumine-API-Key: lk_...
X-Lumine-Timestamp: 1722501000
X-Lumine-Signature: a1b2c3...
```

This aligns with the idempotency pattern defined in Phase 8
(`execution-engine.md`).

## Filtering and sorting

List endpoints support query parameter filtering:

```
GET /api/v1/orders?symbol=XAUUSD&status=FILLED,ACTIVE&sort=-created_at&limit=50
GET /api/v1/lineage?portfolio_id={id}&from=2026-07-01T00:00:00Z&to=2026-08-01T00:00:00Z
```

- Comma-separated values = OR within a field (`status=FILLED,ACTIVE`)
- `sort=-field` = descending, `sort=field` = ascending
- Date filters use ISO 8601 with `Z` suffix

## What this document does NOT define

- Middleware implementation (Phase 14+).
- Rate limit values (Phase 11).
- Exact request/response payload schemas for every resource (those are
  owned by their producing phases: Phase 4 for proposals, Phase 7 for
  workflow runs, Phase 8 for orders).
- Frontend consumption patterns (Phase 10).

## Phase boundary

This document fixes the REST endpoint surface, common envelope,
pagination, and idempotency contract. It does not define implementation,
rate limits, or payload schemas owned by other phases.

---

## Implemented Surface Reconciliation (2026-08-14)

The sections above are the Phase 9 contract as designed. The table below
records the **actual surface served by `backend/src/lumine/api/routers/*`
(verified against source + `docs/09-api/openapi.yaml`, which is regenerated
byte-identical from code)**. Divergences are deliberate implementation
decisions to satisfy the frontend client contracts (`frontend/src/lib/api/`)
and are tracked in `docs/15-implementation/deviation-log.md`.

### Implemented endpoints (per domain)

| Domain | Implemented (under `/api/v1`) |
|--------|-------------------------------|
| portfolio | `GET /portfolio/summary`, `POST /portfolio/{portfolio_id}/simulate`, `GET /portfolio/positions`, `GET /portfolio/positions/{position_id}`, `GET /portfolio/exposure` — single-default-portfolio (`portfolio_id="default"`); `{id}` variants + CRUD + export **belum** ada |
| orders | `GET /orders`, `GET /orders/{order_id}`, `POST /orders`, `PATCH /orders/{order_id}` (modify: `{price?, volume?}` min 1), `DELETE /orders/{order_id}` (cancel) — history + bulk status **belum** ada |
| workflows | `GET /workflows` (PaginatedList[WorkflowRun]), `GET /workflows/{run_id}`, `POST /workflows` — **bukan** `{workflow_id}/runs` hierarchy dari spec |
| lineage | `GET /lineage`, `GET /lineage/{lineage_id}` — sesuai spec |
| market | `GET /market/bars`, `GET /market/signals` (global, paginated), `GET /market/quote/{symbol}`, `GET /market/quotes?symbols=`, `GET /market/ohlcv/{symbol}?timeframe&limit&since`, `GET /market/symbol/{symbol}`, `GET /market/symbols`, `GET /market/volatility/{symbol}?window`, `GET /market/correlation?symbols&window`, `GET /market/spread/{symbol}?period`, `GET /market/session/{symbol}`, `GET /market/features/{symbol}` — **path `quote/{symbol}` (singular) dan batch `quotes` berbeda dari spec `quotes/{symbol}`**; signals per-symbol belum |
| journal | `GET /journal`, `GET /journal/{entry_id}` — sesuai spec |
| streams | 6 SSE channel: `market-data`, `analyst-outputs`, `ic-decisions`, `cio-proposals`, `risk-assessments`, `execution-orders` (lihat `sse-api.md`) |
| admin | `GET/POST /admin/keys`, `DELETE /admin/keys/{key_id}`, `GET/POST /admin/kill-switch` — kill-switch menerima `{armed, reason, tier?}` dan persist tier di Redis |
| rpc | `POST /rpc/run-decision-cycle`, `POST /rpc/halt-trading`, `POST /rpc/resume-trading`, `POST /rpc/cancel-order` — **nama command berbeda dari spec** (`trigger-workflow`, `kill-switch`, `override-proposal`); kill-switch pindah ke `/admin/kill-switch`; semua command balas `accepted` (belum dispatch ke worker) |

### Divergensi kontrak (spec vs implemented)

| Spec (rest-api.md) | Implemented | Catatan |
|--------------------|-------------|---------|
| `GET /market/quotes/{symbol}` | `GET /market/quote/{symbol}` + `GET /market/quotes?symbols=` (batch) | Frontend client contract (`marketClient.ts`) |
| `GET /market/signals/{symbol}` | `GET /market/signals` (global) | Per-symbol pending (GAP B-06) |
| Workflows `{workflow_id}/runs` hierarchy | flat `/workflows/{run_id}` | Frontend `useRun` |
| `POST /rpc/kill-switch {reason, tier, target?}` | `POST /admin/kill-switch {armed, reason, tier?}` | Tier dipersingkat ke global/book/strategy; `target` belum |
| Cursor pagination (`cursor`, `has_more`) | offset/limit (`PaginatedList {items, total, limit, offset}`) | Frontend hooks memetakan offset → cursor page |
| `POST /rpc/trigger-workflow` / `override-proposal` | belum ada (diganti `run-decision-cycle` dkk.) | — |

### Sumber kebenaran

- Machine-readable contract: `docs/09-api/openapi.yaml` (regenerated from code; test `test_checked_in_contract_matches_generated_schema`).
- Frontend expectations: `docs/15-implementation/sprint-evidence/FRONTEND-API-SPECS.md`.
- Gap & status: `docs/15-implementation/IMPLEMENTATION-GAP-INVENTORY.md`.