# Observability

## Overview

Metrics, logs, traces, dashboards, and alert rules for the V1 runtime, per
D11-4. Everything is self-hosted on the VPS; no telemetry leaves the node.

## Three pillars

| Pillar | Toolchain | Content |
|--------|-----------|---------|
| Metrics | Prometheus | Per-service `/metrics` scrape: tick latency, SSE connection count, order throughput, LLM token usage/cost per model, DB pool saturation, Redis stream lag, container CPU/memory vs limits, Caddy request rates |
| Logs | Loki + Promtail | Structured JSON logs from every container; labels: `service`, `level`, `trace_id` |
| Traces | OTel collector → Tempo | End-to-end spans: scheduler tick → committee debate → risk assessment → execution dispatch → MT5 ack |

## The trace_id contract (binding)

`trace_id` is one continuous key across the whole system:

- Every REST request and every scheduler-triggered decision cycle is
  assigned a `trace_id` at entry.
- The same value appears in: the Phase 9 error envelope returned to
  clients, all log lines, and all trace spans.
- The Phase 10 frontend ActivityLog displays `trace_id` (click to copy) —
  an operator can paste it into Grafana and land on the exact backend
  trace. This closes the loop required by Phase 9 `error-contract.md`
  traceability.

## Dashboards (Grafana)

- **Per-zone dashboards:** trade-core, bridge, workers, LLM gateway, data
  stores.
- **Trading dashboard:** equity, exposure, drawdown, SSE stream health
  (n/6 live, staleness per Phase 9 heartbeat semantics).
- **LLM cost dashboard (mandatory):** tokens per model, per agent, per
  day; daily cost vs threshold. Continues the Phase 4/6 cost-tracking
  requirement into operations.
- Access: `/grafana/*` behind Caddy IP allowlist (topology.md rule 2).

## Alert rules (Prometheus + Alertmanager)

**Critical (page operator, delivery < 1 minute):**

| Condition | Why |
|-----------|-----|
| `lumine-trade-core` down | Critical path halted |
| MT5 bridge stream timeout | Positions lose active management (broker-side SL/TP remains as safety net) |
| PostgreSQL not writable | No lineage → no trade (Phase 1 invariant) |
| Kill switch engaged | Operator must know immediately (also surfaces in UI, Phase 10) |
| Backup failed 2× consecutively | Silent data-loss risk (backup-dr.md) |
| Restore test failed | Backup is not a backup until verified |

**Warning:**

| Condition |
|-----------|
| SSE reconnect storms (repeated drops) |
| Daily LLM cost above threshold |
| Disk usage > 75% |
| Container memory > 85% of limit |
| Deploy `verify` job failure (build-deploy.md) |

Alert channel: Telegram and/or email — chosen at implementation; the
contract is delivery time (< 1 min critical), not the channel.

## Retention (VPS disk budget)

| Data | Retention |
|------|-----------|
| Metrics | 30 days |
| Logs | 30 days |
| Traces | 7 days |

## What this document does NOT define

- Concrete alertmanager receivers, Grafana provisioning JSON (Phase 14+).
- Metric naming conventions per service (Phase 14+, instrumentation code).
- SLO definitions and error-budget policy (Phase 13 acceptance criteria).

## Phase boundary

The observability architecture, trace_id contract, and alert obligations
are fixed here. Instrumentation code belongs to Phase 14+.
