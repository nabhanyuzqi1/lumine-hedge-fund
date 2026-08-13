# Sprint 16.1 — Production Infrastructure Setup (Aug 16-22)

**Owner:** DevOps Lead  
**Duration:** 7 days  
**Status:** Ready to Execute  

---

## Sprint Goals

Establish production-ready infrastructure with all core services operational:

1. Deploy and configure VPS environment
2. Implement monitoring and alerting system
3. Set up SSL certificates and security headers
4. Validate backup restore capability
5. Document initial state for future reference

---

## Detailed Task Breakdown

### Task 16.1.A: VPS Configuration & Hardening (Day 1)
**Owner:** Platform Engineer + Security Engineer  
**Duration:** 8 hours  

**Steps:**
1. SSH into VPS and verify current state
   ```bash
   ssh root@166.88.227.177 "hostname && docker --version && df -h /"
   ```
2. Install/verify required packages
   ```bash
   # Check Docker Engine version
   docker --version
   
   # Verify Compose version
   docker compose version
   
   # Check UFW status
   ufw status verbose
   ```
3. Apply security hardening:
   - Update OS packages: `apt update && apt upgrade -y`
   - Configure firewall: Allow only essential ports (22, 80, 443, 20128)
   - Set up fail2ban for SSH protection
   - Configure automatic security updates

**Deliverable:** Hardened VPS ready for service deployment

**Verification Commands:**
```bash
ufw status verbose | grep active
docker ps -a | wc -l  # Should show 0 containers initially
journalctl -u docker --since "1 hour ago" | tail -20
```

---

### Task 16.1.B: Service Deployment (Days 2-3)
**Owner:** Platform Engineer  
**Duration:** 16 hours  

**Step 1: Backend Services**
```bash
cd /opt/lumine/backend
docker compose -f docker-compose.prod.yml pull
docker compose -f docker-compose.prod.yml up -d postgres redis api headroom 9router
```

**Expected Containers:**
- backend-postgres-1 ✓
- backend-redis-1 ✓
- backend-api-1 ✓
- headroom ✓
- 9router ✓

**Step 2: Control Plane Services**
```bash
cd /srv/control-plane
docker compose pull
docker compose up -d caddy authelia homepage uptime-kuma dozzle landing
```

**Expected Containers:**
- control-caddy ✓
- control-authelia ✓
- control-homepage ✓
- control-uptime-kuma ✓
- control-dozzle ✓
- control-landing ✓

**Step 3: MT5 Container**
```bash
docker pull backend-mt5:latest
docker run -d --name lumine-mt5 -v mt5_data:/root/.wine-mt5 ... [full command from prod compose]
```

**Step 4: Health Verification**
```bash
# Check all containers running
docker ps --format "{{.Names}}	{{.Status}}" | grep -c "Up"

# API health check
curl http://localhost:8000/health

# Database connectivity test
docker exec backend-postgres-1 pg_isready -U lumine -d lumine

# Redis connectivity
docker exec backend-redis-1 redis-cli ping
```

**Deliverable:** All 13 services deployed and healthy

---

### Task 16.1.C: Monitoring & Alerting (Day 4)
**Owner:** DevOps Lead  
**Duration:** 8 hours  

**Step 1: Prometheus Installation**
```bash
# Download and install Prometheus
wget https://github.com/prometheus/prometheus/releases/download/v2.47.0/prometheus-2.47.0.linux-amd64.tar.gz
tar xzf prometheus-*.tar.gz
cp prometheus*/prometheus /usr/local/bin/
cp prometheus*/promtool /usr/local/bin/
```

**Step 2: Node Exporter (for each server)**
```bash
# Run as daemon
nohup /usr/local/bin/node_exporter --collector.procstat > /var/log/node-exporter.log 2>&1 &
```

**Step 3: Grafana Dashboard Creation**
- Service Health Overview
- Resource Utilization (CPU/Memory/Disk)
- Network Traffic Analysis
- Error Rate Tracking
- Custom dashboards for business metrics

**Step 4: Alert Rules Configuration**
```yaml
groups:
  - name: critical-alerts
    rules:
      - alert: ServiceDown
        expr: up{job="lumine-api"} == 0
        for: 5m
        annotations:
          summary: "API service is down"
          
      - alert: HighDiskUsage
        expr: node_filesystem_avail{mountpoint="/"} < 10*1024*1024*1024
        for: 10m
        annotations:
          summary: "Disk usage above 90%"
```

**Step 5: Alert Channels Setup**
- Slack webhook integration
- PagerDuty escalation policy
- Email notifications for critical incidents

