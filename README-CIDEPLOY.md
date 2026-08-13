# 🚀 CI/CD DEPLOYMENT GUIDE - Lumine Hedge Fund Platform

**Goal:** Deploy production environment via GitHub Actions (GitOps workflow)  
**VPS Target:** `166.88.227.177`  
**Strategy:** Build → Test → Deploy → Verify → Backup pipeline

---

## 📋 QUICK START CHECKLIST

Before running any deployments, complete these steps in order:

### Phase 1: Preparation (Local Machine) ⏱️ ~15 min

- [ ] **Generate deploy SSH key** (separate from personal keys!)
  ```bash
  cd /Users/nabhan/Dev/lumine-hedge-fund
  ssh-keygen -t ed25519 -f id_lumine_deploy -C "lumine-deploy" -N ""
  ```

- [ ] **Add deploy public key to VPS**
  ```bash
  # Copy to clipboard first
  cat id_lumine_deploy.pub
  
  # Then manually add to VPS root authorized_keys via SSH:
  ssh -i id_rsa.priv root@166.88.227.177
  mkdir -p ~/.ssh && chmod 700 ~/.ssh
  echo "PASTE_PUBLIC_KEY_HERE" >> ~/.ssh/authorized_keys
  chmod 600 ~/.ssh/authorized_keys
  exit
  ```

- [ ] **Test deploy key works**
  ```bash
  ssh -i id_lumine_deploy -o StrictHostKeyChecking=no root@166.88.227.177 hostname
  # Expected output: host1785957413
  ```

- [ ] **Generate environment variables** (if not already set)
  ```bash
  DB_PASSWORD=$(openssl rand -base64 24)
  HMAC_SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")
  LLM_GATEWAY_API_KEY=$(uuidgen)
  echo "DB_PASSWORD=$DB_PASSWORD"
  echo "HMAC_SECRET_KEY=$HMAC_SECRET_KEY"
  echo "LLM_GATEWAY_API_KEY=$LLM_GATEWAY_API_KEY"
  ```

### Phase 2: GitHub Secrets Configuration ⏱️ ~5 min

Navigate to: https://github.com/nabhanyuzqi1/lumine-hedge-fund/settings/secrets/actions

Click **"New repository secret"** for each item below:

| Secret Name | Value | Where to get it |
|-------------|-------|-----------------|
| `DEPLOY_HOST` | `166.88.227.177` | Hardcoded target |
| `DEPLOY_USER` | `root` | Hardcoded target |
| `DEPLOY_SSH_KEY` | Paste entire contents of `id_lumine_deploy` | File on your machine (include BEGIN/END lines) |
| `DB_PASSWORD` | Generated password | Step above or existing config |
| `HMAC_SECRET_KEY` | 64-char hex string | Step above or existing config |
| `LLM_GATEWAY_API_KEY` | UUID or API key | Step above or 9router setup |
| `VNC_PASSWORD` | `LumineVnc!2026` | Default per plan |
| `GITHUB_BACKUP_TOKEN` (optional) | Personal access token | For backup upload feature |

**⚠️ CRITICAL SECURITY NOTES:**
- NEVER commit `.env` files with real secrets to Git
- NEVER share private keys (`id_lumine_deploy`) publicly
- NEVER use your personal SSH key (`id_rsa.priv`) for automation
- Rotate all secrets quarterly or after personnel changes

### Phase 3: Template Configuration ⏱️ ~5 min

Create/update `.env.template` at repository root with all required variables. Ensure it matches secrets format exactly.

```bash
cd /Users/nabhan/Dev/lumine-hedge-fund
cat > .env.template << 'EOF'
# Environment template for production deployment
# DO NOT COMMIT ACTUAL .env FILE WITH REAL SECRETS!

DB_PASSWORD=<GENERATE_SECURE_PASSWORD>
HMAC_SECRET_KEY=<GENERATE_RANDOM_64_CHAR_HEX>
LLM_GATEWAY_API_KEY=<GENERATE_UUID>
VNC_PASSWORD=LumineVnc!2026

POSTGRES_DB=lumine
POSTGRES_USER=luminous_app
REDIS_HOST=redis
REDIS_PORT=6379

APP_ENV=production
LOG_LEVEL=INFO
EOF

git add .env.template
git commit -m "chore: add production environment template"
git push origin main
```

### Phase 4: Trigger First Deployment 🎯

**Option A: Manual Deploy (Recommended for first time)**

1. Go to: https://github.com/nabhanyuzqi1/lumine-hedge-fund/actions
2. Select **"Deploy"** workflow under Recent workflows
3. Click **"Run workflow"** button
4. Choose branch: `main`
5. Click blue **"Run workflow"** button again
6. Watch logs progress (~5-10 minutes total)

**Option B: Auto Deploy (Push-based)**

Just push any code changes to `main` branch and monitoring will auto-trigger:
```bash
git add .
git commit -m "feat: some change"
git push origin main
```

---

## 🔍 VERIFICATION STEPS

After deployment completes, verify everything works:

### Immediate Checks
```bash
# SSH into VPS
ssh -i id_rsa.priv root@166.88.227.177

# Check containers are healthy
docker ps -a --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

# Verify backend API responds
curl http://localhost:8000/api/health

# Check database connectivity
docker exec postgresql pg_isready -U luminous_app

# Test Redis
docker exec redis redis-cli ping
```

