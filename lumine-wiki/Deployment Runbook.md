---
title: "Deployment Runbook"
aliases: ["Deploy Guide", "VPS Deployment"]
type: concept
status: evergreen
created: 2026-08-23
updated: 2026-08-23
tags: ["#deploy", "#vps", "#docker", "#runbook"]
---

# Deployment Runbook

Step-by-step guide untuk deploy Lumine ke VPS (166.88.227.177).

## 📋 Prerequisites

- [ ] SSH key: `~/.ssh/id_lumine_deploy`
- [ ] VPN aktif (kalau dari jaringan terbatas)
- [ ] CI hijau di branch `dev`
- [ ] Semua tests passing

## 🚀 Quick Deploy Commands

### Backend
```bash
ssh root@166.88.227.177 "cd /opt/lumine/backend && \
  git pull && \
  docker compose -f docker-compose.vps.yml up -d --build backend"
```

### Frontend
```bash
ssh root@166.88.227.177 "cd /opt/lumine/backend && \
  git pull && \
  docker compose -f docker-compose.vps.yml up -d --build --force-recreate frontend"
```

### MT5/EA
```bash
# 1. Copy EA source
scp scripts/deploy/mt5/LumineEA.mq5 root@166.88.227.177:/opt/lumine-ea/LumineEA.mq5

# 2. Restart MT5 (EA akan compile saat startup)
ssh root@166.88.227.177 "docker restart lumine-mt5"

# 3. Verify
ssh root@166.88.227.177 "docker exec backend-redis-1 redis-cli HGETALL mt5:status"
```

---

## 📦 Full Deployment (Fresh Start)

### Step 1: Prepare VPS

```bash
# SSH to VPS
ssh root@166.88.227.177

# Update system
apt update && apt upgrade -y

# Install Docker
curl -fsSL https://get.docker.com | sh
systemctl enable docker
systemctl start docker

# Install Docker Compose
apt install docker-compose-plugin -y
```

### Step 2: Clone Repository

```bash
cd /opt
git clone https://github.com/username/lumine-hedge-fund.git lumine
cd lumine/backend
```

### Step 3: Setup Environment

```bash
# Create .env file
cat > .env << 'EOF'
# Database
REDIS_URL=redis://redis:6379/0

# Auth
HMAC_SECRET_KEY=<generate-32-char-secret>
VITE_LUMINE_API_KEY=web-frontend
VITE_LUMINE_API_SECRET=<generate-32-char-secret>

# LLM
GEMINI_API_KEY=<key>
DEEPSEEK_API_KEY=<key>
OPENAI_API_KEY=<key>

# MT5 Proxy
MT5_PROXY_SECRET=<secret>

# News RSS
NEWS_RSS_FEEDS=https://www.bbc.com/news/business/rss.xml,https://oilprice.com/rss/main.xml
EOF
```

### Step 4: Deploy Services

```bash
# Start all services
docker compose -f docker-compose.vps.yml up -d --build

# Check status
docker ps
```

### Step 5: Verify Deployment

```bash
# Backend health
curl https://lumine.biz.id/api/health

# Redis
docker exec backend-redis-1 redis-cli PING

# MT5 EA
docker logs lumine-mt5 --since 2m | grep "v4 ready"
```

---

## 🔄 Update Procedures

### Backend Only (Code Changes)

```bash
# 1. Pull latest code
ssh root@166.88.227.177 "cd /opt/lumine/backend && git pull"

# 2. Rebuild backend container
ssh root@166.88.227.177 "cd /opt/lumine/backend && \
  docker compose -f docker-compose.vps.yml up -d --build backend"

# 3. Verify
ssh root@166.88.227.177 "docker logs backend --since 1m | tail -20"
```

### Frontend Only (UI Changes)

```bash
# 1. Pull latest code
ssh root@166.88.227.177 "cd /opt/lumine/backend && git pull"

# 2. Rebuild frontend (MUST use --force-recreate)
ssh root@166.88.227.177 "cd /opt/lumine/backend && \
  docker compose -f docker-compose.vps.yml up -d --build --force-recreate frontend"

# 3. Verify bundle
ssh root@166.88.227.177 "docker exec frontend ls -la /usr/share/nginx/html/assets/ | grep superadmin"
```

### MT5/EA Update

