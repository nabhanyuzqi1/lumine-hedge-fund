# Lumine Disaster Recovery Playbook

**Version:** 1.0  
**Date:** 2026-08-13  
**Classification:** CRITICAL - OPERATIONS ONLY  
**Last Tested:** Pending First Validation  

---

## Purpose

This playbook provides step-by-step procedures for disaster recovery of the Lumine production infrastructure at VPS 166.88.227.177. It must be followed EXACTLY in any disaster scenario to ensure successful recovery with minimal data loss and downtime.

**CRITICAL WARNING:** This document should NEVER be committed to public repositories. Keep offline or in encrypted secure storage accessible only to authorized operations personnel.

---

## When to Use This Playbook

Trigger this playbook when ANY of the following events occur:

- [ ] Complete system failure (server unresponsive, all containers down)
- [ ] Data corruption detected (database errors, config mismatches)
- [ ] Security breach requiring full reset
- [ ] Hardware failure requiring server replacement
- [ ] Cloud provider outage requiring failover
- [ ] Accidental deletion of critical data/configs
- [ ] Backup file integrity verification failure

**DO NOT use this playbook for routine maintenance or upgrades.** Use standard deployment procedures instead.

---

## Pre-Disaster Preparation Checklist

Before any disaster occurs, verify these items are in place:

### ✅ Required Items

- [ ] Latest backup file exists and verified (`/root/lumine-backups/latest.tar.gz`)
- [ ] Encryption key for backup securely stored and accessible
- [ ] SSH private key available for emergency access  
- [ ] Alternative VPS provisioned (hot standby preferred)
- [ ] Recovery procedure documented here
- [ ] Team trained on recovery steps
- [ ] Contact list updated and accessible
- [ ] Rollback plan documented if recovery fails

### ⚠️ If Any Missing

**DO NOT proceed with actual disaster recovery until ALL items checked.** Schedule time to prepare before emergency arises.

---

## Recovery Time Objectives (RTO/RPO)

| Metric | Target | Current Capability | Gap |
|--------|--------|-------------------|-----|
| RPO (Recovery Point Objective) | ≤ 24 hours | ~24 hours (daily backups) | ✅ Met |
| RTO (Recovery Time Objective) | ≤ 4 hours | Unproven (not tested) | ❌ Unknown |
| Data Integrity Verification | Automated | Manual only | ❌ Needs Automation |

**Note:** These targets assume fresh VPS provisioning. If hardware salvage possible, times may improve.

---

## Scenario-Specific Procedures

### Scenario A: Complete Server Failure (Disk Corruption/OS Crash)

#### Step 1: Assess Damage (5 minutes)
```bash
# From alternate machine/admin terminal
ssh root@166.88.227.177 "hostname && uptime" 2>/dev/null || echo "Server UNRESPONSIVE"
curl -sf https://166.88.227.177/health 2>/dev/null || echo "Services DOWN"
```

If server completely unresponsive:

#### Step 2: Provision New Server (30 minutes)
```bash
# Option 1: Cloud provider auto-scaling group (preferred)
# Option 2: Manual VM creation from same image as original
# Option 3: Emergency dedicated server procurement

Required specs (minimum):
- Ubuntu 24.04 LTS
- 4 vCPU / 8 GB RAM / 160 GB SSD
- Public IP address
- Docker Engine 29.x installed
- Basic UFW firewall rules applied
```

#### Step 3: Install Base System (15 minutes)
```bash
# On new server
sudo apt update && sudo apt upgrade -y
sudo apt install docker.io docker-compose git -y
sudo curl -L "https://github.com/docker/compose/releases/download/v2.24.0/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose
sudo useradd -m lumine && sudo usermod -aG docker lumine
```

#### Step 4: Retrieve Backup Archive (5 minutes)
```bash
# Download latest backup from secure off-site location
wget https://github.com/nabhanyuzqi1/lumine-backups/raw/main/backups/20260812.tar.gz \
     --header="Authorization: Bearer $GITHUB_BACKUP_TOKEN" \
     -O /tmp/lumine-backup.tar.gz

# Verify integrity
sha256sum /tmp/lumine-backup.tar.gz > /tmp/checksum.txt
# Compare against known-good checksum (documented separately)
```

#### Step 5: Restore Configuration (10 minutes)
```bash
cd /opt
mkdir -p luminedelete /luminedeclare/optbackup
tar xzf /tmp/lumine-backup.tar.gz -C /luminedeclare/optbackup/

# Copy configs back
cp /luminedeclare/optbackup/* /opt/lumine/
chmod 600 /opt/lumine/.env
chown -R root:root /opt/lumine

# Verify restoration
ls -la /opt/lumine/backend/docker-compose.prod.yml
ls -la /opt/lumine/.env
```

