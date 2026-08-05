# Deployment Topology

## Overview

Lumine deploys as a set of Docker containers on a single Linux VPS via
Docker Compose. Each service is a separate container with its own resource
limits and network policy. The topology is designed to scale horizontally
to cloud-native in the future without rewriting service contracts.

## Single-VPS topology (initial release)

```
VPS (Linux, single node)
├─ docker-compose.yml
│
├─ Service: lumine-trade-core        (Zone 1, 1 container, critical path)
├─ Service: lumine-mt5-bridge        (Zone 2, 1 container, isolated)
├─ Service: lumine-research-worker   (Zone 3, 1 container, async)
├─ Service: lumine-review-worker     (Zone 3, 1 container, async)
├─ Service: lumine-sandbox-worker    (Zone 3, 1 container, async)
├─ Service: lumine-scheduler         (Zone 5, 1 container, deterministic)
├─ Service: lumine-llm-gateway       (Zone 4, 1 container, AutoGen + 9router)
├─ Service: lumine-news-adapter      (Zone 5, 1 container, organic multi-source)
├─ Service: postgres                 (Zone 5, 1 container, persistent volume)
├─ Service: redis                    (Zone 5, 1 container, persistent volume)
└─ Service: observability stack      (Zone 5, logs/metrics/traces)
```

## Isolation & resource policy

- Each service runs in its own container with CPU/memory limits declared in
  the compose file.
- `lumine-trade-core` and `lumine-mt5-bridge` are high-priority services.
- Research, review, and sandbox workers are low-priority; they may be
  throttled or paused without affecting trading.
- Internal bridge network: services communicate over a private Docker
  network. Only `lumine-trade-core` and `lumine-mt5-bridge` require outbound
  access to the MT5 server. The news adapter requires outbound HTTPS to
  public sources. The LLM gateway requires outbound HTTPS to 9router / LLM
  providers.
- Persistent volumes: PostgreSQL data, Redis AOF, lineage archive, news
  cache.
- Secrets management: Docker secrets / env injection. Detailed credential
  architecture is defined in Phase 11 Security.

## Scaling path (future, post first release)

The topology is deliberately shaped so that horizontal scaling does not
require contract changes.

| Stage | Change | Constraint |
|-------|--------|------------|
| V1 (initial) | Single VPS, one instance per service | Current release |
| V2 | Horizontal replicas of async workers (research/review/sandbox) | Workers are already stream-consuming, stateless |
| V3 | Trade-core remains single | Critical path consistency requires single-writer to lineage |
| V4 | MT5 bridge remains single | One MT5 connection per account |
| V5 | Multi-broker | Multiple bridge containers, one per broker, behind `BrokerGateway` Port |
| V6 | Multi-account | Multiple trade-core instances, shared governance + lineage store |

Trade-core and MT5 bridge single-instance constraints are architectural, not
incidental: the lineage invariant (single writer, ACID) and the MT5
single-connection constraint require it. Horizontal scaling of the critical
path is achieved by sharding accounts, not by replicating trade-core.

## Network & egress

```
Internet
   │
   ├── MT5 server ◄─────── lumine-mt5-bridge (only MT5 egress)
   │
   ├── 9router / LLM ◄──── lumine-llm-gateway (only LLM egress)
   │
   ├── Public news ◄────── lumine-news-adapter (organic sources)
   │
   └── (no other outbound from any service)

Internal Docker bridge network
   ├── all lumine-* services
   ├── postgres
   └── redis
```

No service other than the three above has outbound internet access. This
minimizes attack surface and prevents accidental dependency on paid/external
services.

## Failure & restart policy

- All services declare restart policies in compose (`unless-stopped` for
  infra, `on-failure` for workers).
- `lumine-trade-core` crash → all open orders must have SL/TP set on broker
  side (safety net); trade-core restart resumes from persisted state in
  PostgreSQL.
- `lumine-mt5-bridge` crash → trade-core detects stream timeout, enters safe
  state (no new entries, manage existing via broker-side SL/TP).
- Worker crashes are non-critical; they resume from the last consumed stream
  offset.
- PostgreSQL unavailability → trade-core halts all new decisions (lineage
  cannot be written). This is intentional: no lineage, no trade.
- Redis unavailability → trade-core halts new decisions (cannot dispatch to
  bridge); existing broker-side SL/TP remains active.

## What this topology guarantees

- **Single-node simplicity for V1** with a clear path to cloud-native.
- **Process isolation** so a single component failure degrades, not crashes,
  the system.
- **Minimal egress** so external dependencies stay explicit and replaceable.
- **Persistent state** in PostgreSQL + Redis volumes for resumability.
- **No critical-path horizontal scaling trick** — single-writer invariants
  are preserved by design.
