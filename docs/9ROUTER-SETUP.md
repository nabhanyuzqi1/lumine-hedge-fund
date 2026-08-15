# 9router LLM Gateway Setup

## Status Saat Ini (15 Aug 2026)

- **Container**: `9router` (Up 23 hours, port 20128:20128)
- **API Key**: `sk-fc7...9ad5` (valid, stored di `/app/data/db/data.sqlite`)
- **Provider Credentials**: **0 aktif** (blocker committee feed)
- **Database**: `/var/lib/docker/volumes/backend_9router_data/_data/db/data.sqlite`

```sql
SELECT * FROM providerConnections; -- 0 rows (credentials HILANG sejak 14 Aug)
SELECT * FROM usageHistory WHERE status='ok' LIMIT 3;
-- Row 1: 14 Aug 10:08 | opencode/deepseek-v4-flash-free | 84→16 tokens | OK
-- Row 2-7: sama, provider opencode sukses — SEKARANG CREDENTIALS DIHAPUS
```

## Blocker Impact

### Committee Feed "No committee activity yet"
- **Root cause**: AutoGen pipeline (`pyautogen`) tidak bisa panggil LLM
- **Test konfirmasi**:
  ```bash
  curl -H "Authorization: Bearer sk-fc7..." \
    http://9router:20128/v1/chat/completions \
    -d '{"model":"deepseek/deepseek-chat","messages":[...]}'
  # → {"error":{"message":"No active credentials for provider: deepseek"}}
  ```

### Models Available (8,000+ models) tapi 0 Working
```bash
curl -H "Authorization: Bearer sk-fc7..." http://9router:20128/v1/models
# → 8000+ models listed (alicode-intl, anthropic, ag, blackbox, ...)
# TAPI semua return "No active credentials for provider: <name>"
```

---

## Setup Instructions

### 1. Akses UI
```
URL: http://lumine.biz.id:20128
```
- **Tidak ada Caddy route** (belum di-mount ke `/autogen-studio`)
- Akses direct via port :20128 (307 redirect → login)

### 2. Login
**Password location**:
```bash
ssh root@166.88.227.177
cd /var/lib/docker/volumes/backend_9router_data/_data/db
sqlite3 data.sqlite "SELECT data FROM settings WHERE id=1;"
# → JSON dengan field password (bcrypt hash)
```

**Alternative**: Reset via Docker exec (jika lupa):
```bash
docker exec 9router sh -c "cat /app/data/.env | grep ADMIN_PASSWORD"
# atau cek dokumentasi 9router untuk password default
```

### 3. Setup Provider Credentials

**Recommended providers** (gratis/low-cost):
1. **OpenCode** (`opencode` alias `oc`)
   - Model: `deepseek-v4-flash-free`, `nemotron-3-ultra-free`, `laguna-s-2.1-free`
   - **No API key needed** (free tier)
   - **Verified working kemarin** (7 request sukses 14 Aug)

2. **DeepSeek** (`deepseek`)
   - Model: `deepseek-v4-flash`, `deepseek-chat`
   - API key: https://platform.deepseek.com

3. **OpenAI** (`openai`)
   - Model: `gpt-4o-mini`, `gpt-4o`
   - API key: https://platform.openai.com

4. **Gemini** (`google`)
   - Model: `gemini-2.0-flash-exp`
   - API key: https://makersuite.google.com/app/apikey

**UI Steps**:
1. Login → Settings → Providers
2. Klik "+ Add Provider"
3. Pilih provider (e.g., `opencode` atau `deepseek`)
4. Masukkan credentials:
   - **opencode**: tidak butuh API key (free tier)
   - **deepseek/openai/gemini**: paste API key
5. Test connection → Save
6. Set as **active** (toggle)

### 4. Verify Setup
```bash
# Test models list (harus return >0 models tanpa error)
curl -H "Authorization: Bearer sk-fc7..." \
  http://127.0.0.1:20128/v1/models | grep -c '"id"'

# Test completion (harus return content, bukan error)
curl -H "Authorization: Bearer sk-fc7..." \
  -H "Content-Type: application/json" \
  http://127.0.0.1:20128/v1/chat/completions \
  -d '{
    "model": "oc/deepseek-v4-flash-free",
    "messages": [{"role":"user","content":"Balas: OK"}],
    "max_tokens": 10
  }'
# Expected: {"choices":[{"message":{"content":"OK"}}]}
# NOT: {"error":{"message":"No active credentials..."}}
```

### 5. Update Backend Config (Optional)
Jika model default di `.env` berbeda:
```bash
# /opt/lumine/backend/.env
LLM_GATEWAY_URL=http://9router:20128  # ✓ sudah benar
LLM_GATEWAY_API_KEY=sk-fc7...         # ✓ sudah benar
LLM_DEFAULT_MODEL=oc/deepseek-v4-flash-free  # ← UPDATE jika perlu
```