```bash
# 1. Copy EA source to VPS
scp scripts/deploy/mt5/LumineEA.mq5 root@166.88.227.177:/opt/lumine-ea/LumineEA.mq5

# 2. Restart MT5 container (EA will auto-compile)
ssh root@166.88.227.177 "docker restart lumine-mt5"

# 3. Wait for EA init (30-60s)
sleep 60

# 4. Verify EA version
ssh root@166.88.227.177 "docker exec backend-redis-1 redis-cli HGET mt5:status ea_version"
```

### Caddy (Reverse Proxy)

```bash
# 1. Update Caddyfile
ssh root@166.88.227.177 "cd /opt/lumine/backend && git pull"

# 2. Validate config
ssh root@166.88.227.177 "docker exec backend-caddy-1 caddy validate --config /etc/caddy/Caddyfile"

# 3. Reload Caddy
ssh root@166.88.227.177 "docker exec backend-caddy-1 caddy reload --config /etc/caddy/Caddyfile"
```

---

## 🛠️ Maintenance Tasks

### View Logs

```bash
# Backend
ssh root@166.88.227.177 "docker logs backend --since 10m -f"

# Frontend
ssh root@166.88.227.177 "docker logs frontend --since 10m"

# Redis
ssh root@166.88.227.177 "docker logs backend-redis-1 --since 10m"

# Caddy
ssh root@166.88.227.177 "docker logs backend-caddy-1 --since 10m"

# MT5
ssh root@166.88.227.177 "docker logs lumine-mt5 --since 10m"
```

### Restart Services

```bash
# All services
ssh root@166.88.227.177 "cd /opt/lumine/backend && docker compose -f docker-compose.vps.yml restart"

# Single service
ssh root@166.88.227.177 "docker restart backend"
```

### Clean Up

```bash
# Remove unused images
ssh root@166.88.227.177 "docker image prune -a -f"

# Remove unused volumes (CAREFUL!)
ssh root@166.88.227.177 "docker volume prune -f"
```

---

## 🚨 Rollback

### Backend Rollback

```bash
# 1. SSH to VPS
ssh root@166.88.227.177

# 2. Go to previous commit
cd /opt/lumine/backend
git log --oneline -5  # find good commit
git checkout <good-commit-hash>

# 3. Rebuild
docker compose -f docker-compose.vps.yml up -d --build backend

# 4. Verify
docker logs backend --since 1m
```

### Frontend Rollback

```bash
# Same as backend, but with --force-recreate
docker compose -f docker-compose.vps.yml up -d --build --force-recreate frontend
```

---

## 📊 Health Checks

```bash
# Backend API
curl -s https://lumine.biz.id/api/health | jq

# Redis
ssh root@166.88.227.177 "docker exec backend-redis-1 redis-cli INFO | grep connected_clients"

# MT5 EA Status
ssh root@166.88.227.177 "docker exec backend-redis-1 redis-cli HGETALL mt5:status"

# EA Log (last errors)
ssh root@166.88.227.177 "docker exec lumine-mt5 sh -c 'iconv -f UTF-16LE -t UTF-8 /root/.wine-mt5/drive_c/Program\ Files/HFM\ Metatrader\ 5/MQL5/logs/*.log 2>/dev/null' | grep -aE 'error|UNREACH|4014' | tail -10"

# Frontend Bundle
curl -s https://lumine.biz.id/ | grep -o 'src="[^"]*\.js"' | head -5
```

---

## 🔐 Security Checklist

- [ ] `.env` tidak di-commit ke repo
- [ ] SSH key-only auth (no password)
- [ ] Cloudflare tunnel aktif
- [ ] Rate limiting di Caddy
- [ ] CORS hanya untuk lumine.biz.id
- [ ] HMAC secret kuat (32+ char random)
- [ ] API keys tidak expose di frontend bundle

---

## 📝 Deployment Log

Setelah deploy, catat di `00_Meta/log.md`:

```markdown
- [2026-08-23 14:30] Deployed commit abc123 — Backend fix for EA status
  - Services: backend
  - Verification: ✅ All health checks pass
  - Issues: None
```

---

> [!warning] Common Pitfalls
> - Backend changes BUT no `--build` → old image still running
> - Frontend changes BUT no `--force-recreate` → old bundle cached
> - `.env` changes BUT no rebuild → build-time vars not updated
> - MT5 restart BUT EA not compiled → check `/opt/lumine-ea/LumineEA.mq5` exists

---

## 🔗 Related

- [[Error Encyclopedia]] — Troubleshooting
- [[MT5 & EA]] — EA specifics
- [[Architecture Overview]] — System design
