# Lumine Fund

**Institutional-grade trading workstation for a single-operator AI fund.**
Lumine Fund is the execution and risk layer of [Lumine](https://lumine.biz.id): a self-hosted,
human-supervised system that trades XAUUSD and BTCUSD through MetaTrader 5, with every order
gated by deterministic risk rules and a full append-only audit trail.

> Status: active development. Live trading is off by default and requires an explicit,
> two-step owner activation.

---

## Why it exists

Most retail trading tools optimise for speed of clicking. A fund needs the opposite: a system
that makes the safe action the easy one. Lumine Fund is built around three rules:

1. **Risk before profit.** Every order passes a deterministic gate. Kill switch, drawdown
   limits, and stale-data checks are enforced server-side, not in the browser.
2. **Nothing happens silently.** Orders, rejections, and operator actions are written to an
   append-only ledger with the reason attached.
3. **Human authority is explicit.** Flattening, releasing a kill switch, and going live all
   require a second confirmation and a TOTP step-up.

## What is inside

- **Terminal**: full-width candlestick chart, one-line order ticket, live bid/ask/spread,
  open positions and pending orders in a single screen.
- **Risk engine**: position sizing, hard stops, daily and total drawdown limits, exposure caps.
- **AI layer**: strategy agents and an LLM analyst that produce conclusions and proposals; a
  synthesizer distils them into a single readable verdict. Agents can propose, never execute.
- **Operations**: system metrics, session-aware market status, backup age, and an audit view
  for reconciliation.
- **MetaTrader bridge**: a single EA polls the API, reports fills, and reconciles positions.

## Stack

| Layer | Technology |
| --- | --- |
| Frontend | React 18, Vite, lightweight-charts |
| API | FastAPI, SQLAlchemy Core, PostgreSQL 16 |
| Execution | MetaTrader 5 + custom EA (MQL5) |
| Runtime | Native `systemd --user` services, no containers |

## Repository layout

```
api/        FastAPI service: auth, orders, risk gate, SSE stream, metrics
frontend/   React terminal and operator console
ea/         MetaTrader 5 expert advisor
strategies/ Strategy definitions and backtest artefacts
deploy/     systemd units and deployment helpers
docs/       Architecture, ADRs, runbooks, release evidence
scripts/    Operational tooling
```

Deep documentation lives in [`docs/README.md`](docs/README.md).

## Running locally

Prerequisites: Python 3.12+, Node 20+, PostgreSQL 16.

```bash
# API
cd api
python -m venv .venv && source .venv/bin/activate
pip install -e ".[test]"
cp ../.env .env 2>/dev/null || true   # DATABASE_URL, BRIDGE_TOKEN, SESSION secrets
uvicorn app.main:app --port 3110

# Frontend (dev server, proxies /auth, /orders, /stream to :3110)
cd frontend
npm install
npm run dev
```

The production frontend is a static build served by the API (`npm run build`).

## Security posture

- Session cookie is `HttpOnly`; every mutating request carries a CSRF token.
- Secrets live in `.env` files that never enter the repository.
- Kill switch, flatten, and live activation require TOTP step-up.
- All operator and system actions are append-only and attributed.

## License

Proprietary. All rights reserved.
