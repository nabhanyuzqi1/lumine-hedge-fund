# Phase 9 — API Design

## Overview

Phase 9 defines the external API contracts for the Lumine platform. It
consumes the internal stream catalog and port/adapter boundaries from
Phase 1, the stream payload schemas from Phase 3, the order lifecycle
and execution engine from Phase 8, and the workflow lifecycle and
observability contracts from Phase 7. It produces the REST and SSE
contracts consumed by the Phase 10 frontend and the Phase 8 backtest
engine.

Phase 9 does NOT write code. It fixes the contract surface: endpoints,
auth, envelopes, errors, versioning, and stream semantics. Implementation
lives in Phase 14+.

## Documents in this folder

| File | Purpose |
|------|---------|
| `decisions.md` | Locked Phase 9 decision log |
| `rest-api.md` | REST endpoint reference, envelope, resource hierarchy |
| `sse-api.md` | SSE endpoint reference, subscription filtering, reconnect contract |
| `auth.md` | HMAC-SHA256 API key scheme, scopes, key management |
| `error-contract.md` | Error codes, common envelope, HTTP status mapping |

## Decisions at a glance

| # | Decision | Rationale |
|---|----------|-----------|
| D9-1 | **SSE for realtime, REST for the rest** | Dashboard is read-only consumer; SSE gives built-in auto-reconnect, lower backend complexity. WebSocket gated to future via Port/Adapter. |
| D9-2 | **Hybrid REST + RPC** | Resources for CRUD (portfolio, orders, workflows, lineage, journal); RPC namespace for commands (trigger-workflow, kill-switch). |
| D9-3 | **Domain-namespaced endpoints** | `/api/v1/{domain}/` — portfolio, orders, workflows, lineage, market, journal, streams, admin, rpc. One FastAPI router per domain. |
| D9-4 | **HMAC-SHA256 API Key auth** | Service-to-service dominant use case; no session state; replay protection via timestamp window. Scopes per principal. |
| D9-5 | **URL-prefix versioning** | `/api/v1/` explicit, no header negotiation. Deprecation via `Sunset` + `X-Lumine-Deprecation` headers, minimum 90 days. |
| D9-6 | **Common envelope** | Every response (REST + SSE) wraps `meta` + `data` + `error`. Consistent with Phase 3 stream payload envelope. |
| D9-7 | **6 SSE endpoints** | market-data, analyst-outputs, ic-decisions, cio-proposals, risk-assessments, execution-orders. Remainder via REST polling. |
| D9-8 | **Scope-based API key access** | Per-key scope sets; 5 principals (AutoGen engine, MT5 bridge, risk engine, dashboard operator, backtest engine) each with fixed scopes. |

## What Phase 9 does NOT define

- Middleware or gateway implementation (Phase 14+).
- Rate limit values and throttling policy (Phase 11 infrastructure).
- Physical deployment topology, reverse proxy, CDN (Phase 11).
- Frontend consumption patterns or component contracts (Phase 10).
- WebSocket upgrade path (future, via Port/Adapter replaceability).
- Backtest API consumption details (Phase 8 owns the engine; Phase 9
  defines the contracts it calls).

## Phase boundary

This phase fixes the API contract surface. Implementation (FastAPI
routers, middleware, SSE handlers, HMAC verification) belongs to
Phase 14+.