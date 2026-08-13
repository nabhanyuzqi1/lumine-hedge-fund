# 🦞 LUMINE VPS DEPLOYMENT PLAN
**Server:** 166.88.227.177  
**Date:** 2026-08-13  
**Status:** ✅ SSH Connected | ⚠️ EMPTY SLATE | 🚀 Ready for Deployment

---

## 📊 CURRENT STATE (Clean Ubuntu)

### System Information
```bash
OS:              Ubuntu 24.04.3 LTS (Noble Numbat)
Kernel:          Linux 6.8.0-88-generic x86_64
Hostname:        host1785957413
Uptime:          ~2 minutes (FRESH INSTALL)
Disk Usage:      1.9G / 75G (3% used) ✅ 97% FREE SPACE
SSH Access:      ✅ Working with `id_rsa.priv`
```

### What's Running
- ❌ **Docker**: NOT installed
- ❌ **PostgreSQL**: NOT installed
- ❌ **Redis**: NOT installed
- ❌ **Lumine Backend**: NOT deployed
- ✅ Only default Ubuntu system services

---

## 🎯 DEPLOYMENT OBJECTIVE

Deploy the complete **Lumine Hedge Fund Platform** infrastructure from scratch, including:
1. Container orchestration (Docker & Compose)
2. Database layer (PostgreSQL + Redis)
3. Backend FastAPI services
4. AI/LLM gateway (9router)
5. Control plane (Caddy, Authelia, Homepage)
6. Monitoring & logging
7. Backup automation
8. Security hardening

---

## 📋 DEPLOYMENT STEPS

### PHASE 1: SYSTEM PREPARATION ⚙️
*(Estimated: 15 minutes)*

#### Step 1.1: Update System Packages
```bash
apt update && apt upgrade -y
```

#### Step 1.2: Install Prerequisites
```bash
apt install -y curl wget git vim net-tools ufw
```

#### Step 1.3: Configure Firewall (Security First!)
```bash
ufw allow 22/tcp    # SSH
ufw allow 80/tcp    # HTTP (for Caddy)
ufw allow 443/tcp   # HTTPS (for Caddy)
ufw default deny incoming
ufw enable
```

---

### PHASE 2: CONTAINER ORCHESTRATION 🔧
*(Estimated: 30 minutes)*

#### Step 2.1: Install Docker Engine
```bash
# Add Docker's official GPG key
curl -fsSL https://get.docker.com -o get-docker.sh
sh get-docker.sh

# Add current user to docker group
usermod -aG docker $USER
newgrp docker

# Verify installation
docker --version
docker compose version
```

#### Step 2.2: Install Docker Compose Plugin (if separate)
```bash
docker plugin install grafana/dokploy:latest  # Optional plugins
```

---

### PHASE 3: DATABASE LAYER 🗄️
*(Estimated: 15 minutes)*

#### Step 3.1: Create PostgreSQL Container
```bash
cd /opt/lumine/backend
docker compose -f docker-compose.prod.yml up -d postgresql
```

#### Step 3.2: Wait for DB to be ready
```bash
docker logs -f postgresql --tail 50
# Look for: "database system is ready to accept connections"
```

#### Step 3.3: Create Redis Container
```bash
docker run -d \
  --name redis \
  -p 6379:6379 \
  redis:7-alpine \
  --appendonly yes
```

---

### PHASE 4: BACKEND SERVICES 🦞
*(Estimated: 45 minutes)*

#### Step 4.1: Clone Repository
```bash
cd /opt
git clone https://github.com/nabhanyuzqi1/lumine-hedge-fund.git
cd lumine-hedge-fund/backend
```

#### Step 4.2: Setup Environment Variables
```bash
cp .env.example .env
nano .env

# Required variables:
DB_PASSWORD=<generate_secure_password>
HMAC_SECRET_KEY=<generate_random_bytes>
LLM_GATEWAY_API_KEY=$(uuidgen)
REDIS_HOST=redis
REDIS_PORT=6379
POSTGRES_DB=lumine
POSTGRES_USER=luminous_app
POSTGRES_HOST=postgresql
```

#### Step 4.3: Build and Deploy Containers
```bash
docker compose -f docker-compose.prod.yml build
docker compose -f docker-compose.prod.yml up -d
```

#### Step 4.4: Monitor Startup
```bash
docker compose -f docker-compose.prod.yml ps
docker logs -f backend-api --tail 100
```

---

### PHASE 5: CONTROL PLANE 🔐
*(Estimated: 30 minutes)*

#### Step 5.1: Setup Caddy Reverse Proxy
```bash
mkdir -p /srv/control-plane/caddy
cd /srv/control-plane/caddy

# Create Caddyfile
cat > Caddyfile << 'EOF'
166.88.227.177 {
    reverse_proxy localhost:8000
}
EOF

docker run -d \
  --name control-caddy \
  --network host \
  -v $(pwd)/Caddyfile:/etc/caddy/Caddyfile \
  caddy:2
```

#### Step 5.2: Setup Authelia (Authentication)
```bash
cd /srv/control-plane/authelia
docker compose up -d
```

#### Step 5.3: Setup Homepage Dashboard
```bash
cd /srv/control-plane/homepage
docker compose up -d
```

---

### PHASE 6: MONITORING & LOGGING 📊
*(Estimated: 20 minutes)*

