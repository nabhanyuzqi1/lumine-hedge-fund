# Execution Engine

## Overview

This document defines how Lumine sends orders to MT5 reliably, without
duplicates, and with clear failure handling. The Execution Engine is the
only component that may transition orders from PENDING to FILLED/FAILED.

## Decision: Idempotency Key + Redis Dedup

Every execution attempt gets an idempotency key:
`idempotency_key = "{order_id}:{attempt_number}"`

Before sending to MT5, the Execution Controller checks Redis:
```
SET idempotency_key 1 NX EX 3600
```

If the key already exists, the command was already sent; skip and return
the previous result.

## Execution Flow

```
Order in PENDING state
    |
    v
Execution Controller
    |---> Generate idempotency_key
    |---> Check Redis dedup
    |---> If duplicate: return cached result
    |---> If new: LPUSH to mt5:commands
    |---> Wait for result on mt5:results (30s timeout)
    |---> On FILLED: update state to FILLED
    |---> On PARTIAL: update state to PARTIAL_FILL, wait for more
    |---> On ERROR/timeout: update state to FAILED, set reason
```

## Retry Policy

- **No automatic retry.** A FAILED order stays FAILED.
- Human or monitoring system decides to retry.
- Retry creates a **new order** with `retry_of = original_order_id`.
- The new order gets a new idempotency key sequence.

## Timeout Handling

| Scenario | Timeout | Action |
|----------|---------|--------|
| No result from EA | 30 seconds | Mark FAILED, reason="MT5 timeout" |
| Partial fill stalled | 60 seconds | Mark PARTIAL_FILL, alert Position Manager |
| Redis connection lost | 5 seconds | Mark FAILED, reason="Redis unavailable" |

## Error Classification

| Error Code | Category | Action |
|------------|----------|--------|
| 10004 | Requote | Retry allowed (manual) |
| 10006 | Request rejected | No retry |
| 10013 | Invalid request | No retry |
| 10014 | Invalid volume | No retry |
| 10015 | Invalid price | Retry allowed (manual) |
| 10016 | Invalid stops | No retry |
| 10018 | Market closed | No retry |
| 10019 | No money | No retry |
| 10021 | Price off | Retry allowed (manual) |

## What This Document Does NOT Define

- MQL5 EA implementation (Phase 14+)
- Redis connection pooling (Phase 11)
- Alerting/monitoring integration (Phase 10/11)
- Order routing to multiple brokers (future)

## Phase Boundary

This document fixes the idempotency mechanism, retry policy, timeout rules,
and error classification. It does not define EA code, infrastructure, or
monitoring dashboards.