#### Step 6: Deploy Services (15 minutes)
```bash
cd /opt/lumine/backend
docker compose -f docker-compose.prod.yml pull
docker compose -f docker-compose.prod.yml up -d --remove-orphans

# Wait for healthy status
until docker compose -f docker-compose.prod.yml ps --format "{{.Names}}\t{{.Status}}" | grep -q "healthy"; do
  sleep 10
done

echo "Services deployed successfully!"
```

#### Step 7: Verification (10 minutes)
```bash
# Check all services healthy
docker compose -f docker-compose.prod.yml ps

# Test API health endpoint
curl http://localhost:8000/health

# Verify database connectivity
docker exec -it backend-postgres-1 pg_isready -U lumine -d lumine

# Check Redis connectivity  
docker exec -it backend-redis-1 redis-cli ping
```

**Expected Outcome:** All 6 backend services running healthy within 45 minutes total.

---

### Scenario B: Database Corruption/Compromise

#### Step 1: Stop Affected Services (Immediate)
```bash
ssh root@166.88.227.177 << 'EOF'
  # Isolate database immediately
  docker stop api mt5 9router headroom
  
  # Check database logs for corruption evidence
  docker logs backend-postgres-1 --tail 100
  
  # Verify backup availability
  ls -lh /root/lumine-backups/*.sql.gz 2>/dev/null || echo "No SQL backup found"
EOF
```

#### Step 2: Restore Database Only (30 minutes)
```bash
# Create backup before restore (safety measure)
docker run --rm -v postgres_data:/var/lib/postgresql/data \
  postgres:16-alpine sh -c "tar czf /tmp/pg_backup_before_restore.tar.gz /var/lib/postgresql/data"

# Pull clean database image
docker pull postgres:16-alpine

# Drop corrupted container
docker rm -f backend-postgres-1

# Create new container with fresh data volume
docker run -d --name backend-postgres-1 \
  -v postgres_data:/var/lib/postgresql/data \
  -e POSTGRES_USER=lumine \
  -e POSTGRES_PASSWORD=<restore-from-environment-variable> \
  -e POSTGRES_DB=lumine \
  postgres:16-alpine

# Wait for initialization
sleep 30

# Import backup if SQL backup exists
docker exec -i backend-postgres-1 psql -U lumine -d lumine < /path/to/backup.sql
```

#### Step 3: Verify Data Integrity (10 minutes)
```bash
# Check row counts match expected values
docker exec -i backend-postgres-1 psql -U lumine -d lumine -c \
  "SELECT COUNT(*) FROM lineage_records; SELECT COUNT(*) FROM fills;"

# Compare against known-good numbers (documented elsewhere)
# Expected: lineage_records ~500, fills ~1200
```

#### Step 4: Restart Services (5 minutes)
```bash
ssh root@166.88.227.177 << 'EOF'
  docker start backend-postgres-1
  docker start api mt5 9router headroom
  
  # Monitor startup logs
  docker logs -f backend-api-1 &
EOF
```

**Expected Outcome:** Database restored to pre-corruption state within 1 hour total.

---

### Scenario C: Security Breach Requiring Full Reset

#### Step 1: Immediate Containment (5 minutes)
```bash
# Block all external traffic except emergency access
ssh root@166.88.227.177 << 'EOF'
  ufw disable
  ufw default deny incoming
  ufw allow from 10.0.0.0/8 to any port 22
  ufw enable
  systemctl restart sshd
EOF

# Stop all non-critical services
docker stop dozzle homepage control-homepage 2>/dev/null || true
```

#### Step 2: Evidence Collection (15 minutes)
```bash
# Collect forensic data BEFORE reset
ssh root@166.88.227.177 << 'EOF'
  # Save system state
  tar czf /tmp/forensic_state_$(date +%Y%m%d_%H%M%S).tar.gz \
    /var/log/auth.log \
    /var/log/syslog \
    /etc/ssh/sshd_config \
    ~/.ssh/authorized_keys \
    /opt/lumine/.env
  
  # Copy to secure off-site location
  scp /tmp/forensic_state*.tar.gz security-team@secure-server:/incident-evi
EOF
```

#### Step 3: Full Reset Procedure (2 hours)
**WARNING:** This will destroy ALL data and configurations. Backup existing configs first if possible.

```bash
# 1. Backup current configs (if still accessible)
ssh root@166.88.227.177 << 'EOF'
  cd /opt/lumine
  tar czf /tmp/preserve-configs.tar.gz backend/infrastructure/
  
  # Delete everything except essential directories
  rm -rf /opt/lumine/*
  rm -rf /srv/control-plane/*
  
  # Rebuild from scratch
  mkdir -p /opt/lumine /srv/control-plane
EOF

# 2. Fresh deployment from repository
# Download fresh configs from Git repository
git clone https://github.com/nabhanyuzqi1/lumine-hedge-fund.git /tmp/fresh-repo

# Replace all old files
cp -r /tmp/fresh-repo/scripts/deploy/* /opt/lumine/
cp -r /tmp/fresh-repo/infrastructure/control-plane/* /srv/control-plane/

# Apply security patches
sed -i 's/DB_PASSWORD=.*/DB_PASSWORD=$(openssl rand -base64 32)/g' /opt/lumine/.env
sed -i 's/HMAC_SECRET_KEY=.*/HMAC_SECRET_KEY=$(openssl rand -hex 32)/g' /opt/lumine/.env
# Repeat for all sensitive variables...
```

