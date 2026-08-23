---
title: "LLM Routing"
aliases: ["AI Model Router", "LLM Pipeline"]
type: concept
status: evergreen
created: 2026-08-23
updated: 2026-08-23
tags: ["#llm", "#ai", "#routing", "#gemini", "#deepseek"]
---

# LLM Routing

Multi-model AI routing untuk decision making di Lumine.

## 🎯 Overview

Lumine menggunakan **multi-model approach** dengan automatic failover:
- Circuit breaker untuk model yang down
- Model selection berdasarkan task type
- Fallback chain untuk reliability

## 🤖 Supported Models

| Model | Provider | Use Case |
|-------|----------|----------|
| Gemini 3.1 Pro | oa/gemini-3.1-pro | Primary analyst |
| DeepSeek v4 Flash | oc/deepseek-v4-flash-free | Fast analysis |
| GPT-4 | oa/gpt-4 | Complex reasoning |
| GLM-5 | oa/glm-5 | Alternative |

## 🔄 Routing Logic

### Model Selection (every 60s)

```python
# services/llm_router.py
async def select_model(task: str) -> str:
    cache_key = f"llm:{task}:{datetime.now().strftime('%Y%m%d%H')}"

    # Check cache
    cached = await redis.get(cache_key)
    if cached:
        return cached.decode()

    # Check circuit breaker
    for model in PRIORITY_ORDER:
        if await is_model_healthy(model):
            await redis.setex(cache_key, 3600, model)
            return model

    # All models down - use fallback
    return FALLBACK_MODEL
```

### Circuit Breaker

```python
async def is_model_healthy(model: str) -> bool:
    key = f"circuit:{model}"
    failures = int(await redis.get(key) or 0)

    if failures >= 3:
        # Check if cooldown period passed
        ttl = await redis.ttl(key)
        if ttl > 0:
            return False  # Still in cooldown

    return True

async def record_failure(model: str):
    key = f"circuit:{model}"
    count = await redis.incr(key)
    if count == 1:
        await redis.expire(key, 300)  # 5 min cooldown
```

### Health Check

```python
async def check_model_health(model: str) -> bool:
    try:
        response = await client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "ping"}],
            max_tokens=5,
            timeout=10
        )
        return True
    except Exception:
        await record_failure(model)
        return False
```

## 📊 Data Flow

```
Market Data (ticks + indicators)
         │
         ▼
    LLM Router ───► Select Model (Gemini/DeepSeek/GPT)
         │
         ▼
    Analyst Prompt ───► "Analyze EURUSD: trend=BULLISH, volatility=0.5%"
         │
         ▼
    LLM Response ───► {decision: "BUY", confidence: 0.75, reasons: [...]}
         │
         ▼
    Decision Engine ───► Validate + Risk Check
         │
         ▼
    Command Queue ───► Redis LPUSH mt5:commands
```

## 📝 Prompt Templates

### Analyst Prompt

```
You are a forex analyst. Analyze the following market data:

Symbol: {symbol}
Current Price: {price}
Trend: {trend}
SMA 20: {sma20}
Volatility: {volatility}

Recent News:
{news_headlines}

Provide:
1. Market bias (BULLISH/BEARISH/NEUTRAL)
2. Entry recommendation (BUY/SELL/HOLD)
3. Confidence level (0-1)
4. Key reasons (bullet points)
```

### Decision Output Schema

```json
{
  "symbol": "EURUSD",
  "decision": "BUY",
  "confidence": 0.75,
  "entry_price": 1.08550,
  "stop_loss": 1.08400,
  "take_profit": 1.08700,
  "reasons": [
    "Trend is bullish above SMA20",
    "Volatility is moderate",
    "News sentiment is positive"
  ],
  "risk_reward": 2.0
}
```

## 🔧 Configuration

### Redis Keys

```
lumine:llm_routing    — Current selected model
circuit:<model>       — Failure count + cooldown
llm:<task>:<hour>     — Model selection cache
```

### Environment Variables

```bash
GEMINI_API_KEY=xxx
DEEPSEEK_API_KEY=xxx
OPENAI_API_KEY=xxx
LLM_TIMEOUT=30
LLM_MAX_RETRIES=3
```

## 🐛 Debugging

### Check Current Model

```bash
redis-cli GET lumine:llm_routing
```

### Check Circuit Breaker

```bash
redis-cli GET circuit:oa/gemini-3.1-pro
redis-cli TTL circuit:oa/gemini-3.1-pro
```

### Force Model Switch

```bash
redis-cli SET lumine:llm_routing "oc/deepseek-v4-flash-free"
```

### Reset Circuit Breaker

```bash
redis-cli DEL circuit:oa/gemini-3.1-pro
```

## 🚨 Common Issues

### Model Down - No Fallback

**Symptoms:**
```
analyst_failed: All models are down
```

**Fix:**
1. Check API keys di `.env`
2. Check circuit breaker status
3. Manually reset: `redis-cli DEL circuit:*`
4. Verify model health: `curl https://api.openai.com/v1/models`

---

### Stale Model Selection

**Symptoms:**
- Model tidak berubah meskipun down

**Fix:**
```bash
redis-cli DEL lumine:llm_routing
redis-cli DEL llm:*
```

---

### Cache Mismatch

**Symptoms:**
- Router selects model A, analyst uses model B

**Fix:**
Ensure `await` on all async calls:
```python
# WRONG
model = redis.get(key)  # Returns coroutine

# RIGHT
model = await redis.get(key)
```

---

## 📈 Monitoring

### LLM Status API

```
GET /api/llm/status

Response:
{
  "current_model": "oa/gemini-3.1-pro",
  "healthy": true,
  "last_check": "2026-08-23T10:00:00Z",
  "circuit_breakers": {
    "oa/gemini-3.1-pro": {"failures": 0, "ttl": null},
    "oc/deepseek-v4-flash-free": {"failures": 2, "ttl": 120}
  }
}
```

### Frontend Indicator

```tsx
<LLMStatusBadge
  model={llmStatus.current_model}
  healthy={llmStatus.healthy}
/>
```

---

## 🔗 Related

- [[Architecture Overview]] — System design
- [[Backend Architecture]] — API implementation
- [[Error Encyclopedia]] — LLM errors
