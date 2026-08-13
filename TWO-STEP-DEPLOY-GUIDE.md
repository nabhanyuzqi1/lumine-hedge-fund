# 🚀 TWO-STEP VPS DEPLOYMENT GUIDE

**Problem:** Fresh Ubuntu server = empty (no Docker, no tools installed)  
**Solution:** 2-phase approach to get everything working!

---

## ⚡ QUICK OVERVIEW

### Phase 1: Bootstrap Server (Run ONCE) ⚙️
**What it does:** Installs ALL prerequisites on FRESH server
- Updates Ubuntu system
- Installs Docker & Docker Compose
- Configures firewall (UFW + Fail2Ban)
- Creates directory structure
- Clones Git repository
- Deploys basic control plane services

**When to run:** First time on fresh VPS ✅

**Time required:** ~15-20 minutes

---

### Phase 2: Deploy Application (Regular) 🎯
**What it does:** Deploys your actual Lumine application
- Builds backend containers
- Transfers configuration files
- Starts all services
- Health checks verification
- Automated backups

**When to run:** After bootstrap is done ✅  
**Automation:** Push code → Auto-deploy OR Manual trigger

**Time required:** ~8-12 minutes

---

## 📋 STEP-BY-STEP EXECUTION

### PHASE 1: Bootstrap Fresh Server (FIRST TIME ONLY!)

#### Method A: Via GitHub Actions (Recommended)

1. **Go to Actions tab:**
   https://github.com/nabhanyuzqi1/lumine-hedge-fund/actions

2. **Select "Deploy" workflow**

3. **Click "Run workflow"** button

4. **IMPORTANT:** In dropdown, select **"Bootstrap Fresh Server"** (not "Application Update")

5. **Click blue "Run workflow" button**

6. **Watch logs progress (~15-20 min):**
   - Setup SSH connection
   - Transfer bootstrap script
   - Install Docker
   - Configure firewall
   - Create directories
   - Clone repository

7. **Expected SUCCESS:**
   ```
   ✅ BOOTSTRAP COMPLETE!
   Services installed:
   - Docker Engine ✅
   - Control Plane ✅
   - Lumine Repository ✅
   ```

✅ **Done!** Your server now has Docker and infrastructure ready!

---

#### Method B: Manual Bootstrap (Alternative)

If you prefer manual setup:

```bash
# 1. SSH into fresh VPS
ssh -i id_lumine_deploy root@166.88.227.177

# 2. Run these commands sequentially:
apt update && apt upgrade -y
apt install -y curl wget docker.io git

# 3. Install Docker Compose plugin
curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
chmod +x /usr/local/bin/docker-compose

# 4. Create directory structure
mkdir -p /opt/lumine/backend /srv/control-plane /root/lumine-backups
chmod 700 /root/lumine-backups

# 5. Clone repository from local (if you have it)
cd /opt/lumine
git clone https://github.com/nabhanyuzqi1/lumine-hedge-fund.git . || echo "Skip repo clone"

# 6. Exit and test Docker
docker --version
exit
```

---

### PHASE 2: Deploy Application (After Bootstrap)

#### Option A: Automatic (Push to main)

Just push any change to `main` branch:

```bash
git add .
git commit -m "feat: some improvement"
git push origin main
```

**Workflow auto-triggers:**
1. Build backend container
2. Transfer to VPS
3. Start services
4. Verify health
5. Complete ✅

---

#### Option B: Manual Trigger

1. **Go to Actions:** https://github.com/nabhanyuzqi1/lumine-hedge-fund/actions

2. **Select "Deploy" workflow**

3. **Click "Run workflow"**

4. **IMPORTANT:** Select **"Application Update"** 

5. **Click blue "Run workflow"**

6. **Wait for completion (~8-12 min)**

---

## 🔍 VERIFICATION CHECKLIST

### After Bootstrap Phase:

Verify Docker is installed:
```bash
ssh -i id_lumine_deploy root@166.88.227.177
docker --version    # Should show version number
docker compose version  # Should work
```

Directory structure exists:
```bash
ls -la /opt/lumine/    # Should show lumines folder
ls -la /srv/control-plane/  # Should exist
```

Repository cloned:
```bash
cd /opt/lumine && ls  # Should see code files
```

✅ **Bootstrap successful if:** Docker works + directories exist

---

### After Application Deployment:

Check containers running:
```bash
ssh -i id_lumine_deploy root@166.88.227.177
docker ps -a --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
```

Expected output:
```
NAME            STATUS               PORTS
postgresql      Up (healthy)         5432/tcp
redis           Up (healthy)         6379/tcp
backend-api     Up (healthy)         127.0.0.1:8000->8000/tcp
mt5             Up                   127.0.0.1:5900->5900/tcp
9router         Up                   0.0.0.0:20128->20128/tcp
headroom        Up                   
```