#### Step 4: Secure Key Rotation (30 minutes)
```bash
# Generate completely new credentials
openssl rand -base64 32 > /tmp/new-db-password.txt
openssl rand -hex 32 > /tmp/new-hmac-key.txt
uuidgen > /tmp/new-api-key.txt

# Update all configuration files
sed -i "s/^DB_PASSWORD=.*/DB_PASSWORD=$(cat /tmp/new-db-password.txt)/g" /opt/lumine/.env
sed -i "s/^HMAC_SECRET_KEY=.*/HMAC_SECRET_KEY=$(cat /tmp/new-hmac-key.txt)/g" /opt/lumine/.env
sed -i "s/^LLM_GATEWAY_API_KEY=.*/LLM_GATEWAY_API_KEY=$(cat /tmp/new-api-key.txt)/g" /opt/lumine/.env

# Regenerate SSH keys
ssh-keygen -t ed25519 -f /root/.ssh/id_ed25519_new -N "" -C "post-breach-new-key"
mv /root/.ssh/id_ed25519_new{,.bak}
mv /root/.ssh/id_ed25519_new.pub .ssh/authorized_keys.new
```

#### Step 5: Verification & Monitoring (1 hour)
```bash
# Deploy fresh system
cd /opt/lumine/backend
docker compose -f docker-compose.prod.yml up -d --build

# Health check loop
for i in {1..12}; do
  health=$(/curl -sf http://localhost:8000/health 2>/dev/null && echo "healthy" || echo "unhealthy")
  [ "$health" = "healthy" ] && break
  sleep 30
done

# Enable enhanced logging
journalctl -fu backend-api-1 > /var/log/breach-investigation.log &
logger -t "breach-reset" "System reset complete, enhanced monitoring active"
```

**Expected Outcome:** Clean system rebuilt within 3-4 hours with zero remnants of compromised data.

---

## Post-Recovery Actions

After ANY successful recovery:

1. **Document the incident:**
   ```markdown
   Incident ID: DR-[YYYYMMDD]-[NNN]
   Start time: YYYY-MM-DD HH:MM UTC
   End time: YYYY-MM-DD HH:MM UTC
   Duration: X hours Y minutes
   Root cause: [Identified during post-mortem]
   Lessons learned: [What improved]
   ```

2. **Update monitoring/alerting:** Add new alert triggers based on what caused incident

3. **Review and update playbook:** Document any gaps discovered during recovery

4. **Schedule follow-up test:** Plan next DR drill within 30 days

5. **Notify stakeholders:** Inform leadership and affected users about recovery completion

---

## Emergency Contacts

Store this information SECURELY (NOT in this public document):

| Role | Name | Phone | Slack | Email |
|------|------|-------|-------|-------|
| DevOps Lead | [REDACTED] | [REDACTED] | @devops-emergency | [REDACTED] |
| Security Officer | [REDACTED] | [REDACTED] | @security-incidents | [REDACTED] |
| External Support Provider | [Vendor] | 1-[REDACTED] | N/A | support@[vendor].com |
| Cloud Provider | AWS/GCP/Azure | 1-[REDACTED] | Account Portal | [Account ID] |

**Access Method:** These contacts MUST be available via:
- Encrypted password manager (last pass)
- Physical document in secured safe
- Printed contact sheet in operations room

---

## Testing Schedule

This playbook MUST be tested according to schedule below:

| Drill Type | Frequency | Duration | Participants | Success Criteria |
|------------|-----------|----------|--------------|------------------|
| Tabletop Exercise | Quarterly | 2 hours | Operations Team | All steps understood |
| Partial Recovery Test | Monthly | 4 hours | DevOps Engineers | Specific scenario works |
| Full Disaster Simulation | Semi-Annually | 8 hours | Entire Operations | RTO/RPO met |

**Next Scheduled Test:** 2026-11-13 (First validation required before Phase 16)

---

## Approval & Sign-Off

This disaster recovery playbook requires quarterly review and sign-off:

| Review Cycle | Date | Status | Reviewer Signature |
|-------------|------|--------|-------------------|
| Initial Creation | 2026-08-13 | Draft | _________________ |
| Q3 Review | TBD | Pending | _________________ |
| Q4 Review | TBD | Pending | _________________ |

**Authorized Personnel Only:** Only senior operations staff authorized to modify this playbook. Changes require approval from CTO or Security Director.

---

**Document Classification:** SECRET - DISASTER RECOVERY PROCEDURES  
**Distribution:** Operations Leadership, Security Team, CTO Office Only  
**Retention:** Keep for minimum 7 years for compliance purposes  
**Next Review:** 2026-09-13 or after any actual disaster event
