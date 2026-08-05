# MT5 Integration

## Overview

This document defines how the Python backend communicates with MetaTrader 5.
The backend never touches MT5 directly; all execution goes through an Expert
Advisor (EA) running inside MT5.

## Decision: Redis Pub/Sub + Queue Bridge

The backend and MT5 EA communicate via Redis:

- **Command Queue** (`lpush`/`brpop`): Python pushes execution commands; EA
  pops and executes.
- **Response Pub/Sub** (`publish`/`subscribe`): EA publishes execution results;
  Python subscribes and updates state.

This is asynchronous, decoupled, and works across different machines
(backend on Linux VPS, MT5 on Windows VPS or local).

## Architecture

```
Python Backend (Execution Controller)
    |
    | LPUSH mt5:commands {order_id, action, symbol, volume, sl, tp, idempotency_key}
    v
Redis Queue
    |
    | BRPOP mt5:commands
    v
MT5 Expert Advisor (MQL5)
    |
    | OrderSend() / OrderClose()
    v
MT5 Server
    |
    | Fill/Error
    v
EA publishes to Redis Pub/Sub
    |
    | PUBLISH mt5:results {order_id, ticket, status, fill_price, error_code}
    v
Python Backend (subscribed)
```

## Message Schemas

### Command Message (Python → EA)

```json
{
  "command_id": "uuid",
  "order_id": "uuid",
  "action": "OPEN|CLOSE|MODIFY",
  "symbol": "XAUUSD",
  "volume": 0.01,
  "order_type": "BUY|SELL",
  "stop_loss": 1950.00,
  "take_profit": 1980.00,
  "idempotency_key": "uuid:attempt_1",
  "timestamp": "2026-07-31T21:00:00Z"
}
```

### Result Message (EA → Python)

```json
{
  "command_id": "uuid",
  "order_id": "uuid",
  "ticket": 123456789,
  "status": "FILLED|PARTIAL|REJECTED|ERROR",
  "fill_price": 1965.50,
  "fill_volume": 0.01,
  "error_code": 0,
  "error_message": "",
  "timestamp": "2026-07-31T21:00:05Z"
}
```

## EA Responsibilities

- Listen on `mt5:commands` queue (blocking pop with timeout).
- Validate command schema.
- Execute via `OrderSend()` or `OrderClose()`.
- Publish result to `mt5:results` channel.
- Handle partial fills by publishing multiple result messages.
- Never retry automatically; retry is a new command from Python.

## Python Responsibilities

- Generate idempotency key: `order_id:attempt_N`.
- Check Redis dedup before sending: `SET idempotency_key 1 NX EX 3600`.
- If key exists, skip sending and return previous result.
- Subscribe to `mt5:results` and update order state machine.
- Handle timeout: if no result in 30s, mark order FAILED and alert.

## Tradeoffs

| Decision | Rationale | Risk |
|----------|-----------|------|
| Redis bridge | Async, decoupled, cross-platform | Requires Redis running 24/7 |
| Pub/Sub for results | Real-time updates without polling | Message loss if Python offline; need persistence |
| Queue for commands | Guarantees delivery, supports multiple EAs | Single point of failure if Redis down |

## What This Document Does NOT Define

- MQL5 EA source code (Phase 14+)
- Redis persistence configuration (Phase 5 — `docs/05-data/redis-roles.md`)
- Failover Redis setup (Phase 11)
- Network security between Python and MT5 (Phase 12)

## Phase Boundary

This document fixes the Redis bridge pattern, message schemas, and EA/Python
responsibilities. It does not define EA code, Redis infrastructure, or
production deployment.