Test API health:
```bash
curl http://localhost:8000/api/health
```

Expected JSON response with `"status": "healthy"`

✅ **Deployment successful if:** All containers healthy + API responding

---

## 🆘 TROUBLESHOOTING

### Issue: Bootstrap fails at "Install Docker"

**Symptoms:** Workflow shows error during package installation  
**Cause:** Network issue or Ubuntu package repository problem  

**Fix:**
1. Wait 5 minutes, retry bootstrap
2. Check if internet connectivity works from GHA runner
3. Try manual bootstrap method instead

---

### Issue: "Permission denied" after bootstrap

**Symptoms:** SSH key not accepted  
**Cause:** Key mismatch or wrong format in secrets  

**Fix:**
1. Delete `DEPLOY_SSH_KEY` secret
2. Re-run: `cat id_lumine_deploy` in terminal
3. Copy ENTIRE output (all lines)
4. Create new secret with exact content
5. Retry bootstrap

---

### Issue: Containers won't start after deployment

**Symptoms:** Docker compose up succeeds but unhealthy  
**Cause:** Missing environment variables or database init  

**Fix:**
1. Check `/opt/lumine/backend/.env` file on VPS contains all secrets
2. Manually SSH and inspect errors:
   ```bash
   docker logs backend-api --tail 50
   docker logs postgresql --tail 50
   ```
3. Apply database migrations:
   ```bash
   docker exec postgresql psql -U luminous_app -d lumines -c "SELECT version();"
   docker exec backend-api python -m alembic upgrade head
   ```

---

### Issue: Bootstrapped successfully but deployment fails

**Symptoms:** Bootstrap phase green check ✓, but application deployment red ❌  
**Cause:** Secrets missing or incorrect values  

**Fix:**
1. Verify all 7 secrets are uploaded to GitHub:
   - DEPLOY_HOST ✅
   - DEPLOY_USER ✅
   - DEPLOY_SSH_KEY ✅
   - DB_PASSWORD ✅
   - HMAC_SECRET_KEY ✅
   - LLM_GATEWAY_API_KEY ✅
   - VNC_PASSWORD ✅

2. Check secret values match expectations (especially passwords)

3. Retry deployment workflow

---

## 📊 WHEN TO USE WHICH PHASE?

| Scenario | Action Required | Phase to Use |
|----------|----------------|--------------|
| Fresh Ubuntu VPS (just provisioned) | Install everything first | ✅ **Bootstrap Phase** |
| Already bootstrapped, updating code | Deploy new version | ✅ **Application Phase** |
| Want to force reinstall everything | Wipe and start fresh | ✅ **Bootstrap Phase** |
| Need to rollback to previous version | Use CI/CD revert | ✅ **Application Phase** |
| Add new feature to codebase | Push to main branch | ✅ **Auto-application** |
| Testing changes without pushing | Manual trigger | ✅ **Manual Application** |

---

## ⚠️ CRITICAL REMINDERS

### During Bootstrap:
- [ ] Don't interrupt the process (~15-20 min)
- [ ] Let Git clone complete
- [ ] Wait for success confirmation
- [ ] Verify Docker works before proceeding

### Before Application Phase:
- [ ] Confirm bootstrap completed successfully
- [ ] All 7 GitHub secrets configured
- [ ] Test SSH connectivity one more time
- [ ] Have personal SSH key (`id_rsa.priv`) accessible as backup

### After Both Phases:
- [ ] Document that bootstrap was completed (date, notes)
- [ ] Never run bootstrap again unless wiping server
- [ ] Future updates use application phase only
- [ ] Set up automated daily backups

---

## 🔄 SUMMARY FLOWCHART

```
Fresh VPS → Phase 1: Bootstrap
                ↓
        Docker + Infrastructure Ready
                ↓
Phase 2: Deploy App (First Time)
                ↓
        All Services Running
                ↓
Future Changes: Push Code → Auto-Deploy
```

**Total time to production:** ~25-30 minutes (first time)  
**Ongoing updates:** ~5-10 minutes per deployment

---

## ✨ NEXT STEPS AFTER SETUP

Once both phases complete successfully:

1. **Set up monitoring:** Configure Uptime Kuma alerts
2. **Schedule backups:** Daily cron job for database dumps
3. **Document procedure:** Write team access procedures
4. **Plan DR test:** Quarterly disaster recovery simulation
5. **Establish rotation:** Quarterly SSH key rotation

---

**Ready to deploy?** Start with Phase 1 (Bootstrap) on fresh VPS! 🚀✨

Questions? Review troubleshooting section above! ~★(◕‿◕) ノ💪