### Expected Services Running
- ✅ `postgresql` - Database server (port 5432 internal)
- ✅ `redis` - Cache/broker (port 6379 internal)
- ✅ `backend-api` - FastAPI application (port 8000 loopback)
- ✅ `mt5` - MT5 Wine desktop (ports 5900, 6901 loopback)
- ✅ `9router` - LLM gateway (port 20128 public)
- ✅ `headroom` - Resource control (internal only)

### Control Plane Access (via Caddy + Authelia)
Access URLs (configure Caddyfile as needed):
- Homepage dashboard: `https://166.88.227.177/homepage/`
- Uptime Kuma: `https://166.88.227.177/uptime-kuma/`
- Dozzle logs: `https://166.88.227.177/dozzle/`
- Landing page: `https://166.88.227.177/`

Authentication via Authelia SSO required for protected routes.

---

## 🛡️ MONITORING & ALERTS

### GitHub Actions Monitoring
- Workflow runs logged at: https://github.com/nabhanyuzqi1/lumine-hedge-fund/actions
- View recent runs, retry failed jobs, inspect logs
- Enable notifications for failures

### VPS Health Checks
Configure Uptime Kuma (`control-uptime-kuma`) to monitor:
- Backend API endpoint health
- PostgreSQL availability
- Redis connectivity
- Container uptime status

### Log Aggregation
Use Dozzle (`control-dozzle`) for real-time container log viewing:
- No need to run `docker logs -f` manually
- Browser-based terminal access
- Search and filter capabilities

---

## 🆘 TROUBLESHOOTING

### Deployment Fails Immediately
**Symptom:** Workflow fails at "Setup SSH" step  
**Cause:** Wrong SSH key or missing secret  
**Fix:** 
1. Verify `DEPLOY_SSH_KEY` contains entire private key text (BEGIN/END included)
2. Ensure key matches public key added to VPS
3. Check key permissions: `chmod 600 id_lumine_deploy`

### Containers Won't Start
**Symptom:** `docker compose up -d` succeeds but services unhealthy  
**Cause:** Missing env vars, database init issues  
**Fix:**
```bash
ssh -i id_rsa.priv root@166.88.227.177
cd /opt/lumine
docker compose logs backend-api --tail 50  # Check error messages
docker compose down && docker compose up -d --force-recreate
```

### API Returns 500 Error
**Symptom:** Backend starts but `/api/health` fails  
**Cause:** Database migration incomplete, connection refused  
**Fix:**
```bash
docker exec postgresql psql -U luminous_app -d lumines -c "SELECT version();"
docker exec backend-api python -m luminery.lumine.scripts.migrate upgrade head
```

### Memory/CPU Exhausted
**Symptom:** Containers OOM killed constantly  
**Cause:** Not enough RAM on VPS  
**Fix:** Upgrade VPS plan to minimum 4GB RAM, optimize Docker memory limits:
```bash
cat > docker-compose.prod.yml << 'EOF'
services:
  backend-api:
    deploy:
      resources:
        limits:
          cpus: '1.0'
          memory: 1G
EOF
```

---

## 🔄 ROLLBACK PROCEDURE

If deployment breaks production:

### Automatic Rollback
Workflow includes built-in rollback on failure step (see `deploy-v2.yml`). Triggers automatically when deployment fails.

### Manual Rollback
```bash
# Stop current broken services
ssh -i id_rsa.priv root@166.88.227.177
cd /opt/lumine
docker compose -f docker-compose.prod.yml down

# Restore from latest backup
ls -lt /root/lumine-backups/*.tar.gz | head -1
tar xzf /root/lumine-backups/<backup-file>.tar.gz -C /opt/lumine/

# Restart clean state
docker compose -f docker-compose.prod.yml up -d
```

### Emergency VPS Rebuild
```bash
# Contact hosting provider support
# Request full VPS reinstall from snapshot
# Or provision fresh VPS and deploy from git
```

---

## 📊 COST OPTIMIZATION

### Reduce Docker Resource Usage
```bash
# Set memory limits per container
nano docker-compose.prod.yml
# Add deploy.resources.limits sections
# Example:
#   backend-api:
#     deploy:
#       resources:
#         limits:
#           memory: 1G

# Prune unused images monthly
ssh root@166.88.227.177 "docker system prune -a -f"
```

### Optimize Build Cache
GitHub Actions caches Docker layers between runs for faster builds. Monitor cache usage and clean periodically if approaching limits.

---

## 📞 SUPPORT CONTACT

- **Documentation Issues:** Check `docs/11-infrastructure/` folder
- **Deployment Problems:** Review workflow logs first
- **Security Concerns:** Contact security officer immediately
- **Emergency VPS Access:** Use personal key `id_rsa.priv`

---

## ✨ NEXT STEPS

After successful first deployment:
1. [ ] Schedule automated daily backups (cron job on VPS)
2. [ ] Configure SSL/TLS certificates (Caddy handles this automatically)
3. [ ] Set up monitoring alerts (Slack/PagerDuty integration)
4. [ ] Document emergency procedures for operations team
5. [ ] Plan disaster recovery test (quarterly)
6. [ ] Establish key rotation schedule (quarterly)

**🎉 Congratulations!** Your Lumine platform is now deployed via secure CI/CD pipeline!
