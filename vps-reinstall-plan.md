# VPS REINSTALL SAFETY CHECKLIST - Lumine Hedge Fund Platform
**IP**: 166.88.227.177  
**Date**: 2026-08-13  
**Status**: ⚠️ PENDING USER CONFIRMATION

---

## 🔍 CURRENT VPS STATUS (Snapshot taken before reinstall)

### System Info
- **OS**: Ubuntu 24.04.3 LTS (Noble Numbat)
- **Kernel**: Linux 6.8.0-88-generic x86_64
- **Hostname**: host1785957413
- **Uptime**: ~2 minutes (FRESH INSTALL)
- **SSH Access**: ✅ Confirmed with `id_rsa.priv`

### Disk Usage
```
Filesystem      Size  Used Avail Use% Mounted on
/dev/sda1        77G  1.9G   75G   3% /
```
✅ **97% disk still free** - very clean system!

### Current Services
- Only default Ubuntu services (cron, ssh, systemd, etc.)
- ❌ Docker: NOT installed
- ❌ PostgreSQL: NOT installed
- ❌ Redis: NOT installed
- ❌ Lumine app: NOT deployed

### Data Status
⚠️ **NO DATA TO BACKUP** - VPS appears to be freshly provisioned or wiped

---

## 📋 DEPLOYMENT REQUIREMENTS (from CLAUDE.md)

### Technology Stack Required:
1. **Runtime**: Python 3.11+
2. **API Framework**: FastAPI
3. **AI Orchestration**: Microsoft AutoGen
4. **LLM Gateway**: 9router
5. **Database**: PostgreSQL + Redis
6. **Containerization**: Docker (optional but recommended)
7. **Frontend**: React + Vite + Tailwind (Phase 10)

### Key Applications:
- Backend API (FastAPI)
- AI Agents (AutoGen workers)
- PostgreSQL database
- Redis cache/message broker
- MT5 connection (if trading)
- Frontend dev server (Phase 10)

---

## ✅ REINSTALL DECISION MATRIX

### Option A: FRESH START (Recommended since VPS is empty)
**Pros:**
- Clean slate, no legacy issues
- Fresh security hardening from ground up
- All apps configured correctly for Lumine requirements
- No data loss risk (nothing to lose!)

**Cons:**
- None applicable in this case

### Option B: Keep current state
**Pros:**
- Already running
- Nothing to configure yet

**Cons:**
- No applications deployed yet anyway
- Just wasting resources on blank Ubuntu instance

---

## 🚀 RECOMMENDED ACTION PLAN

### Phase 1: System Setup ⚙️
1. Update OS packages
2. Install Docker & Docker Compose
3. Install PostgreSQL + Redis
4. Configure firewall (UFW)
5. Security hardening (fail2ban, SSH config)

### Phase 2: Lumine Deployment 🦞
1. Clone repository
2. Configure environment variables (.env)
3. Setup PostgreSQL database
4. Setup Redis connections
5. Deploy backend services
6. Configure AutoGen workers
7. Test endpoints

### Phase 3: Verification ✅
1. Health checks on all services
2. API endpoint testing
3. Database connectivity
4. Redis pub/sub working
5. Agent communication tests

---

## ⚠️ CRITICAL WARNINGS

### BEFORE PROCEEDING:
1. [ ] Confirm you want fresh install (no rollback possible)
2. [ ] Verify SSH key backup (`id_rsa.priv`) accessible locally
3. [ ] Confirm port access not blocked by cloud provider
4. [ ] Ensure Git repo accessible if doing git clone
5. [ ] Have environment variables ready (.env file)

### SECURITY NOTES:
- Change default SSH root password after setup
- Consider using non-root user for app deployment
- Enable automatic security updates
- Configure proper firewall rules
- Never commit `.env` files to Git (already in .gitignore?)

---

## 📝 POST-REINSTALL CHECKLIST

After deployment, verify:
- [ ] PostgreSQL accepting connections
- [ ] Redis responding to ping
- [ ] FastAPI backend healthy at `/health`
- [ ] AutoGen agents can communicate
- [ ] Logs writing correctly
- [ ] Firewall allows only necessary ports (22, 8000, etc.)
- [ ] Backup strategy implemented
- [ ] Monitoring/alerting configured

---

## 🆘 EMERGENCY ROLLBACK

If something goes wrong:
1. VPS provider console → Revert to snapshot (if available)
2. Manual SSH rescue mode
3. Re-provision new VPS from scratch
4. Restore from local Git repo

---

**USER CONFIRMATION REQUIRED**: Reply "PROCEED" to begin fresh installation
**OR** request modifications to this plan
