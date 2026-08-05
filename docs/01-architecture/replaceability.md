# Replaceability

## Overview

Product-philosophy principle #9 mandates: every component — broker, model,
prompt, strategy, data source, agent framework — must be replaceable without
rewriting the platform. Lock-in is a defect. Lumine achieves this via the
Port/adapter pattern plus a versioned artifact registry. This document
defines the Port table, the replace protocol, and the registry invariants.

## Port / adapter table

Every replaceable component sits behind a Port (abstract interface). An
adapter implements a Port. Replacing a component means implementing a new
adapter and registering it — no neighbor rewrite.

| Component | Port interface | Current adapter | Replace with (examples) |
|-----------|----------------|-----------------|--------------------------|
| Broker | `BrokerGateway` | MT5 Bridge | LMAX, OANDA, Interactive Brokers |
| Market data | `MarketDataProvider` | MT5 Bridge (organic) | LMAX feed, IB feed (organic); Polygon / Alpha Vantage (optional paid) |
| LLM provider | `LLMGateway` | 9router → GPT-5.5 / DeepSeek / Kimi / Qwen / GLM | Direct Anthropic / OpenAI; local model |
| Prompt | `PromptProvider` | Versioned `.prompt` files | Alternative template engine |
| Strategy | `StrategyEngine` | Intraday / swing books | Regime-adaptive, ML-based |
| Feature source | `FeatureProvider` | Python TA-Lib | Custom, alternative lib |
| Risk policy | `RiskPolicyProvider` | Versioned YAML / JSON | Rule engine |
| News | `NewsProvider` | Organic multi-source aggregator | Paid terminal (Bloomberg / Refinitiv) as optional adapter |
| Persistence | `LineageStore` | PostgreSQL | TimescaleDB, ClickHouse (interface stable) |

Port interface names are stable contracts. Adapter internals may change
freely. Phase 1 fixes the Port table; adapter selection may evolve without
amending this document as long as the Port contract holds.

## Replace protocol

Replacing a component follows a disciplined path that preserves safety and
reproducibility.

1. **Implement new adapter** — implement the Port interface.
2. **Register version** — add the new version to the versioned registry.
3. **Shadow mode** — new adapter runs in parallel; output is compared
   against the incumbent. It does not execute live.
4. **A/B validation** — Review worker compares performance and output
   divergence over a sufficient window.
5. **CIO approval** — production switch requires CIO sign-off (principle
   #7: self-modification as research, not production authority).
6. **Registry update** — new decisions pin to the new version.
7. **Old decisions stay pinned** — historical lineage records retain their
   original version snapshot (reproducibility invariant).

Shadow mode and A/B validation are mandatory for any component whose output
influences a live trading decision. Cosmetic or observability-only
components may skip shadow mode at CIO discretion.

## Versioned registry

The registry stores versioned artifacts pinned per decision. This is the
mechanism that makes every decision reproducible.

| Registry table | Contents |
|----------------|----------|
| `model_versions` | model ID + provider + sampling config (temperature, etc.) |
| `prompt_versions` | prompt template + variables |
| `strategy_versions` | strategy spec + parameters |
| `policy_versions` | risk policy + envelope |

Every lineage record stores a snapshot of all artifact versions used in
that decision. Replaying a decision = re-running with the same versions.
For LLM non-determinism, the lineage stores the actual LLM output, not only
the input.

## No hardcoding

- Model IDs (e.g. GPT-5.5, GLM-5.2) are never hardcoded in trade-core; they
  are resolved via the registry.
- Broker details (MT5 server, login) are never hardcoded; they live in
  config + adapter.
- Prompt text is never inlined in code; it lives in versioned prompt files.
- Strategy parameters are never literals in code; they live in versioned
  strategy registry entries.

Hardcoding any of the above is treated as a defect and must be refactored
to go through the registry / adapter layer.

## Replaceability and the news layer

The news adapter is replaceable like any other component. The default
adapter is organic multi-source (government / forexfactory / google / yahoo
/ social / RSS). A paid terminal adapter (Bloomberg / Refinitiv) may be
added behind the same `NewsProvider` Port without changing consumers. The
organic-first principle means the paid adapter is optional, never a default
dependency.

## Replaceability and market data

The MT5 bridge is the default `MarketDataProvider` and `BrokerGateway`
adapter. If a future broker provides its own data feed, a new adapter can
implement both Ports behind the same interfaces. Paid third-party
aggregators (Polygon, Alpha Vantage) are optional adapters, never the
default; the organic-first principle keeps the platform runnable without
them.

## What replaceability guarantees

- **No vendor lock-in.** Broker, model, prompt, strategy, data source, and
  news source can each be swapped independently.
- **Reproducibility preserved.** Old decisions stay pinned to old versions;
  new versions only affect new decisions.
- **Safe rollout.** Shadow + A/B + CIO approval prevents unvalidated
  replacements from reaching production.
- **Contract stability.** Port interfaces are the stable backbone; adapters
  may evolve freely.
- **No silent drift.** Every replacement is a versioned registry change,
  visible in lineage.
