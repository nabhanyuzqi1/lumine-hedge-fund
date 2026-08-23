---
title: "Backend Architecture"
aliases: ["Python Backend", "FastAPI Backend"]
type: concept
status: evergreen
created: 2026-08-23
updated: 2026-08-23
tags: ["#backend", "#python", "#fastapi", "#api"]
---

# Backend Architecture

Python FastAPI backend untuk Lumine.

## 🏗️ Stack

| Component | Technology |
|-----------|------------|
| Framework | FastAPI + Uvicorn |
| Python | 3.12 |
| Database | Redis (in-memory) |
| Realtime | SSE (Server-Sent Events) |
| Auth | HMAC-SHA256 signature |
| Deploy | Docker Compose |

## 📁 Directory Structure

```
backend/
├── app/
│   ├── main.py              # FastAPI app entry
│   ├── api/                 # API routes
│   │   ├── market.py        # /api/market/*
│   │   ├── news.py          # /api/news/*
│   │   ├── llm.py           # /api/llm/*
│   │   └── sse.py           # /api/sse/*
│   ├── sse/                 # SSE publishers
│   │   ├── status.py        # Status stream
│   │   └── ticks.py         # Tick stream
│   ├── services/            # Business logic
│   │   ├── llm_router.py    # Model selection
│   │   ├── news_ingest.py   # RSS ingestion
│   │   └── analyst.py       # LLM analysis
│   └── core/                # Config & utilities
│       ├── config.py
│       └── auth.py          # HMAC validation
├── tests/                   # pytest unit tests
└── docker-compose.vps.yml   # Production deploy
```

## 🔌 API Endpoints

### Market Data

```
GET /api/market/quotes       — Current prices (EURUSD, XAUUSD, BTCUSD)
GET /api/market/features     — Technical indicators (SMA, volatility, trend)
GET /api/market/bars/:symbol — OHLCV bars
```

### News

```
GET /api/news/headlines      — RSS news with LLM analysis
GET /api/news/:id            — Single news detail
```

### LLM

```
GET /api/llm/status          — Current model, routing status
POST /api/llm/analyze        — Trigger manual analysis
```

### SSE Streams

```
GET /api/sse/status          — Status + positions stream
GET /api/sse/ticks           — Real-time tick stream
```

### MT5 Proxy (EA ↔ Backend)

```
POST /mt5-proxy/ticks        — EA sends tick data
POST /mt5-proxy/status       — EA sends status
POST /mt5-proxy/seed/bars    — EA sends seed bars
GET  /mt5-proxy/commands     — EA polls for commands
POST /mt5-proxy/trade/result — EA sends trade outcome
```

## 🔐 Authentication

### HMAC Signature (Frontend → Backend)

```typescript
// Frontend
const timestamp = Date.now().toString();
const signature = await hmacSha256(secret, timestamp);
headers: {
  'X-Timestamp': timestamp,
  'X-Signature': signature,
  'X-API-Key': apiKey
}
```

```python
# Backend validation
def validate_hmac(timestamp: str, signature: str, api_key: str):
    expected = hmac.new(
        SECRET.encode(),
        timestamp.encode(),
        hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(signature, expected):
        raise HTTPException(401, "Invalid signature")
```

### MT5 Secret (EA → Backend)

```python
# EA sends header
X-MT5-Secret: <MT5_PROXY_SECRET>

# Backend validates
if request.headers.get("X-MT5-Secret") != MT5_PROXY_SECRET:
    raise HTTPException(403, "Invalid MT5 secret")
```

## 📊 Redis Schema

```
mt5:status          HSET  {ea_version, ea_build, symbol, equity, ...}
mt5:ticks           LIST  [tick1, tick2, ...] (last 1000)
mt5:commands        LIST  [cmd1, cmd2, ...] (pending)
mt5:seed_bars       LIST  [bar1, bar2, ...]
mt5:results         LIST  [result1, result2, ...]

lumine:news:raw     LIST  Raw RSS items
lumine:news:analyzed HSET {id: {title, sentiment, impact}}
lumine:llm_routing  STRING Current model name
```

## 🚀 Development

### Run Locally

```bash
cd backend
python -m venv .venv
.venv/Scripts/activate  # Windows
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

### Run Tests

```bash
cd backend
env -u PYTHONPATH .venv/Scripts/python.exe -m pytest tests/unit/ -q
```

### Deploy to VPS

```bash
ssh root@166.88.227.177 "cd /opt/lumine/backend && \
  git pull && \
  docker compose -f docker-compose.vps.yml up -d --build backend"
```

---

## 🔗 Related

- [[Architecture Overview]] — System design
- [[MT5 & EA]] — EA integration
- [[Error Encyclopedia]] — Debug guide
- [[Deployment Runbook]] — Deploy steps