---

## Architecture

### Flow: AutoGen → 9router → Upstream Provider
```
AutoGen Agent (Python)
  ↓ POST /v1/chat/completions
9router (decolua/9router:latest)
  ↓ route berdasarkan model prefix (oc/deepseek/openai/...)
  ↓ load credentials dari providerConnections table
Upstream Provider API (OpenCode/DeepSeek/OpenAI/Gemini)
  ↓ response
9router
  ↓ normalize response ke OpenAI format
AutoGen Agent
```

### Database Schema
```sql
-- Provider credentials (0 rows saat ini — MUST FIX)
CREATE TABLE providerConnections (
  id TEXT PRIMARY KEY,
  provider TEXT,      -- 'opencode', 'deepseek', 'openai', ...
  authType TEXT,      -- 'api_key', 'oauth', 'none'
  name TEXT,
  email TEXT,
  priority INTEGER,
  isActive INTEGER,   -- 1 = active, 0 = disabled
  data TEXT,          -- JSON: {api_key, base_url, ...}
  createdAt TEXT,
  updatedAt TEXT
);

-- Usage tracking (7 rows dari 14 Aug — sukses via opencode)
CREATE TABLE usageHistory (
  id INTEGER PRIMARY KEY,
  timestamp TEXT,
  provider TEXT,
  model TEXT,
  connectionId TEXT,
  apiKey TEXT,
  endpoint TEXT,
  promptTokens INTEGER,
  completionTokens INTEGER,
  cost REAL,
  status TEXT,       -- 'ok', 'error'
  tokens TEXT,       -- JSON
  meta TEXT          -- JSON
);
```

### Volume Mount
```yaml
# backend/docker-compose.vps.yml (NOT in compose — standalone)
9router:
  image: decolua/9router:latest
  ports:
    - "20128:20128"
  volumes:
    - 9router_data:/app/data  # SQLite DB + JWT secret + machine-id
```

**Data location**:
```
/var/lib/docker/volumes/backend_9router_data/_data/
├── auth/
│   └── cli-secret
├── db/
│   ├── data.sqlite        ← credentials, usage, settings
│   ├── data.sqlite-shm
│   └── data.sqlite-wal
├── logs/
├── jwt-secret
└── machine-id
```

---

## Troubleshooting

### "No active credentials for provider: X"
**Cause**: `providerConnections` table kosong atau `isActive=0`

**Fix**:
1. Akses UI → Settings → Providers
2. Add provider + API key
3. Toggle "Active" = ON
4. Test via curl (lihat Step 4 di atas)

### UI 307 Redirect Loop
**Cause**: Cookie tidak ter-set (CORS/domain mismatch)

**Fix**:
```bash
# Clear browser cookies untuk lumine.biz.id:20128
# Atau akses via http://166.88.227.177:20128 (IP direct)
```

### Container Restart → Credentials Hilang
**Cause**: SQLite corrupt atau volume tidak persist

**Check**:
```bash
docker volume inspect backend_9router_data  # harus ada
ls -la /var/lib/docker/volumes/backend_9router_data/_data/db/
```

**Fix**: Backup volume sebelum restart:
```bash
docker run --rm -v backend_9router_data:/data -v $(pwd):/backup \
  alpine tar czf /backup/9router-backup-$(date +%F).tar.gz /data
```

---

## Next: Caddy Route (Optional)

Untuk akses via `https://lumine.biz.id/autogen-studio` (bukan :20128):

```caddyfile
# /opt/lumine/backend/Caddyfile
lumine.biz.id {
  # ... existing routes ...

  # 9router UI (reverse proxy tanpa auth)
  handle_path /autogen-studio* {
    reverse_proxy 9router:20128 {
      header_up X-Forwarded-Proto {scheme}
      header_up X-Forwarded-Host {host}
    }
  }
}
```

**Rebuild Caddy**:
```bash
cd /opt/lumine/backend
docker compose -f docker-compose.vps.yml up -d --force-recreate caddy
```

---

## Status Evidence

### Before Fix (15 Aug 11:00 UTC)
```
sqlite3> SELECT COUNT(*) FROM providerConnections;
0

curl http://9router:20128/v1/chat/completions (with valid API key)
→ {"error":{"message":"No active credentials for provider: deepseek"}}

Committee feed UI: "No committee activity yet"
```

### After Fix (Expected)
```
sqlite3> SELECT COUNT(*) FROM providerConnections WHERE isActive=1;
≥1

curl http://9router:20128/v1/chat/completions
→ {"choices":[{"message":{"content":"..."}}]}

Committee feed UI: agent messages muncul (AutoGen berhasil panggil LLM)
```
