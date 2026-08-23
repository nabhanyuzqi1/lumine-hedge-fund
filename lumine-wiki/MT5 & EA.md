---
title: "MT5 & EA"
aliases: ["MT5", "Expert Advisor", "LumineEA"]
type: concept
status: evergreen
created: 2026-08-23
updated: 2026-08-23
tags: ["#mt5", "#ea", "#mql5", "#trading"]
---

# MT5 & EA

MetaTrader 5 + Expert Advisor implementation untuk Lumine.

## 📊 MT5 Instances

### lumine-mt5 (HFM Broker)

| Property | Value |
|----------|-------|
| Container | `lumine-mt5` |
| Broker | HFM (Hugo's Way) |
| Account | Live account |
| Symbols | EURUSD, XAUUSD |
| Timezone | Server time (GMT+2/3) |
| noVNC | https://lumine.biz.id/novnc/vnc.html |

### lumine-mt5-crypto (Exness Broker)

| Property | Value |
|----------|-------|
| Container | `lumine-mt5-crypto` |
| Broker | Exness |
| Account | Demo account (463852058) |
| Symbols | BTCUSD |
| Timezone | Server time |
| noVNC | https://lumine.biz.id/novnc-crypto/vnc.html |

## 🤖 LumineEA

Expert Advisor yang menghubungkan MT5 dengan backend via HTTP.

### Current Version

```
v4.13 — 2026.08.22
Features: FORCE_SEED, PARTIAL_CLOSE, CUT_LOSS, SELF_HEALING
```

### Source Location

```
Repo: scripts/deploy/mt5/LumineEA.mq5
VPS:  /opt/lumine-ea/LumineEA.mq5 (bind mount)
```

### EA Inputs

```mql5
input string InpProxyURL    = "http://lumine.biz.id/mt5-proxy";
input string InpSeedSymbols = "EURUSD,XAUUSD,BTCUSD";
input bool   InpEnableSeed  = true;  // Force seed on startup
input int    InpTimerMs     = 1000;  // Poll interval
```

### EA Lifecycle

```
OnInit()
  ├── Load inputs
  ├── Validate proxy connection
  ├── Build seed data for all timeframes
  └── Start timer (1s interval)

OnTimer()
  ├── PollCommands() — GET /commands
  ├── Process command if any
  ├── SendStatus() — POST /status
  └── Backoff if errors

OnTick()
  ├── Check for new tick
  ├── PostTick() — POST /ticks
  └── Update last_tick_time (prevent replay)

OnDeinit()
  └── Send final status
```

### HTTP Endpoints (EA ↔ Backend)

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/mt5-proxy/ticks` | POST | Send tick data |
| `/mt5-proxy/status` | POST | Send EA status |
| `/mt5-proxy/commands` | GET | Poll for commands |
| `/mt5-proxy/seed/bars` | POST | Send seed bars |
| `/mt5-proxy/trade/result` | POST | Trade outcome |

### Data Formats

**Tick POST:**
```json
{
  "symbol": "EURUSD",
  "bid": 1.08542,
  "ask": 1.08544,
  "time": 1724367890123,
  "volume": 150
}
```

**Status POST:**
```json
{
  "ea_version": "4.13",
  "ea_build": 20260822,
  "symbol": "EURUSD",
  "timeframe": 1,
  "account_balance": 10000.00,
  "account_equity": 10150.00,
  "positions": 2,
  "uptime": 3600
}
```

**Command GET:**
```json
{
  "cmd": "OPEN",
  "symbol": "EURUSD",
  "type": "BUY",
  "volume": 0.01,
  "sl": 1.08400,
  "tp": 1.08700,
  "comment": "LLM Signal"
}
```

## 🔧 EA Development

### Compile EA

```bash
# Di VPS (auto-compile saat container start)
docker restart lumine-mt5

# Manual compile via metaeditor64.exe (Wine)
docker exec lumine-mt5 wine "C:\\Program Files\\HFM Metatrader 5\\metaeditor64.exe" /compile:"C:\\Program Files\\HFM Metatrader 5\\MQL5\\Experts\\LumineEA.mq5"
```

### Deploy EA Update

```bash
# 1. Copy source to VPS
scp scripts/deploy/mt5/LumineEA.mq5 root@166.88.227.177:/opt/lumine-ea/LumineEA.mq5

# 2. Restart MT5 (EA will compile on startup)
ssh root@166.88.227.177 "docker restart lumine-mt5"

# 3. Wait 60s for EA init
sleep 60

# 4. Verify new version
ssh root@166.88.227.177 "docker exec backend-redis-1 redis-cli HGET mt5:status ea_version"
```

### Debug EA

```bash
# EA logs
ssh root@166.88.227.177 "docker exec lumine-mt5 sh -c 'iconv -f UTF-16LE -t UTF-8 \"/root/.wine-mt5/drive_c/Program Files/HFM Metatrader 5/MQL5/logs/*.log\" 2>/dev/null' | tail -50"

# Filter errors
ssh root@166.88.227.177 "docker exec lumine-mt5 sh -c 'iconv -f UTF-16LE -t UTF-8 \"/root/.wine-mt5/drive_c/Program Files/HFM Metatrader 5/MQL5/logs/*.log\" 2>/dev/null' | grep -aE 'error|4014|UNREACH'"

# Check EA status
ssh root@166.88.227.177 "docker exec backend-redis-1 redis-cli HGETALL mt5:status"
```

## ⚙️ MT5 Configuration

### Whitelist WebRequest

**CRITICAL:** EA harus whitelist domain untuk HTTP requests.

**Method 1: GUI (Recommended for new builds)**
1. Buka noVNC
2. Tools → Options → Expert Advisors
3. Scroll ke "Allow WebRequest for listed URL:"
4. Ketik: `http://lumine.biz.id`
5. Klik OK

**Method 2: terminal.ini (For older builds)**
```bash
# WARNING: Format berbeda per MT5 build!
# Build < 6140: terminal.ini dengan ANSI splice
# Build 6140: common.ini (set via GUI only)

ssh root@166.88.227.177 "docker exec lumine-mt5 python3 /tmp/patch_whitelist.py"
```

### Profile & Charts

**Location:**
```
/root/.wine-mt5/drive_c/Program Files/HFM Metatrader 5/
├── Profiles/Charts/Default/
│   └── chart01.chr  — Chart profile dengan EA
└── MQL5/Profiles/Charts/Default/
    └── chart01.chr  — Alternative location
```

**Chart .chr Format (UTF-16LE):**
```
[Chart]
Symbol=EURUSD
Period=1
...
[Expert]
Enabled=1
Path=Experts\LumineEA.ex5
Inputs=InpProxyURL=http://lumine.biz.id/mt5-proxy;InpSeedSymbols=EURUSD,XAUUSD;
```

### Portable Mode

MT5 di Lumine berjalan dalam **portable mode**:
- Data folder: `<install_dir>/`
- Bukan: `AppData/Roaming/MetaQuotes/Terminal/<hash>/`

**Verify:**
```bash
ls "/root/.wine-mt5/drive_c/Program Files/HFM Metatrader 5/portable.txt"
```

## 🚨 Common Issues

### Error 4014 — WebRequest Not Whitelisted

**Symptoms:**
```
LumineEA: proxy UNREACHABLE at PollCommands code=4014
```

**Fix:** See [[#Whitelist WebRequest]] above.

**Root Cause:** MT5 build 6140 menyimpan whitelist di `common.ini`, bukan `terminal.ini`.

---

### EA Not Attaching to Chart

**Symptoms:**
- Redis status kosong
- Log tidak ada "v4 ready"

**Debug:**
```bash
# Check if .chr exists
ssh root@166.88.227.177 "docker exec lumine-mt5 ls -la '/root/.wine-mt5/drive_c/Program Files/HFM Metatrader 5/Profiles/Charts/Default/'"

# Check EA .ex5 exists
ssh root@166.88.227.177 "docker exec lumine-mt5 ls -la '/root/.wine-mt5/drive_c/Program Files/HFM Metatrader 5/MQL5/Experts/LumineEA.ex5'"
```

**Fix:**
1. Copy chart01.chr dengan EA attached
2. Restart MT5
3. Verify EA init in logs

---

### REPLAY_DETECTED — Duplicate Ticks

**Symptoms:**
```
REPLAY_DETECTED: tick already processed
```

**Fix:** EA v4.12+ sudah handle dengan `last_tick_time` check.

---

### EA Build Not Numeric

**Symptoms:**
```bash
redis-cli HGET mt5:status ea_build  # returns "__DATE__"
```

**Fix:** EA v4.13+ convert `__DATE__` ke integer.

---

## 📚 References

- [[Error Encyclopedia]] — Semua error MT5/EA
- [[Deployment Runbook]] — Deploy EA
- [[Architecture Overview]] — System design
- `scripts/deploy/mt5/LumineEA.mq5` — Source code


## Multi-Instance (Crypto)

23 Aug 2026 — EA crypto instance (Exness BTCUSD) untuk streaming 24/7.

### Arsitektur
- EA crypto (`/opt/lumine-ea-crypto/LumineEA.mq5`) = copy EA HFM + InpProxyURL = `http://lumine.biz.id/mt5-proxy-crypto`
- Container `lumine-mt5-crypto` mount `/opt/lumine-ea-crypto:/opt/lumine-ea:ro`
- Caddy route `/mt5-proxy-crypto/*` → strip prefix → proxy `redis-http-proxy:8765`
- **Caddy 2.11.4 TIDAK bisa menambah header/query ke upstream** → EA crypto tambah `?instance=crypto` sendiri di HttpPostJson
- Whitelist WebRequest: `AllowWebRequest=http://lumine.biz.id` + `WebRequestUrl` hash WAJIB ada di common.ini
- EA parameter input di chart01.chr OVERRIDE default source

### Redis Keys (terpisah dari HFM)
- `mt5crypto:status` — HSET, TTL 90s
- `mt5crypto:logs` — LIST, trim 200
- `mt5crypto:commands` — LIST, BRPOP per-instance
- `mt5:ticks` — SHARED (symbol-generic)
- `mt5:seed_bars` — SHARED (symbol-generic)

### Proxy `_ns()` detection (priority)
1. Query param `?instance=...` (EA crypto kirim `?instance=crypto`)
2. Header `X-Instance: ...` (test internal)
3. Default → `mt5:`

### PITFALLS
- Entrypoint hanya copy EA ke Common/MQL5 — MT5 pakai MQL5/Profiles/Charts/Default/chart01.chr untuk parameter
- chart01.chr parameter input override default source → perlu update chart01.chr juga
- `|| true` WAJIB di compile command (`set -euo pipefail` → crash-loop tanpa ini)
- WebRequestUrl hash di common.ini WAJIB ada — tanpa hash, whitelist tidak aktif (4014)
