# SSE API Reference

## Overview

This document defines the Server-Sent Events (SSE) endpoints for
realtime streaming in Lumine Phase 9. SSE is the V1 realtime transport
(Decision D9-1). WebSocket is gated to future via Port/Adapter
replaceability.

SSE is used because the dashboard is a read-only institutional consumer:
it observes state, it does not send realtime commands. Commands go
through REST (`rest-api.md`).

## Endpoint catalog

| Endpoint | Event type | Scope | Frequency | Heartbeat |
|----------|-----------|-------|-----------|-----------|
| `GET /api/v1/streams/market-data` | `market_data` | `read:market` | ~1/sec (tick) | 5s |
| `GET /api/v1/streams/analyst-outputs` | `analyst_output` | `read:workflows` | Event-driven | 15s |
| `GET /api/v1/streams/ic-decisions` | `ic_decision` | `read:workflows` | Event-driven | 15s |
| `GET /api/v1/streams/cio-proposals` | `cio_proposal` | `read:workflows` | Event-driven | 15s |
| `GET /api/v1/streams/risk-assessments` | `risk_assessment` | `read:portfolio` | Event-driven | 15s |
| `GET /api/v1/streams/execution-orders` | `execution_order` | `read:portfolio` | Event-driven | 15s |

All SSE endpoints are `GET` requests. Authentication uses the same
HMAC-SHA256 API key scheme as REST (see `auth.md`).

## Event format

Each SSE event is a standard SSE frame:

```
id: {event_id}
event: {event_type}
data: {json_envelope}

```

The `data` field contains the common envelope (defined by Phase 9 for
the external API; distinct from the Phase 3 internal stream envelope):

```json
{
  "meta": {
    "api_version": "v1",
    "timestamp": "2026-08-01T14:30:00.123Z",
    "request_id": "stream-{stream_id}",
    "status": "ok"
  },
  "data": { },
  "error": null
}
```

The `id` field is the event ID used for `Last-Event-ID` reconnection.

## Subscription filtering

SSE is GET-only, so filtering happens via query parameters:

```
GET /api/v1/streams/market-data?symbol=XAUUSD
GET /api/v1/streams/analyst-outputs?workflow_run_id={run_id}
GET /api/v1/streams/ic-decisions?workflow_run_id={run_id}
GET /api/v1/streams/cio-proposals?workflow_run_id={run_id}
GET /api/v1/streams/risk-assessments?portfolio_id={id}
GET /api/v1/streams/execution-orders?symbol=XAUUSD&status=PENDING,ACTIVE
```

| Endpoint | Filters |
|----------|---------|
| `market-data` | `symbol` (required) |
| `analyst-outputs` | `workflow_run_id` (optional; omit for all active runs) |
| `ic-decisions` | `workflow_run_id` (optional) |
| `cio-proposals` | `workflow_run_id` (optional) |
| `risk-assessments` | `portfolio_id` (optional) |
| `execution-orders` | `symbol`, `status`, `portfolio_id` (all optional) |

Comma-separated values = OR within a field (`status=PENDING,ACTIVE`).

## Heartbeat

To keep connections alive through proxies and detect dead clients,
the server sends heartbeat comments at the interval listed per endpoint:

```
: heartbeat

```

A heartbeat is an SSE comment line (starts with `:`). It carries no
data and does not increment the event ID. Clients should not surface
heartbeats to the UI.

If no heartbeat is received within `2 × heartbeat_interval`, the client
should treat the connection as dead and reconnect.

## Reconnect contract

### Server side: `Last-Event-ID`

When a client reconnects, it sends the last received event ID via the
standard `Last-Event-ID` HTTP header:

```
GET /api/v1/streams/execution-orders?symbol=XAUUSD
Last-Event-ID: 17001
X-Lumine-API-Key: lk_...
X-Lumine-Timestamp: 1722501000
X-Lumine-Signature: a1b2c3...
```

The server replays missed events from the backing Redis stream
(Phase 1 stream catalog) up to a maximum retention window (default
5 minutes, configurable in Phase 11). Events older than the window
are dropped; the client receives a `stream_resumed` event with
`gap_detected: true` and continues from the current position.

### Client side: reconnect behavior

The client (browser `EventSource` or server-side consumer) must:

1. Send `Last-Event-ID` on every reconnect.
2. Backoff: 1s → 2s → 4s → 8s → max 30s.
3. Reset backoff to 1s after a connection stays open 30+ seconds.
4. On `404 Not Found`: do not reconnect (stream or resource does not exist).
5. On `401`/`403`: do not reconnect (auth invalid; retrying will not help).
6. On `429 Too Many Requests`: honor `Retry-After` header before reconnecting.
7. On `5xx`: reconnect with backoff.
8. On network error: reconnect with backoff.

The standard `EventSource` API implements most of this automatically;
the client only needs to handle `404`/`401`/`403` explicitly to avoid
infinite reconnect loops.

## Freshness

Every event carries `meta.timestamp` (ISO 8601 with milliseconds and
`Z` suffix). Clients use this to detect staleness without server-side
logic:

- If `now - meta.timestamp > 2 × heartbeat_interval`, the stream is stale.
- Stale streams should surface a degraded indicator in the UI (Phase 10).

## Stream lifecycle

| State | Meaning |
|-------|---------|
| `stream_open` | First event sent on connection. `data: {stream_id, started_at}`. |
| `stream_resumed` | Sent after `Last-Event-ID` reconnect. `data: {from_event_id, gap_detected}`. |
| Normal events | The event types listed in the catalog. |
| `stream_closed` | Sent before server closes the connection (graceful shutdown). `data: {reason}`. |

A stream may be closed by the server during graceful shutdown (Phase 7
graceful termination) or when the backing resource no longer exists
(e.g., a `workflow_run_id` reaches a terminal state).

## Connection limits

| Limit | Value | Source |
|-------|-------|--------|
| Max concurrent SSE connections per API key | 20 | Phase 11 config |
| Max concurrent SSE connections per host | 1000 | Phase 11 config |
| Event buffer per connection (missed events) | 1000 | Phase 11 config |
| Replay retention window | 5 minutes | Phase 11 config |

Concrete values are Phase 11 infrastructure decisions; the contract
surface (that these limits exist and are enforced) is fixed here.

## Backpressure

If a client cannot keep up with events, the server applies backpressure:

1. Buffer up to `event_buffer` events per connection.
2. If the buffer fills, send a `stream_dropped` event with
   `{reason: "client_too_slow", last_event_id}` and close the connection.
3. The client reconnects with `Last-Event-ID` to resume; events beyond
   the retention window are lost.

This prevents a slow client from blocking the producer (Phase 1 stream
consumer must never block the producer).

## What this document does NOT define

- SSE handler implementation (Phase 14+).
- Redis stream consumer internals (Phase 1 port/adapter).
- Concrete connection limits and buffer sizes (Phase 11 config).
- Frontend `EventSource` consumption patterns (Phase 10).
- WebSocket upgrade path (future, via Port/Adapter).

## Phase boundary

This document fixes the SSE endpoint surface, event format,
subscription filtering, reconnect contract, heartbeat, and backpressure
semantics. It does not define implementation, infrastructure limits, or
frontend consumption.