# Audit Log & Security Monitoring

## Overview

Security audit and monitoring architecture per D12-6. Two complementary
paths — structured PostgreSQL audit trail for queryable evidence, and
Loki structured logs for operational correlation via `trace_id`.
Prometheus alerting on security anomalies.

## Dual logging architecture

| Path | Technology | Purpose | Retention |
|------|-----------|---------|-----------|
| Security event log | PostgreSQL (`security_events`) | Queryable, structured audit trail of security-relevant events | 90 days |
| Structured logs | Loki + Promtail | Operational logs with `security=true` label, correlated via `trace_id` | 30 days (D11-4) |

## Security event log

### Schema

| Column | Type | Constraint | Description |
|--------|------|------------|-------------|
| `id` | UUID | PK, DEFAULT gen_random_uuid() | Unique event identifier |
| `timestamp` | TIMESTAMPTZ | NOT NULL, DEFAULT now() | When the event occurred |
| `event_type` | security_event_type | NOT NULL | Event category (see enum below) |
| `actor` | VARCHAR(128) | NOT NULL | Who performed the action |
| `target` | VARCHAR(256) | | What was acted upon |
| `detail` | JSONB | DEFAULT '{}' | Additional context (reason, trace_id, old/new values, IP) |
| `source_ip` | INET | | Originating IP address |
| `trace_id` | UUID | | Correlation with Tempo traces and Loki logs |

### Event type enum

```sql
CREATE TYPE security_event_type AS ENUM (
    'auth_success',
    'auth_failure',
    'kill_switch_engage',
    'kill_switch_disengage',
    'order_cancel_manual',
    'proposal_override',
    'key_rotation',
    'deploy_start',
    'deploy_complete',
    'config_change',
    'backup_start',
    'backup_complete',
    'restore_test_start',
    'restore_test_complete'
);
```

### Immutability policy

- Application role has INSERT permission only — no UPDATE, no DELETE.
- Only the operator via direct SQL (psql as superuser) can modify or
  archive records.
- Table partitioned by month (`timestamp` RANGE) for performance;
  old partitions can be detached and archived to B2/S3 after 90 days.

### Partitioning

```sql
CREATE TABLE security_events (
    id UUID DEFAULT gen_random_uuid(),
    timestamp TIMESTAMPTZ NOT NULL DEFAULT now(),
    event_type security_event_type NOT NULL,
    actor VARCHAR(128) NOT NULL,
    target VARCHAR(256),
    detail JSONB DEFAULT '{}',
    source_ip INET,
    trace_id UUID,
    PRIMARY KEY (id, timestamp)
) PARTITION BY RANGE (timestamp);

-- Monthly partitions created automatically or via cron
CREATE TABLE security_events_2026_08
    PARTITION OF security_events
    FOR VALUES FROM ('2026-08-01') TO ('2026-09-01');
```

## Loki structured logs

Logs with `security=true` label are written by application services
for security-relevant operational events:

```json
{
  "timestamp": "2026-08-01T14:31:00Z",
  "level": "warn",
  "service": "lumine-trade-core",
  "security": true,
  "trace_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "message": "auth_failure: invalid signature for API key lumine-key-7",
  "source_ip": "203.0.113.42",
  "event_type": "auth_failure"
}
```

Loki logs provide the operational view — real-time search, correlation
with traces via `trace_id`, and integration with Grafana dashboards.

## Alerting rules

### Critical alerts (Prometheus + Alertmanager)

| Condition | Metric/Log query | Threshold |
|-----------|-----------------|-----------|
| Brute force attempt | `rate(auth_failure_total[5m])` by source_ip | > 5 in 5 minutes from same IP |
| Kill switch engaged | `kill_switch_status` | Value = 1 |
| Proposal overridden | `rate(proposal_override_total[10m])` | > 0 (every override is notable) |
| Key rotation occurred | `security_event_total{event_type="key_rotation"}` | > 0 |
| Deploy started but not completed | `deploy_started - deploy_completed` | > 1 for 15 minutes |

### Warning alerts

| Condition | Threshold |
|-----------|-----------|
| Sporadic auth failures | 1-2 failures in 5 minutes |
| Config change | Any `config_change` event |
| Backup failure (already covered by D11-5) | 2 consecutive failures |

Alert delivery: same channel as D11-4 observability alerts (Telegram
and/or email, < 1 minute for critical).

## The trace_id loop (closed)

```
Frontend ActivityLog
  │ trace_id displayed (click to copy)
  │
  ▼
Operator pastes trace_id into Grafana
  │
  ├─ Loki: all log lines with this trace_id
  ├─ Tempo: full trace span from scheduler → decision → execution
  └─ security_events: all security events with this trace_id
```

This closes the loop required by Phase 9 `error-contract.md` and
Phase 11 `observability.md` — every security-relevant operation
carries a `trace_id` that connects the frontend ActivityLog to the
backend audit trail.

## What this document does NOT define

- Concrete `security_events` migration SQL, partitioning cron job
  (Phase 14+).
- Prometheus recording rules and alertmanager configuration (Phase 14+).
- Grafana security dashboard JSON (Phase 14+).
- SIEM integration — not in V1 scope.

## Phase boundary

Audit log architecture, event schema, immutability policy, and alerting
rules are fixed here. Implementation code and configurations belong to
Phase 14+.