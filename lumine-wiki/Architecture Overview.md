---
title: "Architecture Overview"
aliases: ["System Architecture", "Lumine Architecture"]
type: concept
status: evergreen
created: 2026-08-23
updated: 2026-08-23
tags: ["#architecture", "#system-design", "#overview"]
---

# Architecture Overview

High-level system design untuk Lumine Hedge Fund platform.

## 🎯 System Goal

**Closed-loop trading system** dengan AI-driven decision making:

```
Research Pipeline → LLM Committee → Decision Engine → EA/MT5 → Trade Outcome
        ↑                                                          ↓
        └──────────────────── Feedback Loop ──────────────────────┘
```

## 📐 Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                          VPS (166.88.227.177)                        │
├─────────────────────────────────────────────────────────────────────┤
│                                                                       │
│  ┌──────────────┐     ┌──────────────┐     ┌──────────────┐         │
│  │   Frontend   │◄────│    Caddy     │────►│   Backend    │         │
│  │  (React+TS)  │     │ (Rev Proxy)  │     │  (FastAPI)   │         │
│  └──────────────┘     └──────────────┘     └──────┬───────┘         │
│                              ▲                     │                  │
│                              │                     ▼                  │
│                       Cloudflare             ┌──────────┐           │
│                    (SSL + Tunnel)             │  Redis   │           │
│                                              └────┬─────┘           │
│                                                   │                  │
│  ┌────────────────────────────────────────────────┼──────────┐      │
│  │                     MT5 Instances               │          │      │
│  │  ┌─────────────────┐      ┌─────────────────┐  │          │      │
│  │  │   lumine-mt5    │      │ lumine-mt5-crypto│  │          │      │
│  │  │   (HFM, Forex)  │      │  (Exness, BTC)  │  │          │      │
│  │  │   EURUSD/XAU    │      │   BTCUSD        │  │          │      │
│  │  └────────┬────────┘      └────────┬────────┘  │          │      │
│  │           │                        │           │          │      │
│  │      LumineEA.mq5            LumineEA.mq5      │          │      │
│  │           │                        │           │          │      │
│  └───────────┼────────────────────────┼───────────┼──────────┘      │
│              │                        │           │                  │
│              └───────── HTTP POST ────┴───────────┘                  │
│                        (ticks, status)                               │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘
```

## 🔄 Data Flow

### 1. Market Data Flow (MT5 → Backend → Frontend)

```
MT5 EA (OnTick)
    │
    ├─── HTTP POST /mt5-proxy/ticks ───► Redis LPUSH mt5:ticks
    │                                        │
    ├─── HTTP POST /mt5-proxy/status ──► Redis HSET mt5:status
    │                                        │
    └─── HTTP GET /mt5-proxy/commands ◄─── Redis LPOP mt5:commands
                                             │
                                        Backend SSE
                                             │
                                             ▼
                                        Frontend (EventSource)
```

### 2. Research Pipeline Flow

```
RSS Feeds (BBC, OilPrice, MarketWatch)
    │
    ├─── Backend Fetch (15 min) ───► Redis LPUSH lumine:news:raw
    │                                      │
    │                                 LLM Analysis
    │                                      │
    │                                      ▼
    │                               Redis HSET lumine:news:analyzed
    │                                      │
    └──────────────────────────────────────┼──────────────────────►
                                           │
                                      Frontend Display
```

### 3. LLM Decision Flow

```
Scheduled Task (every 60s)
    │
    ├─── Fetch Market Data ───► ticks + indicators + news
    │
    ├─── LLM Router ───► Select best model (Gemini/DeepSeek/GPT)
    │
    ├─── Analyst Prompt ───► Generate decision (BUY/SELL/HOLD)
    │
    ├─── Decision Engine ───► Validate + Risk Check
    │
    └─── Command Queue ───► Redis LPUSH mt5:commands
                                  │
                             EA Polls & Executes
