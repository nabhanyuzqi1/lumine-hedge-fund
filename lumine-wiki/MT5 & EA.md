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


## PITFALL: Candle Close Harus Sinkron per Timeframe (24 Aug 2026)

Agregasi bar (5m/15m/1h/4h dari bar 1m) WAJIB pakai first-open / last-close:

```python
# BENAR (array_agg — pattern query 15m di market.py):
func.array_agg(open ORDER BY ts)[1]                                        # open bar PERTAMA
func.array_agg(close ORDER BY ts)[array_length(array_agg(close ORDER BY ts), 1)]  # close bar TERAKHIR

# SALAH (MIN/MAX — close mengikuti nilai ekstrem):
func.min(open)  # open bukan dari bar pertama
func.max(close) # close mengikuti high — candle 1h "menyeret" pola 1m → kotor
```

Sinkronisasi: close bar 1h = close bar 15m terakhir dalam bucket 1h (bukan max/ekstrem).

### Warna Candle (lightweight-charts)
CSS `var(--...)` TIDAK di-resolve oleh canvas lightweight-charts → candle hitam.
Gunakan hex langsung: up `#34d399` (hijau), down `#f0555b` (merah) — dari CHART_COLORS di lib/chart-theme.ts.



## PITFALL: PK bars_15m/1h/4h/1d Wajib (ts, symbol) — TIDAK ts-only (24 Aug 2026)

**Gejala:** candle XAUUSD & BTCUSD "kotor" — hole parah di 15m/1h (XAU cuma
24 bar/24jam dari 96; BTC 1h 18 dari 24), close tidak sinkron antar symbol.

**Root cause:** bars_15m/1h/4h/1d PK = ts SAJA (tanpa symbol). Karena BTCUSD
& XAUUSD punya bucket ts yang SAMA → `ON CONFLICT DO NOTHING` → bar symbol
kedua TIDAK PERNAH masuk. Migration untuk 4 tabel:

```sql
ALTER TABLE bars_15m DROP CONSTRAINT bars_15m_pkey;
ALTER TABLE bars_15m ADD PRIMARY KEY (ts, symbol);
-- (1h, 4h, 1d sama)
DELETE FROM bars_15m; DELETE FROM bars_1h; DELETE FROM bars_4h; DELETE FROM bars_1d;
```

ORM `_make_bar_table` (models.py) WAJIB `symbol primary_key=True` untuk semua
tabel (partitioned ATAU tidak) — sebelumnya `primary_key=partitioned` → 15m+
ts-only → ON CONFLICT gagal setelah migration DB.

**Seed worker:** skip 15m juga (hanya 1m/5m dari EA). Semua TF ≥ 15m dari
agregasi lokal (first-open/last-close) supaya close SINKRON antar symbol.

## PITFALL: LLM Routing Tidak Baca Setting Manual Default (24 Aug 2026)

**Gejala:** user set default model (mis. `r9u/routers9/stealth/ox-alpha`) via
superadmin, tapi decision cycle SELALU pakai `ag/gemini-3.7-flash-high`.

**Root cause 3-lapis:**
1. `auto_select_best_model` probe_pool = `ranked[:8]` (skor tier heuristic)
   → model rank-rendah (ox-alpha tier2) TIDAK PERNAH di-probe → tidak masuk
   `available_models`.
2. rpc worker filter chain: `if m not in avail: continue` → chain manual
   kosong → `filtered = avail[:3]` = gemini (ranking heuristic).
3. Circuit breaker 120s TIDAK pernah di-reset walau probe sukses → model
   sehat tetap skip.

**Fix 3 lapis (backend/src/lumine/):**
- `routing_overlay.py` `auto_select_best_model`: manual default model SELALU
  masuk probe_pool (+ probe OK → `close_circuit()`).
- `rpc/worker.py`: manual_default TIDAK difilter avail heuristic — hanya
  circuit-open yang skip.
Verifikasi: `[ROUTING] chain=['r9u/routers9/stealth/ox-alpha']` di log api.

## noVNC MT5 Crypto (24 Aug 2026)
Route /novnc-crypto WAJIB ada di Caddyfile.prod → `reverse_proxy
lumine-mt5-crypto:6901` (container terpisah). Tanpa itu: **404** — /novnc
hanya ke lumine-mt5 (HFM). WebSocket /novnc-crypto/websockify* TANPA
forward_auth (Caddy 2.11 pecah WS upgrade); halaman di-auth.

## Positioning: Tabel Position Kosong (24 Aug 2026)
GET /api/v1/portfolio/positions pakai list_open → tabel KOSONG saat 0 posisi
open (padahal ada 24 closed history). Fix: PositionRepository.list_recent(50)
→ tampilkan open + closed history.



## PITFALL: PositionSync close-loop — snapshot crypto kosong menutup posisi HFM (24 Agu 2026)

**Gejala:** posisi XAUUSD real (1 open, floating +280) TIDAK pernah muncul di
DB/UI — status selalu closed, updated_at stagnan 19 Agu. User lapor "24
posisi filled tapi belum entry, order tidak masuk EA, LLM tidak tahu posisi".
Tabel position = closed history saja, 0 open.

**Root cause:** `_sync_once` memproses 2 key per cycle:
1. `mt5:positions` (snapshot EA HFM, n=1 posisi XAUUSD) → upsert OPEN ✅
2. `mt5crypto:positions` (snapshot EA crypto, n=0 — EA crypto TIDAK punya
   posisi) → `_upsert_positions([])` → close-loop menutup SEMUA posisi open
   TANPA filter symbol → row XAUUSD (HFM) di-close tiap 10 detik ❌

Jadi tiap cycle: open (dari mt5) → langsung closed (dari mt5crypto). DB
selalu closed walau MT5 real punya posisi open. Sinyal/analyst hanya lihat
0 posisi → order/sinyal duplikat, tidak sinkron.

**Fix (position_sync.py):**
```python
POSITIONS_KEY_SYMBOLS = {"mt5:positions": "XAUUSD", "mt5crypto:positions": "BTCUSD"}
# _sync_once → allowed_symbols={...}
# _upsert_positions(payload, allowed_symbols): close-loop skip pos.symbol
#   not in allowed_symbols
```
Plus: `Position.updated_at` pakai `onupdate=_utcnow` — sleep: sebelumnya
updated_at tetap 19 Agu walau mt5_profit di-update tiap 10s.

**Verifikasi:** SELECT status FROM positions → 1 open (ticket 258048867,
mt5_profit live, updated_at hari ini), 23 closed. LLM thermal dewan baca
posisi open via PositionRepository.

## Catatan EA
- EA HFM kirim snapshot /positions tiap ~10 detik ke `mt5:positions`
- EA crypto kirim ke `mt5crypto:positions` — snapshot [] kalau 0 posisi
- Close-loop JANGAN pernah menutup posisi di luar instance symbol map
