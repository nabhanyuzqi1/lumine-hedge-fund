---
title: "Error Encyclopedia"
aliases: ["Error Patterns", "Troubleshooting Guide"]
type: concept
status: evergreen
created: 2026-08-23
updated: 2026-08-23
tags: ["#errors", "#debugging", "#troubleshooting"]
---

# Error Encyclopedia

Kumpulan semua error yang pernah terjadi di Lumine + cara fix. DIURUTKAN dari yang paling sering/menyebalkan.

## 🔴 CRITICAL — System Breaking

### 1. MT5 WebRequest 4014 — Whitelist Not Working

**Error:**
```
LumineEA: proxy UNREACHABLE at PollCommands code=4014
```

**Root Cause:**
MT5 build 6140 menyimpan whitelist di `Config/common.ini`, bukan `Config/terminal.ini`. Patch manual ke terminal.ini TIDAK EFEKTIF.

**Fix (Working):**
Set whitelist via GUI MT5:
1. Buka noVNC → MT5 window
2. Tools → Options → Expert Advisors tab
3. Scroll ke "Allow WebRequest for listed URL:"
4. Ketik: `http://lumine.biz.id`
5. Klik OK

**File Locations (for reference):**
- HFM (working): `terminal.ini` punya ANSI-splice `[Experts]\nAllowWebRequest=...`
- Crypto (build 6140): `common.ini` punya `[Experts]` section — TAPI AllowWebRequest harus di-set via GUI

**Pitfall:**
- Jangan patch terminal.ini dengan Python → akan corrupt format
- Jangan assume format sama antar MT5 build
- Selalu verify dengan GUI setelah patch file

---

### 2. DATA_INTEGRITY — Empty/Placeholder ke LLM

**Error:**
```
'kekosongan dan cacat data adalah hal fatal'
```

**Root Cause:**
- API return `null` atau empty string
- Frontend fallback ke 'unavailable'
- Backend kirim mock data ke LLM

**Fix:**
```python
# WRONG
if not data:
    return {"value": "unavailable"}

# RIGHT
if not data:
    raise HTTPException(503, "Data source unavailable")
    # Frontend MUST show offline banner, NOT fake data
```

**Rule:**
- Null ≠ "unavailable" → cacat data
- API gagal → honest empty state + offline indicator
- NEVER hardcode trend/value sebagai fallback

---

### 3. REPLAY_DETECTED — Duplicate Tick Processing

**Error:**
```
REPLAY_DETECTED: tick already processed
```

**Root Cause:**
EA restart → re-seed semua bars → ticks duplikat masuk pipeline

**Fix:**
EA v4.12+ punya `last_tick_time` check:
```mql5
if(tick.time_msc <= g_lastTickTime) return; // skip replay
```

**Verification:**
```bash
redis-cli LLEN mt5:ticks  # harus naik, bukan explode
```

---

## 🟠 HIGH — Deployment Blockers

### 4. Frontend 401 Unauthorized — HMAC Missing

**Error:**
```
GET /api/market/quotes → 401 Unauthorized
```

**Root Cause:**
Frontend tidak punya `VITE_LUMINE_API_KEY` dan `VITE_LUMINE_API_SECRET` di build time.

**Fix:**
```bash
ssh root@166.88.227.177 "cd /opt/lumine/backend && \
  sed -i '/^VITE_LUMINE_API/d' .env && \
  echo 'VITE_LUMINE_API_KEY=web-frontend' >> .env && \
  echo 'VITE_LUMINE_API_SECRET=<secret>' >> .env && \
  docker compose -f docker-compose.vps.yml up -d --build frontend"
```

**Pitfall:**
- `VITE_*` vars MUST be present saat `docker build` → tidak bisa set setelah container jalan
- Rebuild wajib: `--build` flag

---

### 5. Backend Image Baked — Changes Not Reflected

**Error:**
Backend code changes tidak muncul di VPS setelah `git pull`

**Root Cause:**
Backend di-bake ke Docker image → bind mount hanya untuk development

**Fix:**
```bash
ssh root@166.88.227.177 "cd /opt/lumine/backend && \
  git pull && \
  docker compose -f docker-compose.vps.yml up -d --build backend"
```

**ALWAYS:**
- Backend changes → `--build`
- Frontend changes → `--build --force-recreate`

---

### 6. Git Stash Blocking Pull

**Error:**
```
error: Your local changes to the following files would be overwritten by merge
```

**Root Cause:**
Manual config edits di VPS (Caddyfile, docker-compose) masuk working tree

**Fix:**
```bash
git stash  # atau
git checkout --theirs <file> && git add <file>
git pull
git stash pop  # kalau perlu
```

**Prevention:**
- Config changes → commit ke repo, jangan edit manual di VPS
- Pakai `.env` untuk secrets, bukan edit file

---

## 🟡 MEDIUM — Functional Issues

### 7. EA Not Attaching to Chart After Restart

