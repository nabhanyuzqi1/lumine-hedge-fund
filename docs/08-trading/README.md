# Phase 8 — Trading Architecture

## Overview

Phase 8 defines how approved investment proposals become real trades. It covers
order lifecycle, MT5 integration, execution, and risk engine boundaries.

Phase 8 does NOT define: API design (Phase 9), dashboard (Phase 10),
infrastructure (Phase 11), or implementation code (Phase 14+).

## Documents

| Document | Purpose |
|----------|---------|
| `order-lifecycle.md` | Order state machine, transitions, audit trail |
| `mt5-integration.md` | Redis bridge, message schemas, EA responsibilities |
| `risk-engine.md` | Position sizing, stop loss, exposure limits, LLM assessment |
| `execution-engine.md` | Idempotency, retry policy, timeout, error classification |
| `decisions.md` | Locked decisions for Phase 8 |

## Phase Boundary

This phase fixes the order state machine, transition authority, audit
payload, MT5 bridge pattern, risk formula structure, and execution
idempotency. It does not define MQL5 EA code, Redis infrastructure,
risk math implementation, or production deployment.