```

## 🏗️ Component Details

### Frontend (React + TypeScript)

**Tech Stack:**
- React 18 + TypeScript
- Vite (build)
- Tailwind CSS + shadcn-ui
- Recharts / Lightweight Charts

**Pages:**
- `/dashboard` — Overview, positions, PnL
- `/terminal` — Chart + order entry
- `/research` — News + analysis
- `/superadmin` — System config

**Key Components:**
- `CandlestickChart` — OHLC + volume
- `PositionsTable` — Live positions
- `NewsFeed` — RSS news with LLM analysis

### Backend (Python FastAPI)

**Tech Stack:**
- Python 3.12
- FastAPI + Uvicorn
- Redis (data store + pub/sub)
- SSE (Server-Sent Events)

**API Endpoints:**
```
/api/health                 — Health check
/api/sse/status             — SSE stream (ticks, positions)
/api/market/quotes          — Current prices
/api/market/features        — Technical indicators
/api/news/headlines         — News feed
/api/llm/status             — LLM routing status
/mt5-proxy/ticks            — EA → Backend
/mt5-proxy/status           — EA → Backend
/mt5-proxy/commands         — EA ← Backend
```

### MT5 + EA (MQL5)

**Instances:**
- `lumine-mt5` — HFM broker, EURUSD + XAUUSD
- `lumine-mt5-crypto` — Exness, BTCUSD

**EA Features (LumineEA v4.13):**
- HTTP bridge ke backend via Redis proxy
- Seed bars on startup (force mode)
- Tick streaming (real-time)
- Command execution (open/close positions)
- Status reporting (version, build, health)

**EA Inputs:**
```mql5
input string InpProxyURL = "http://lumine.biz.id/mt5-proxy";
input string InpSeedSymbols = "EURUSD,XAUUSD,BTCUSD";
input bool   InpEnableSeed = true;
```

### Redis (Data Layer)

**Keys:**
```
mt5:status          — HSET (ea_version, ea_build, symbol, ...)
mt5:ticks           — LIST (last 1000 ticks)
mt5:commands        — LIST (pending commands)
mt5:seed_bars       — LIST (seed data)
mt5:results         — LIST (trade outcomes)

lumine:news:raw     — LIST (raw RSS)
lumine:news:analyzed — HSET (per news item)
lumine:llm_routing  — STRING (current model)

mt5crypto:status    — HSET (crypto instance)
mt5crypto:*         — (isolated namespace)
```

### Caddy (Reverse Proxy)

**Routes:**
```
lumine.biz.id/              → Frontend (nginx)
lumine.biz.id/api/*         → Backend (FastAPI)
lumine.biz.id/mt5-proxy/*   → Redis HTTP Proxy
lumine.biz.id/novnc/*       → noVNC (MT5 GUI)
```

## 🔐 Security Architecture

### Authentication

```
Frontend → Backend: HMAC-SHA256 signature
  - Key: VITE_LUMINE_API_KEY
  - Secret: VITE_LUMINE_API_SECRET
  - Headers: X-Timestamp, X-Signature

MT5 EA → Backend: Shared secret (MT5_PROXY_SECRET)
  - Header: X-MT5-Secret
```

### Network Security

- SSH key-only (no password)
- Cloudflare tunnel (no direct IP exposure)
- Rate limiting di Caddy
- CORS restricted to lumine.biz.id

## 📊 Scalability Considerations

### Current Bottlenecks

1. **Single Redis instance** — semua data lewat satu Redis
2. **SSE connection limit** — satu connection per client
3. **MT5 single-threaded** — EA tidak bisa parallel

### Future Improvements

1. Redis Cluster untuk scaling
2. WebSocket sebagai alternatif SSE
3. Multiple EA instances untuk load balancing

---

## 🔗 Related Pages

- [[MT5 & EA]] — EA implementation details
- [[Backend Architecture]] — API dan data layer
- [[Frontend Architecture]] — React components
- [[LLM Routing]] — Multi-model router
- [[Deployment Runbook]] — Deploy procedures