**Deliverable:** Complete monitoring with active alerts

**Verification:**
```bash
# Check Prometheus targets
curl http://localhost:9090/api/v1/targets | jq '.data.activeTargets[] | select(.health != "up")'

# Check Grafana accessibility
curl -sf http://localhost:3000/login

# Test alert firing
kubectl apply -f /tmp/test-alerts.yaml && sleep 60
```

---

### Task 16.1.D: SSL & Security (Day 5)
**Owner:** Security Engineer  
**Duration:** 8 hours  

**Certificate Management:**
1. Verify Caddy auto-renewal configuration
2. Test certificate expiration dates:
   ```bash
   caddy cert info --domain 166.88.227.177
   openssl x509 -in /etc/caddy/certificates/*.pem -text -noout | grep "Not After"
   ```
3. Configure HSTS headers in Caddyfile
4. Set up Let's Encrypt staging environment for testing

**Security Headers:**
- Strict-Transport-Security (max-age=31536000; includeSubDomains)
- X-Content-Type-Options: nosniff
- X-Frame-Options: SAMEORIGIN
- Content-Security-Policy directives

**Vulnerability Scanning:**
```bash
# Run Trivy on images
trivy image decolua/9router:latest --severity HIGH,CRITICAL

# Run gitleaks on repository
gitleaks detect --report-format sarif --output-path trivy-results.sarif .

# Run bandit on Python code
bandit -r backend/src/ -ll
```

**Deliverable:** Valid SSL certificates and hardened configuration

---

### Task 16.1.E: Backup Verification (Day 6)
**Owner:** DevOps Lead  
**Duration:** 4 hours  

**Restore Testing Procedure:**
1. Create isolated test directory:
   ```bash
   mkdir -p ~/dr-test-staging-{day6,data}
   ```

2. Download encrypted backup (already done at ~/lumine-staging/)

3. Decrypt and extract to staging:
   ```bash
   openssl enc -aes-256-cbc -d -salt      -in ~/lumine-staging/20260812.tar.gz.enc      -pass file:/backup-key.txt      -o ~/dr-test-staging-day6/lumines_restore.tar.gz
   
   cd ~/dr-test-staging-day6
   tar xzf lumines_restore.tar.gz
   ls -R opt/lumine srv/control-plane
   ```

4. Verify file integrity and completeness:
   - Count files in restored directories
   - Compare against expected structure from documentation
   - Validate key configuration files exist and are valid YAML

5. Document restoration time:
   ```bash
   START=$(date +%s)
   # [restore procedure]
   END=$(date +%s)
   echo "Restoration Time: $((END - START)) seconds"
   ```

**Deliverable:** Proven backup restore capability

---

## Success Criteria Checklist

| Criterion | Target | Status | Verified By |
|-----------|--------|--------|-------------|
| All 13 services running | ≥ 12/13 green | ☐ Pending | DevOps Lead |
| Monitoring coverage | ≥ 95% paths | ☐ Pending | DevOps Lead |
| SSL certificates valid | Auto-renewal OK | ☐ Pending | Security Officer |
| Backup restore verified | Data intact | ☐ Pending | Operations Lead |
| Security scans pass | Zero CRITICAL | ☐ Pending | Security Officer |
| Alert channels active | Test successful | ☐ Pending | DevOps Lead |

---

## Risks & Mitigation

| Risk | Impact | Mitigation | Owner |
|------|--------|------------|-------|
| Service startup failure | High | Staging validation first | Platform Eng |
| Certificate renewal issues | Medium | Manual intervention procedure | Security Eng |
| Backup corruption | Critical | Multiple restore points | DevOps Lead |
| Memory pressure | High | Resource quotas configured | Platform Eng |

---

## Communication Plan

- **Daily Standup:** 09:00 UTC via Slack #phase-16-s16-1
- **Blocker Escalation:** Immediate → Team Lead → DevOps Lead (within 2h)
- **Daily Summary:** Posted to Slack at 17:00 UTC
- **End-of-Sprint Review:** Scheduled for Aug 22 @ 14:00 UTC

---

## Handover Preparation

Begin documenting:
1. Initial deployment commands
2. Baseline performance metrics
3. Known issues and workarounds
4. Maintenance procedures

**Deliverable:** Handover document ready by end of Day 7

---

## Sign-off Required Upon Completion

- [ ] DevOps Lead: Confirms infrastructure ready
- [ ] Security Officer: Validates security posture
- [ ] Platform Engineer: Confirms all services stable
- [ ] Product Owner: Approves readiness for next sprint

**Completion Date:** _________________

