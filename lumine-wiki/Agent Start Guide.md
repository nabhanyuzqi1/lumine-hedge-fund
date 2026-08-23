---
title: "Agent Start Guide"
aliases: ["Start Here", "Checkpoint", "Onboarding"]
type: concept
status: evergreen
created: 2026-08-23
updated: 2026-08-23
tags: ["#guide", "#agent", "#checkpoint"]
---

# Agent Start Guide

> [!important] BACA INI DULU
> Sebelum mulai kerja di Lumine, agent WAJIB baca guide ini + related pages.

## 🚀 Quick Start Checklist

### 1. Load Required Skills

```
skill_view(name='lumine')
skill_view(name='vps-fullstack-debugging')
skill_view(name='mql5-ea-development')
```

### 2. Read Core Files

**Wajib baca:**
1. `CLAUDE.md` di repo root — project context untuk agent
2. `backend/README.md` — backend setup
3. `frontend/README.md` — frontend setup

**Optional tapi recommended:**
- `backend/app/api/` — API endpoints
- `backend/app/sse/` — SSE publishers
- `scripts/deploy/mt5/LumineEA.mq5` — EA source

### 3. Check Current State

```bash
# Backend health
ssh root@166.88.227.177 "docker ps | grep backend"

# Redis status
ssh root@166.88.227.177 "docker exec backend-redis-1 redis-cli HGETALL mt5:status"

# MT5 logs
ssh root@166.88.227.177 "docker exec lumine-mt5 cat /tmp/ea.log | tail -20"
```

### 4. Understand Data Flow

```
MT5 EA → HTTP POST → Redis → Backend API → SSE → Frontend
         ↑                                    ↓
         └────────── Commands (GET) ──────────┘
```

## 📚 Knowledge Sources

| Source | Content | When to Use |
|--------|---------|-------------|
| `CLAUDE.md` | Project overview, conventions | Always |
| `skill: lumine` | VPS, deploy, EA specifics | Backend/MT5 work |
| `skill: vps-fullstack-debugging` | Docker, SSE, HMAC issues | Debug production |
| [[Error Encyclopedia]] | All errors + fixes | Troubleshooting |
| [[Deployment Runbook]] | Deploy procedures | Deployment |
| Session history | Past conversations | Context recovery |

## ❓ Questions to Ask Before Starting

### General
- [ ] Apa task spesifik yang perlu dikerjakan?
- [ ] Apakah ada blocking issue yang perlu di-resolve dulu?
- [ ] Apakah test lokal perlu atau langsung rely on CI?

### Backend Changes
- [ ] Apakah perlu rebuild Docker image? (`docker compose up -d --build`)
- [ ] Apakah ada perubahan Redis schema?
- [ ] Apakah SSE endpoint terpengaruh?

### Frontend Changes
- [ ] Apakah perlu update API types?
- [ ] Apakah ada perubahan UI yang perlu sync dengan backend?
- [ ] Apakah responsive/mobile perlu diperhatikan?

### MT5/EA Changes
- [ ] Apakah EA perlu recompile?
- [ ] Apakah whitelist perlu update?
- [ ] Apakah ada perubahan symbol/timeframe?

### Deployment
- [ ] Apakah CI hijau? (gh run list --limit 1)
- [ ] Apakah ada migration SQL?
- [ ] Apakah perlu restart MT5 container?

## 🛡️ Safety Rules

### CRITICAL — Do Not Violate

1. **DATA INTEGRITY = FATAL**
   - Tidak boleh ada placeholder/mock data yang dikirim ke LLM
   - Empty state harus honest, bukan "unavailable"
   - Null values = cacat data

2. **NO GUESSING**
   - Kalau tidak tahu, bilang tidak tahu
   - Kalau error, investigate dulu baru fix
   - Jangan assume tanpa verify

3. **CI HIJAU BEFORE MERGE**
   - Selalu tunggu CI pass sebelum merge ke dev
   - Test command: `cd backend && env -u PYTHONPATH .venv/Scripts/python.exe -m pytest tests/unit/ -q`

4. **SECRETS MANAGEMENT**
   - Jangan commit secrets
   - Pakai `.env` di VPS (tidak di repo)
   - SSH key only: `~/.ssh/id_lumine_deploy`

5. **PRODUCTION CHANGES**
   - Deploy butuh explicit user confirmation untuk risky changes
   - Backup before destructive operations
   - Test di local dulu kalau memungkinkan

## 🔧 Common Workflows

### Add New Feature
1. Create branch dari `dev`
2. Implement + write tests
3. Run CI locally (optional)
4. Push + create PR
5. Wait CI green
6. Merge to dev
7. Deploy to VPS

### Fix Bug
1. Read [[Error Encyclopedia]] untuk pattern
2. Investigate root cause
3. Write test yang catch bug
4. Fix + verify test passes
5. Document in [[Error Encyclopedia]] kalau pattern baru

### Deploy to VPS
1. Ensure CI green
2. SSH to VPS
3. `git pull origin dev`
4. `docker compose -f docker-compose.vps.yml up -d --build <service>`
5. Verify health endpoints
6. Check logs

### Debug Production Issue
1. Check logs: `docker logs <container> --since 5m`
2. Check Redis: `redis-cli HGETALL mt5:status`
3. Check SSE: `curl https://lumine.biz.id/api/sse/status`
4. Reference [[Error Encyclopedia]]

## 📝 Session Workflow

### Start of Session
```bash
# 1. Pull latest
cd lumine-hedge-fund && git pull

# 2. Check CI
gh run list --limit 1

# 3. Check VPS health
ssh root@166.88.227.177 "docker ps --format 'table {{.Names}}\t{{.Status}}'"
```

### End of Session
```bash
# 1. Push jika ada changes
git push

# 2. Update wiki jika ada knowledge baru
# Tulis ke lumine-wiki/02_Wiki/

# 3. Log di [[00_Meta/log.md]]
```

## 🔗 Deep Dive

- [[Architecture Overview]] — System design
- [[Error Encyclopedia]] — Semua error yang pernah terjadi
- [[Deployment Runbook]] — Step-by-step deploy
- [[MT5 & EA]] — Trading layer
- [[Backend Architecture]] — Python backend
- [[Frontend Architecture]] — React frontend

---

> [!tip] Pro Tips
> - Kalau stuck, search session history dengan `session_search(query='...')`
> - Kalau error baru, dokumentasikan di [[Error Encyclopedia]]
> - Kalau workflow baru berhasil, update guide ini
