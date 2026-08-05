# Phase 1 — System Architecture

This directory contains the Phase 1 deliverables for the Lumine AI Hedge Fund
platform. Phase 1 defines the high-level system architecture: topology,
departments, communication, deployment, data flow, and replaceability. No
database schema, event payload schema, agent persona, prompt, MT5 protocol,
risk math, folder structure, or code belongs here — those begin in later
phases.

## Documents

| Document | Purpose |
|----------|---------|
| `high-level-architecture.md` | Five logical zones, process boundaries, diagram |
| `departments-and-books.md` | Eight functional departments, intraday/swing books |
| `communication-and-contracts.md` | Sync/async lanes, stream table, Port/adapter contracts |
| `deployment-topology.md` | Single VPS Docker Compose, scaling path |
| `data-flow.md` | Ten-step decision cycle, safe-state behavior, data sourcing |
| `replaceability.md` | Port table, replace protocol, versioned registry |

## Authority

Phase 1 is the authoritative system architecture reference. Every later phase
(data architecture, AI strategy, trading integration, risk, infrastructure,
security, testing, implementation) must trace its assumptions back to
decisions recorded here. If a later phase conflicts with Phase 1, Phase 1 is
updated first, then affected documentation, then code.

## Phase 1 decisions

| # | Decision | Choice |
|---|----------|--------|
| 1 | Topology | Hybrid: critical-path monolith (trade-core) + async workers + isolated MT5 bridge |
| 2 | LLM boundary | LLM as proposer + deterministic validator |
| 3 | Communication | Hybrid: sync in-proc (critical path) + Redis streams (async dispatch); event log → PostgreSQL |
| 4 | Data store | PostgreSQL-centric (source of truth + partitioned time-series) + Redis cache |
| 5 | MT5 isolation | Separate process + Redis streams command/response; trade-core never calls MT5 API directly |
| 6 | Replaceability | Port/adapter + versioned registry (model/prompt/strategy/policy pinned per decision) |
| 7 | Decision cycle | Deterministic scheduler + event triggers; LLM never self-triggers |
| 8 | Trade management | Deterministic execution of AI-proposed plan; AI re-evaluation on periodic triggers |
| 9 | Data sourcing | Organic/broker-native first (MT5); 3rd-party paid API = optional adapter, never default |
| 10 | News layer | Organic multi-source aggregator (gov/forexfactory/google/yahoo/social/RSS), AI-driven; "Bloomberg Terminal class, free version" target |

## Status

- Phase: 1 — System Architecture
- Strategy: Hybrid critical-path monolith + async workers + isolated MT5 bridge
- Approval: Approved
- Next phase: 2 — Department & Agent Architecture (complete)