#### Step 6.1: Deploy Uptime Kuma
```bash
cd /srv/control-plane/uptime-kuma
docker compose up -d
```

#### Step 6.2: Deploy Dozzle (Log Viewer)
```bash
docker run -d \
  --name control-dozzle \
  --network host \
  -v /var/run/docker.sock:/var/run/docker.sock \
  amir20/dozzle:latest
```

---

### PHASE 7: SECURITY HARDENING 🔒
*(Estimated: 30 minutes)*

#### Step 7.1: Secure SSH Configuration
```bash
# Edit SSH config
cat >> /etc/ssh/sshd_config << 'EOF'
PermitRootLogin prohibit-password
PasswordAuthentication no
PubkeyAuthentication yes
EOF

systemctl restart ssh
```

#### Step 7.2: Install Fail2Ban
```bash
apt install -y fail2ban
systemctl enable fail2ban
systemctl start fail2ban
```

#### Step 7.3: Configure Backups
```bash
mkdir -p /root/lumine-backups
chmod 700 /root/lumine-backups

# Create backup script
cat > /opt/lumine/scripts/backup.sh << 'EOF'
#!/bin/bash
BACKUP_DIR=/root/lumine-backups
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
docker exec postgresql pg_dump -U luminous_app lumines > "$BACKUP_DIR/db_$TIMESTAMP.sql"
tar czf "$BACKUP_DIR/backup_$TIMESTAMP.tar.gz" /opt/lumine
EOF

chmod +x /opt/lumine/scripts/backup.sh

# Schedule daily backup via cron
(crontab -l 2>/dev/null; echo "0 3 * * * /opt/lumine/scripts/backup.sh") | crontab -
```

---

### PHASE 8: VERIFICATION ✅
*(Estimated: 15 minutes)*

#### Step 8.1: Health Check Script
```bash
curl -s http://localhost:8000/api/health || echo "API endpoint check..."
docker ps -a --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
docker compose -f /opt/lumine/backend/docker-compose.prod.yml ps
```

#### Step 8.2: Database Connectivity Test
```bash
docker exec -it postgresql psql -U luminous_app -d lumins -c "SELECT version();"
```

#### Step 8.3: Redis Connection Test
```bash
docker exec redis redis-cli ping
# Should return: PONG
```

---

## 📝 POST-DEPLOYMENT CHECKLIST

After all phases completed, verify:

- [ ] ✅ All Docker containers running (`docker ps`)
- [ ] ✅ PostgreSQL accepting connections
- [ ] ✅ Redis responding to PING
- [ ] ✅ FastAPI backend healthy at `/api/health`
- [ ] ✅ Caddy proxy routing correctly
- [ ] ✅ Authelia authentication functional
- [ ] ✅ Homepage dashboard accessible
- [ ] ✅ Uptime Kuma monitoring active
- [ ] ✅ Dozzle log viewer available
- [ ] ✅ Backup script working
- [ ] ✅ Firewall rules applied
- [ ] ✅ SSH hardened
- [ ] ✅ Logs written correctly

---

## 🚨 CRITICAL WARNINGS

⚠️ **BEFORE YOU BEGIN:**
1. Make sure Git repository is fully sync'd locally
2. Have `.env.template` or `.env.example` file ready
3. Generate secure passwords/secrets locally first
4. Test backup/restore procedure on staging environment
5. Schedule maintenance window if VPS in production
6. Notify stakeholders of deployment downtime

⚠️ **NEVER:**
- Commit actual `.env` files with real secrets
- Push private keys to Git
- Expose database ports to public internet
- Disable firewall during deployment
- Skip verification steps
- Proceed without rollback plan

---

## 🆘 ROLLBACK PROCEDURES

If something goes wrong:

### Option A: Partial Rollback
```bash
# Stop problematic service
docker compose -f docker-compose.prod.yml stop <service-name>

# Restore from last known good state
git checkout HEAD~1 backend/docker-compose.prod.yml
docker compose -f backend/docker-compose.prod.yml up -d
```

### Option B: Full Wipe & Restart
```bash
# STOP ALL SERVICES
docker compose -f /opt/lumine/backend/docker-compose.prod.yml down -v

# Clean everything
rm -rf /opt/lumine
rm -rf /srv/control-plane

# Start over from Phase 1
```

### Option C: Cloud Provider Snapshot
If using cloud provider (DigitalOcean, Linode, etc.):
1. Console → Snapshots → Revert to previous snapshot
2. Or provision new VPS from image

---

## 📞 EMERGENCY CONTACTS

Keep this handy:

- **VPS Provider Support**: [Add your provider's contact]
- **DevOps Lead**: [Your contact]
- **Emergency SSH Key**: Located at `/Users/nabhan/Dev/lumine-hedge-fund/id_rsa.priv`
- **Git Repo**: https://github.com/nabhanyuzqi1/lumine-hedge-fund
- **Backup Location**: GitHub repo backups branch

---

## 🎉 SUCCESS METRICS

Deployment is successful when:
1. All 13 services running and healthy
2. API responds with 200 OK at health endpoint
3. Database queries work correctly
4. Redis pub/sub operational
5. Monitoring shows all green
6. Backup creates valid archive
7. No security vulnerabilities detected

---

**NEXT STEP**: Reply **"START DEPLOYMENT"** to begin Phase 1 automatically!

Or reply with questions about any specific phase before proceeding~ ✨ ~★~