**Error:**
EA tidak init setelah MT5 restart → status Redis kosong

**Root Cause:**
- Profile `.chr` tidak ter-load
- EA path salah
- Session restore meng-override profile

**Fix:**
1. Pastikan `.chr` ada di dua lokasi:
   ```
   MQL5/Profiles/Charts/Default/chart01.chr
   Profiles/Charts/Default/chart01.chr
   ```
2. Hapus chart02-04 dari profile (hanya 1 chart)
3. Restart MT5 → verify EA init di log

**Verification:**
```bash
ssh root@166.88.227.177 "docker exec lumine-mt5 \
  'iconv -f UTF-16LE -t UTF-8 /root/.wine-mt5-crypto/drive_c/Program\ Files/MetaTrader\ 5/MQL5/logs/*.log' \
  | grep 'v4 ready'"
```

---

### 8. EA Build __DATE__ Not Numeric

**Error:**
```
ea_build = "__DATE__"  # string, bukan integer
```

**Root Cause:**
MQL5 `__DATE__` macro return string, bukan timestamp

**Fix:**
```mql5
// EA code
int g_build = (int)StringToInteger(StringSubstr(__DATE__, 0, 4) + 
                                     StringSubstr(__DATE__, 5, 2) + 
                                     StringSubstr(__DATE__, 8, 2));
```

**Verification:**
```bash
redis-cli HGET mt5:status ea_build  # harus integer 20260822
```

---

### 9. LLM Routing Cache Mismatch

**Error:**
LLM router select model A, tapi analyst pakai model B

**Root Cause:**
- Cache key tidak match
- `manual_default` flag tidak ter-set
- `await` coroutine tidak di-await

**Fix:**
```python
# router.py
async def get_model_for_task(task: str) -> str:
    cache_key = f"llm:{task}:{datetime.now().strftime('%Y%m%d%H')}"
    model = await redis.get(cache_key)  # AWAIT!
    if model:
        return model.decode()
    
    # Select model...
    await redis.setex(cache_key, 3600, selected_model)
    return selected_model
```

---

### 10. SSE Connection Drops — Frontend Hangs

**Error:**
SSE stream berhenti, frontend tidak update

**Root Cause:**
- Backend crash
- Redis timeout
- Network drop

**Fix:**
Frontend auto-reconnect:
```typescript
useEffect(() => {
  const es = new EventSource('/api/sse/status');
  es.onerror = () => {
    setTimeout(() => window.location.reload(), 5000);
  };
}, []);
```

---

## 🟢 LOW — Annoyances

### 11. CI Test Fails — Import Error

**Error:**
```
ImportError: cannot import name 'X' from 'Y'
```

**Root Cause:**
Test import module yang tidak ada atau path salah

**Fix:**
```bash
cd backend
env -u PYTHONPATH .venv/Scripts/python.exe -m pytest tests/unit/ -q
```

**Pitfall:**
- Windows: pakai `.venv/Scripts/python.exe`, bukan `python`
- Jangan rely on global PYTHONPATH

---

### 12. Candlestick Chart Volume Test Fails

**Error:**
```
AssertionError: expected volume series to be rendered
```

**Root Cause:**
Volume histogram dihapus dari chart → test outdated

**Fix:**
Hapus test untuk volume series, update test untuk OHLC only

---

## 📚 Error Pattern Reference

| Error Code | Severity | Category | Doc Link |
|------------|----------|----------|----------|
| 4014 | CRITICAL | MT5/EA | [[#1. MT5 WebRequest 4014]] |
| DATA_INTEGRITY | CRITICAL | Backend | [[#2. DATA_INTEGRITY]] |
| REPLAY_DETECTED | CRITICAL | EA | [[#3. REPLAY_DETECTED]] |
| 401 | HIGH | Auth | [[#4. Frontend 401]] |
| Image Baked | HIGH | Deploy | [[#5. Backend Image Baked]] |
| Git Stash | HIGH | Deploy | [[#6. Git Stash Blocking]] |

---

## 🔧 Debug Workflow

```bash
# 1. Check VPS health
ssh root@166.88.227.177 "docker ps | grep -E 'backend|redis|caddy'"

# 2. Check logs
ssh root@166.88.227.177 "docker logs backend --since 5m 2>&1 | tail -30"

# 3. Check Redis
ssh root@166.88.227.177 "docker exec backend-redis-1 redis-cli HGETALL mt5:status"

# 4. Check EA
ssh root@166.88.227.177 "docker exec lumine-mt5 cat /tmp/ea.log | grep -E 'error|4014|UNREACH'"

# 5. Check MT5 window (via noVNC)
# https://lumine.biz.id/novnc/vnc.html
```

---

> [!tip] Prevention
> - Baca [[Deployment Runbook]] sebelum deploy
> - Run CI lokal sebelum push
> - Check [[Error Encyclopedia]] kalau ada error
> - Document error baru di sini
