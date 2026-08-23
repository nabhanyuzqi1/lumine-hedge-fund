---
title: "Lumine Hedge Fund"
aliases: ["Lumine", "lumine-hedge-fund"]
type: moc
status: evergreen
created: 2026-08-23
updated: 2026-08-23
tags: ["#project", "#trading", "#mt5", "#ea", "#ai"]
---

# Lumine Hedge Fund

Platform trading terintegrasi dengan multi-agent AI untuk decision making dan execution.

## 📋 Quick Links

- [[Agent Start Guide]] — **BACA INI DULU** sebelum mulai kerja
- [[Architecture Overview]] — System design lengkap
- [[Error Encyclopedia]] — Semua error yang pernah terjadi + fix
- [[Deployment Runbook]] — Cara deploy ke VPS
- [[MT5 & EA]] — Expert Advisor dan bridge
- [[LLM & Research Pipeline]] — AI routing dan news ingestion

## 🎯 Project Vision

Lumine adalah **closed-loop trading system**:
1. **Research Pipeline** → News ingestion, market data, sentiment
2. **LLM Committee** → Multi-model analysis, decision synthesis
3. **Decision Engine** → Signal generation, risk assessment
4. **Execution (EA/MT5)** → Trade execution, position management
5. **Outcome → Research DB** → Feedback loop untuk improvement

## 🏗️ Tech Stack

| Layer | Technology |
|-------|------------|
| Frontend | React 18 + TypeScript + Vite + Tailwind + shadcn-ui |
| Backend | Python 3.12 + FastAPI + Redis + SSE |
| AI/LLM | Multi-model router (Gemini, DeepSeek, GPT) |
| Trading | MT5 + MQL5 EA + Redis bridge |
| Deploy | Docker Compose + Caddy + Cloudflare |
| VPS | 166.88.227.177 (root, SSH key only) |

## 📁 Repository Structure

```
lumine-hedge-fund/
├── backend/           # Python FastAPI + Redis
│   ├── app/          # Core application
│   ├── tests/        # pytest unit tests
│   └── docker-compose.vps.yml
├── frontend/          # React + TypeScript
│   ├── src/app/      # Pages (dashboard, terminal, research)
│   └── src/components/
├── scripts/deploy/mt5/  # LumineEA.mq5 + entrypoint
└── CLAUDE.md         # Agent context file
```

## 🔑 Key Concepts

- **EA (Expert Advisor)** — MQL5 script yang jalan di MT5, mengirim ticks/status via HTTP POST ke backend
- **HMAC Auth** — Backend menggunakan HMAC signature untuk API auth
- **SSE (Server-Sent Events)** — Realtime data streaming dari backend ke frontend
- **Redis Bridge** — EA ↔ Redis ↔ Backend communication
- **LLM Routing** — Multi-model dengan circuit breaker, fallback otomatis saat model down

## 📊 Current Status

> [!warning] PENDING UPDATE
> Status ini perlu diupdate sesuai progress terbaru.

### ✅ Working
- MT5 HFM instance (EURUSD, XAUUSD)
- EA v4.13 dengan seed + ticks pipeline
- LLM routing dengan fallback
- Frontend dashboard + terminal + research
- HMAC auth untuk API

### 🚧 In Progress
- MT5 Crypto instance (BTCUSD) — whitelist issue
- Realtime chart improvements
- News pipeline enhancement

### 📋 Backlog
- Positions/orders table UI
- Research vs Dashboard tab merger
- Superadmin LLM routing config
- Auto-retest saat market open

---

## 🔗 Related Pages

- [[MT5 & EA]]
- [[Backend Architecture]]
- [[Frontend Architecture]]
- [[LLM Routing]]
- [[Deployment Runbook]]
- [[Error Encyclopedia]]
