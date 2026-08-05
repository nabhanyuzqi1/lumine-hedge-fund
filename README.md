# Lumine — AI-Native Quantitative Hedge Fund Platform

Lumine is an institutional-grade AI-driven quantitative investment system. AI
agents collaborate inside a strict hierarchy to make investment decisions,
manage risk, and execute trades — starting with XAUUSD and scaling to Forex,
Indices, Commodities, Crypto, Stocks, and Futures.

This is **not** a retail trading bot, EA, or signal provider.

## Start here

| If you are… | Read this first |
|-------------|-----------------|
| New to the project | [`docs/00-vision/`](docs/00-vision/) → [`ARCHITECTURE.md`](ARCHITECTURE.md) → [`docs/90-governance-and-operations/92-onboarding/`](docs/90-governance-and-operations/92-onboarding/) |
| Looking for a decision | [`docs/adr/INDEX.md`](docs/adr/INDEX.md) |
| Looking for a topic (not a phase) | [`docs/INDEX.md`](docs/INDEX.md) |
| On-call | [`docs/90-governance-and-operations/94-runbooks/`](docs/90-governance-and-operations/94-runbooks/) |
| Implementing | [`docs/14-implementation/`](docs/14-implementation/) → [`docs/15-implementation/`](docs/15-implementation/) |
| Reporting a vulnerability | [`SECURITY.md`](SECURITY.md) |

## Repository layout

```
lumine-hedge-fund/
├── docs/                              # Knowledge base (Phases 0-15 + governance tier)
│   ├── INDEX.md                       # Topic × phase knowledge map
│   ├── phase-mapping.md               # Master-prompt → folder mapping
│   ├── adr/                           # Architectural Decision Records (single registry)
│   ├── 00-vision/ … 15-implementation/  # Design phases
│   └── 90-governance-and-operations/  # Permanent operating standards
├── backend/                           # Python workspace (FastAPI, AutoGen, MT5)
├── frontend/                          # TypeScript/React workspace
└── .github/workflows/                 # CI/CD
```

## Quickstart

```bash
make install      # backend + frontend deps
make migrate      # apply DB migrations
make run-dev      # backend + frontend dev servers
make test         # full test suite
make lint         # lint everything
```

See [`Makefile`](Makefile) for all targets. CI invokes the same targets —
local and CI parity is enforced.

## Phases

Phases 0–14 (design) are complete. Phase 15 (implementation) is in progress.
See [`docs/phase-mapping.md`](docs/phase-mapping.md) and
[`docs/15-implementation/README.md`](docs/15-implementation/README.md) for
live status.

## License

Proprietary. All rights reserved.
