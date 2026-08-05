# Runtime Topology

## Overview

Phase 11 operationalizes the Phase 1 `deployment-topology.md` contract. The
11 Phase 1 services are unchanged; Phase 11 adds 4 infrastructure components
(Caddy, observability stack, OTel collector, backup sidecar) and one
external runtime dependency (Vercel, frontend only).

## Full runtime layout (V1)

```
Internet
  │
  ├─ HTTPS :443 ──► Caddy (TLS termination, reverse proxy)
  │                   ├─ /api/*      → lumine-trade-core (REST, Phase 9)
  │                   ├─ /streams/*  → lumine-trade-core (SSE, Phase 9)
  │                   └─ /grafana/*  → grafana (IP allowlist, operator only)
  │
  ├─ MT5 server ◄── lumine-mt5-bridge            (egress, Phase 1 unchanged)
  ├─ 9router/LLM ◄── lumine-llm-gateway          (egress, Phase 1 unchanged)
  ├─ Public news ◄── lumine-news-adapter         (egress, Phase 1 unchanged)
  └─ Backup ◄── backup-sidecar → rclone(crypt) → B2/S3   (egress NEW, D11-5)

VPS (single Linux node, Docker Compose v2)
├─ caddy                    (Zone 5, edge — the only public ports :80/:443)
├─ lumine-trade-core        (Zone 1, critical path — 1 instance)
├─ lumine-mt5-bridge        (Zone 2, isolated — 1 instance)
├─ lumine-research-worker   (Zone 3, async)
├─ lumine-review-worker     (Zone 3, async)
├─ lumine-sandbox-worker    (Zone 3, async)
├─ lumine-scheduler         (Zone 5, deterministic)
├─ lumine-llm-gateway       (Zone 4)
├─ lumine-news-adapter      (Zone 5)
├─ postgres                 (Zone 5, volume: pgdata)
├─ redis                    (Zone 5, volume: redis-aof)
├─ prometheus               (Zone 5, volume: prom-data)
├─ loki                     (Zone 5, volume: loki-data)
├─ tempo                    (Zone 5, volume: tempo-data)
├─ otel-collector           (Zone 5)
├─ grafana                  (Zone 5, volume: grafana-data)
└─ backup-sidecar           (Zone 5, cron container)

Frontend (outside VPS)
└─ Vercel — production domain only
   Browser → HTTPS → Caddy → lumine-trade-core
   CORS allowlist: Vercel production origin (D11-1)
```

## Binding rules

1. **Single public entrypoint.** Only Caddy binds public `:80/:443`. No
   other container publishes ports to the host's public interface. All
   inter-service traffic stays on the private Docker bridge network
   (Phase 1 contract).
2. **Grafana is not public.** `/grafana/*` is served only to allowlisted
   operator IPs — operational dashboards expose fund state and must not be
   world-reachable.
3. **Instance invariants preserved.** `lumine-trade-core` and
   `lumine-mt5-bridge` remain single-instance (Phase 1: lineage
   single-writer + MT5 single-connection constraints). Compose declares
   them with the highest CPU/memory priority; workers may be throttled.
4. **Resource limits declared per service** in the compose file (Phase 1
   policy). V1 sizing baseline: 4 vCPU / 8 GB RAM / 160 GB SSD — an
   estimate to be tuned after real-load profiling; not a contract.
5. **Restart policies unchanged from Phase 1:** `unless-stopped` for
   infrastructure, `on-failure` for workers. Trade-core restart resumes
   from PostgreSQL state; open orders always carry broker-side SL/TP.
6. **Failure semantics unchanged from Phase 1:** Postgres or Redis
   unavailability halts new trading decisions (no lineage, no trade);
   bridge crash → safe state, existing positions managed via broker-side
   SL/TP.
7. **Vercel failure isolation.** Vercel outage removes the dashboard only.
   Trading, risk, and the kill switch remain operable via direct API/CLI
   against the VPS. This is the explicit reason the third-party dependency
   is confined to the read/visualization path.

## Scaling path (unchanged from Phase 1, restated for infra)

| Stage | Change | Infra implication |
|-------|--------|-------------------|
| V1 | Single VPS, one instance per service | Current release |
| V2 | Replicated async workers | compose replicas + Redis consumer groups; Caddy/pipeline unchanged |
| V3–V4 | trade-core / bridge stay single | Architectural invariant, not a tuning parameter |
| V5 | Multi-broker bridges | One bridge container per broker; no Caddy or pipeline change |
| V6 | Multi-account trade-cores | Sharding accounts; observability moves to federation/Mimir if multi-node |

## What this document does NOT define

- Concrete compose YAML, Dockerfiles, firewall rules (Phase 14+).
- SSH/user hardening and network ACL policy (Phase 12).
- Backup schedule internals and runbook steps (`backup-dr.md`).

## Phase boundary

The runtime layout and binding rules are fixed here. Concrete manifests
belong to Phase 14+.
