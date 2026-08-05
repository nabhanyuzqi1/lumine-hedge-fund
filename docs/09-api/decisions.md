# Phase 9 — Locked Decisions

## Decision log

| # | Decision | Rationale |
|---|----------|-----------|
| D9-1 | **SSE for realtime streams, REST for the rest** | Dashboard is a read-only institutional consumer — it observes, it does not send realtime commands. SSE gives built-in `Last-Event-ID` reconnect, standard `EventSource` API in every browser, and lower backend complexity than WebSocket. If mobile bidirectional streaming is needed later, the transport is swapped behind the same Port without changing the contract (Phase 1 replaceability principle). |
| D9-2 | **Hybrid REST + RPC endpoint style** | Portfolio, orders, workflows, lineage, journal, and market data fit the resource model naturally (CRUD with clear nouns). Trigger-workflow, kill-switch, and manual override are commands — they are not resources. A dedicated `/api/v1/rpc/` namespace keeps commands explicit without forcing artificial resource modeling. Both paths share the same auth middleware, envelope, and OpenAPI spec. |
| D9-3 | **Domain-namespaced endpoint hierarchy** | `/api/v1/{domain}/` groups endpoints by business domain: portfolio, orders, workflows, lineage, market, journal, streams, admin, rpc. One FastAPI router per domain, one OpenAPI tag per domain. Scales cleanly when XAUUSD expands to multi-asset, and lets each domain evolve independently within the same API version. |
| D9-4 | **HMAC-SHA256 API Key authentication** | Service-to-service is the dominant use case in V1: AutoGen workflow engine → API, MT5 bridge → API, risk engine → API. HMAC-SHA256 with timestamp window gives request-level integrity, replay protection, and zero session state — all without a token endpoint or refresh cycle. Dashboard operators use the same key scheme with different scopes. OAuth2 for third-party integration is gated to future via Port/Adapter. |
| D9-5 | **URL-prefix API versioning** | `/api/v1/` is explicit, unambiguous, and requires no header negotiation. Deprecation policy: `Sunset` HTTP header + `X-Lumine-Deprecation` custom header, minimum 90-day notice before a version is removed. Multiple versions can coexist behind the reverse proxy (Phase 1 port pattern). |
| D9-6 | **Common envelope for all responses** | Every response — REST JSON body and SSE event `data` field — uses a `{meta, data, error}` envelope. This envelope is defined by Phase 9 for the external API; it is distinct from the Phase 3 internal stream envelope (`event_id, ts, schema_version, book, strategy_id, lineage_id, payload`) which carries events between internal services. REST adds HTTP status codes; SSE adds event type strings. The envelope is the contract surface; internal payload shapes are owned by their respective phases. |
| D9-7 | **6 SSE endpoints, 3 REST-polling** | `market_data` streams live prices; `analyst_outputs`, `ic_decisions`, `cio_proposals` stream committee reasoning in realtime; `risk_assessments` and `execution_orders` stream state changes. `features`, `signals`, and `trade_journal` are REST-polled — they are either technical/on-demand or historical/queryable. |
| D9-8 | **Scope-based API key access** | Each key carries a scope set (`read:market`, `write:orders`, `admin:kill_switch`, etc.). The principal-to-scope mapping is fixed in this phase: AutoGen engine, MT5 bridge, risk engine, dashboard operator, and backtest engine each get a defined scope set. Key management is via admin REST endpoints. |

## Principles honored

- **#1 Architecture before code**: contracts before routers; no implementation.
- **#4 Evidence before capital**: API is the evidence pipeline — every trade decision, order, and risk assessment flows through versioned, auditable endpoints.
- **#6 Reproducibility before adaptation**: HMAC signatures, idempotency keys, and explicit versioning make every API interaction replayable and auditable.
- **#9 Replaceability**: HMAC can be swapped for OAuth2; SSE can be swapped for WebSocket; REST can be swapped for gRPC — all behind the same Port interface without changing internal contracts.
- **#10 Safe state by default**: invalid auth → 401 without touching internal state; invalid request → 400 with structured error; kill-switch → `403 KILL_SWITCH_ACTIVE` on all write endpoints (intentional refusal, not unavailability).

## Phase boundary respected

Phase 9 fixes API contracts: endpoints, auth, envelopes, errors, versioning,
and SSE semantics. It does NOT define: middleware implementation (Phase 14+),
rate limit values (Phase 11), deployment topology (Phase 11), frontend
consumption (Phase 10), or WebSocket upgrade path (future).