# Phase 16 Execution Plan — Days 2-5

**Date Range:** Aug 14-17, 2026  
**Sprint:** 16.1 — Production Infrastructure Setup  
**Owner:** DevOps Team  

---

## Executive Summary

Detailed execution plan for Sprint 16.1 infrastructure setup. Each day has specific tasks, deliverables, success criteria, and rollback procedures.

---

## DAY 2 (Aug 14, 2026) — VPS Hardening Complete

### Morning Tasks (09:00-12:00 UTC)

#### Task 2.A: System Updates & Patching
**Owner:** Platform Engineer  
**Duration:** 2 hours

**Steps:**
```bash
# Check for pending updates
sudo apt update && sudo apt list --upgradable

# Apply security patches
sudo apt upgrade -y

# Install security packages
sudo apt install fail2ban ufw auditd rkhunter -y

# Configure automatic security updates
sudo apt install unattended-upgrades -y
sudo dpkg-reconfigure -plow unattended-upgrades
```

**Verification:**
```bash
apt list --upgradable | grep "^stable" | wc -l  # Should be 0
dpkg -l | grep -E "fail2ban|ufw|auditd|rkhunter"
```

---

#### Task 2.B: Firewall Configuration
**Owner:** Security Engineer  
**Duration:** 2 hours

**Steps:**
```bash
# Disable all existing rules
sudo ufw disable

# Set default policies
sudo ufw default deny incoming
sudo ufw default allow outgoing

# Allow essential ports only
sudo ufw allow from any to any port 22 proto tcp comment 'SSH'
sudo ufw allow from any to any port 80 proto tcp comment 'HTTP'
sudo ufw allow from any to any port 443 proto tcp comment 'HTTPS'
sudo ufw allow from any to any port 20128 proto tcp comment '9router Gateway'

# Enable SSH rate limiting
sudo ufw limit ssh/tcp

# Log denied connections
echo 'set loglevel medium' >> /etc/ufw/ufw.conf

# Enable firewall
sudo ufw enable

# Verify configuration
sudo ufw status verbose
```

**Verification:**
```bash
nmap -sT 166.88.227.177  # Only ports 22, 80, 443, 20128 visible
```

---

#### Task 2.C: SSH Security Hardening
**Owner:** Security Engineer  
**Duration:** 1 hour

**WARNING:** Test from separate terminal before closing original session!

**Steps:**
```bash
# Backup current SSH config
sudo cp /etc/ssh/sshd_config /etc/ssh/sshd_config.backup-$(date +%Y%m%d)

# Edit SSH configuration
sudo tee /etc/ssh/sshd_config.d/lumine-hardening.conf << 'EOF'
PasswordAuthentication no
ChallengeResponseAuthentication no
PubkeyAcceptedKeyTypes ssh-ed25519,rsa-sha2-nistp256
MaxAuthTries 3
MaxSessions 2
ClientAliveInterval 300
ClientAliveCountMax 2
PermitRootLogin no
EOF

# Restart SSH service
sudo systemctl restart sshd

# Verify
sudo sshd -t
```

---

#### Task 2.D: Audit Logging Configuration
**Owner:** Platform Engineer  
**Duration:** 1.5 hours

```bash
# Configure audit rules
sudo tee /etc/audisp/plugins.d/syslog.conf > /dev/null << 'EOF'
enabled = yes
format = ascii
path = /var/log/audit.log
group = root
EOF

# Add custom audit rules
sudo tee /etc/audit/rules.d/security.rules << 'EOF'
-w /etc/passwd -p ra -k identity
-w /etc/shadow -p ra -k identity
-w /etc/group -p ra -k identity
-w /etc/sudoers -p wa -k privilege_change
-w /etc/ssh/sshd_config -p wa -k ssh_config
-a always,exit -F arch=b64 -S open -S openat -F exit=-EACCES -k file_access_denied
EOF

# Start audit daemon
sudo systemctl start auditd
sudo systemctl enable auditd

# Verify
sudo auditctl -l | head -20
```

---

#### Task 2.E: Baseline Documentation
**Owner:** Platform Engineer  
**Duration:** 0.5 hour

```bash
cd /opt/lumine
cat > baseline-state-$(date +%Y%m%d).md << EOF
# Server Baseline State - $(date '+%Y-%m-%d %H:%M:%S')

## System Information
\`\`\`bash
hostname
uname -r
cat /etc/os-release
df -h /
free -h
\`\`\`

## Security Configuration
\`\`\`bash
sudo ufw status verbose
sudo systemctl status fail2ban
sudo systemctl status auditd
ls -la /etc/audit/
\`\`\`

## Service Status
\`\`\`bash
docker ps --format "{{.Names}}\t{{.Status}}"
systemctl status docker
\`\`\`

## Disk Usage by Directory
\`\`\`bash
du -sh /* | sort -hr | head -10
\`\`\`
EOF
```

---

### Afternoon Tasks (13:00-17:00 UTC)

#### Task 2.F: Daily Validation
**Owner:** All Team Members  
**Duration:** 1 hour

Verify all morning tasks completed successfully and document findings in daily report.

---

## DAY 3 (Aug 15, 2026) — Service Deployment Verification

### Full Day Tasks

#### Task 3.A: Docker Health Checks
**Owner:** DevOps Lead  
**Duration:** 2 hours

**Verify All Containers:**
```bash
cd /opt/lumine/backend
docker compose -f docker-compose.prod.yml ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

# Check each container individually
for container in backend-api backend-postgres backend-redis; do
    echo "=== ${container} ==="
    docker logs --tail 50 ${container} | grep -i error || echo "No errors found"
done

cd /srv/control-plane
docker compose ps --format "table {{.Names}}\t{{.Status}}"
```

**Success Criteria:**
- [ ] All 13 containers UP and HEALTHY
- [ ] Zero error messages in logs
- [ ] Port mappings correct
- [ ] Resource usage acceptable

---

#### Task 3.B: API Endpoint Testing
**Owner:** DevOps Lead  
**Duration:** 1.5 hours

**Test All Critical Endpoints:**
```bash
# API health check
curl -sf http://localhost:8000/health && echo "✓ API Health OK"

# Database connectivity
docker exec backend-postgres-1 pg_isready -U lumine -d lumine && echo "✓ DB Connected"

# Redis connectivity
docker exec backend-redis-1 redis-cli ping && echo "✓ Redis Responding"

# MT5 noVNC accessibility
curl -sf http://localhost:6901/vnc.html | head -5 && echo "✓ MT5 Accessible"

# 9router gateway status
curl -sf http://localhost:20128/dashboard && echo "✓ 9router Running"
```

---

#### Task 3.C: Load Testing
**Owner:** DevOps Lead  
**Duration:** 1 hour

```bash
# Test API throughput
ab -n 1000 -c 10 http://localhost:8000/health

# Check response times
time curl -s http://localhost:8000/health

# Monitor resource usage during load
watch -n 1 'docker stats --no-stream | head -20'
```

---

#### Task 3.D: Backup Restoration Test
**Owner:** DevOps Lead  
**Duration:** 2 hours

**Execute Full Restore Simulation:**
```bash
# Create isolated restore directory
mkdir -p ~/dr-test-live/{config,data,logs}

# Download backup (already done, verify integrity)
cd ~/lumine-staging
sha256sum 20260812.tar.gz.enc > checksum.sha256
sha256sum -c checksum.sha256 && echo "✅ Checksum verified"

# Prepare decryption (requires secure key access)
openssl enc -aes-256-cbc -d -salt \
  -in 20260812.tar.gz.enc \
  -pass pass:OPERATIONAL_KEY_PLACEHOLDER \
  -o ~/dr-test-live/original.tar.gz

# Extract to staging
cd ~/dr-test-live
tar xzf original.tar.gz

# Validate restored structure
ls -R opt/lumine srv/control-plane | wc -l
echo "Expected files extracted: $(find opt srv -type f | wc -l)"
```

**Document Recovery Time:** Start stopwatch when decrypt command begins, stop when extraction completes.

---

#### Task 3.E: Monitoring Validation
**Owner:** DevOps Lead  
**Duration:** 1.5 hours

```bash
# Check uptime-kuma status
curl -sf https://166.88.227.177:8080/dashboard && echo "✓ Uptime Kuma Active"

# Check homepage dashboard
curl -sf https://166.88.227.177/auth/login && echo "✓ Homepage Auth Working"

# Check Dozzle logs access
curl -sf https://166.88.227.177/logs/realtime && echo "✓ Dozzle Active"

# Verify Caddy reverse proxy
curl -vI https://166.88.227.177/ | grep "HTTP/2" && echo "✓ Caddy HTTPS Working"
```

---

## DAY 4 (Aug 16, 2026) — Monitoring Setup Enhancement

### Full Day Tasks

#### Task 4.A: Prometheus Installation
**Owner:** Platform Engineer  
**Duration:** 2 hours

```bash
# Download and install Prometheus
wget https://github.com/prometheus/prometheus/releases/download/v2.47.0/prometheus-2.47.0.linux-amd64.tar.gz
tar xzf prometheus-*.tar.gz
sudo mv prometheus*/prometheus /usr/local/bin/
sudo mv prometheus*/promtool /usr/local/bin/
rm -rf prometheus*

# Create Prometheus config
sudo tee /etc/prometheus/prometheus.yml > /dev/null << EOF
global:
  scrape_interval: 15s
  evaluation_interval: 15s

scrape_configs:
  - job_name: 'lumine-api'
    static_configs:
      - targets: ['localhost:8000']
    
  - job_name: 'docker'
    static_configs:
      - targets: ['localhost:9323']
EOF

# Run as service
sudo tee /etc/systemd/system/prometheus.service > /dev/null << 'EOF'
[Unit]
Description=Prometheus Monitoring
After=network.target

[Service]
User=root
ExecStart=/usr/local/bin/prometheus --config.file=/etc/prometheus/prometheus.yml
Restart=always

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable prometheus
sudo systemctl start prometheus
```

**Verification:**
```bash
curl http://localhost:9090/api/v1/targets | jq '.data.activeTargets[] | select(.health != "up")'
```

---

#### Task 4.B: Grafana Dashboard Creation
**Owner:** Platform Engineer  
**Duration:** 2 hours

```bash
# Install Grafana
wget -q -O - https://packages.cloud.google.com/apt/doc/apt-key.gpg | sudo apt-key add -
echo "deb https://apt.grafana.com stable main" | sudo tee /etc/apt/sources.list.d/grafana.list
sudo apt update && sudo apt install grafana -y

# Start Grafana service
sudo systemctl enable grafana-server
sudo systemctl start grafana-server
```

**Dashboard JSON Templates:**
- Service Health Overview
- Resource Utilization (CPU/Memory/Disk)
- Network Traffic Analysis
- Error Rate Tracking

**Verification:**
```bash
curl -sf http://localhost:3000/login
# Should show Grafana login page
```

---

#### Task 4.C: Alert Rules Configuration
**Owner:** DevOps Lead  
**Duration:** 1.5 hours

```bash
# Create alerting rules file
sudo tee /etc/prometheus/rules/alerting.yml > /dev/null << EOF
groups:
  - name: lumine-alerts
    rules:
      - alert: APIDown
        expr: up{job="lumine-api"} == 0
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "API service down"
          description: "Lumine API endpoint has been unreachable for >5 minutes"
          
      - alert: HighDiskUsage
        expr: node_filesystem_avail{mountpoint="/"} < 10*1024*1024*1024
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: "Disk usage above 90%"
          
      - alert: HighMemoryUsage
        expr: (node_memory_MemTotal_bytes - node_memory_MemAvailable_bytes) 
              / node_memory_MemTotal_bytes * 100 > 85
        for: 15m
        labels:
          severity: warning
        annotations:
          summary: "Memory usage high"
EOF

# Reference rules in Prometheus config
sudo sed -i '/^rule_files:/a\\n  - /etc/prometheus/rules/*.yml' /etc/prometheus/prometheus.yml

# Reload Prometheus configuration
curl -X POST http://localhost:9090/-/reload
```

---

#### Task 4.D: Alert Channel Integration
**Owner:** DevOps Lead  
**Duration:** 1.5 hours

**Slack Webhook Setup:**
1. In Slack workspace: Apps → Add New App → Incoming Webhooks
2. Generate webhook URL
3. Configure Alertmanager or Prometheus integration

**Test alert firing:**
```bash
curl -X POST http://localhost:9090/api/v1/query -d 'alert={job="test"}'
```

---

## DAY 5 (Aug 17, 2026) — SSL Security Finalization

### Morning Tasks (09:00-12:00 UTC)

#### Task 5.A: Certificate Verification
**Owner:** Security Engineer  
**Duration:** 1 hour

```bash
# Check certificate expiration
caddy cert info --domain 166.88.227.177

# Verify chain of trust
openssl s_client -connect 166.88.227.177:443 -showcerts </dev/null 2>/dev/null | openssl x509 -noout -dates

# Test auto-renewal mechanism
caddy tokens renew --dry-run

# Document expiration dates for all certs
echo "Certificate Expiration Dates:"
caddy cert info --domain 166.88.227.177 | grep -E "(Not Before|Not After)"
```

---

#### Task 5.B: Security Headers Implementation
**Owner:** Security Engineer  
**Duration:** 1.5 hours

```bash
# Update Caddyfile with security headers
sudo tee /srv/control-plane/caddy/Caddyfile.partial.headers.conf > /dev/null << 'EOF'
headers {
  Strict-Transport-Security "max-age=31536000; includeSubDomains; preload"
  X-Frame-Options "DENY"
  X-Content-Type-Options "nosniff"
  X-XSS-Protection "1; mode=block"
  Referrer-Policy "strict-origin-when-cross-origin"
  Permissions-Policy "geolocation=(), microphone=(), camera=()"
  Content-Security-Policy "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'"
  Cache-Control "public, max-age=86400"
}

# Apply reload
sudo caddy reload
EOF
```

**Verification:**
```bash
curl -I https://166.88.227.177/
# Verify all security headers present
```

---

#### Task 5.C: Vulnerability Scanning
**Owner:** Security Engineer  
**Duration:** 1.5 hours

```bash
# Trivy scan of Docker images
trivy image --severity HIGH,CRITICAL decolua/9router:latest > trivy-9router-results.sarif
trivy image --severity HIGH,CRITICAL ghcr.io/chopratejas/headroom:latest > trivy-headroom-results.sarif

# Gitleaks on code repository
gitleaks detect --report-format sarif --output-path gitleaks-results.sarif . --verbose

# Bandit on Python codebase
bandit -r backend/src/ -ll -f sarif -o bandit-results.sarif

# Compile results into single report
echo "# Security Scan Results Summary" > docs/reports/security-scan-summary.md
grep -r "CRITICAL" *.sarif 2>/dev/null | wc -l >> docs/reports/security-scan-summary.md
```

---

### Afternoon Tasks (13:00-17:00 UTC)

#### Task 5.D: Final Validation & Sign-off
**Owner:** DevOps Lead  
**Duration:** 2 hours

**Complete Checklist Review:**
```bash
cat << CHECKLIST | awk -F'\t' '{print $1 "\t" ($2 ? "PASS" : "FAIL")}'
All 13 services UP		$(docker ps -a --format '{{.Status}}' | grep -c 'Up') >= 13
Monitoring coverage ≥95%	$(curl -sf http://localhost:9090/api/v1/targets | jq '[.data.activeTargets[] | .health] | map(select(.=="up")) | length') >= 10
SSL certificates valid		$(caddy cert info --domain 166.88.227.177 | grep -c "Active") > 0
Firewall rules minimal		$(ufw status | grep -c "^22 ") = 1 (SSH)
Backup encryption working	ls ~/lumine-staging/*.enc >/dev/null 2>&1 && echo PASS || echo FAIL
Security headers present	curl -I https://166.88.227.177/ | grep -c "Strict-Transport-Security" > 0
Critical vulns resolved		grep -c "CRITICAL" *.sarif 2>/dev/null | grep -q "^0$" && echo PASS || echo FAIL
CHECKLIST
```

**Generate Final Report:**
```bash
cat > docs/16-implementation/sprint-evidence/sprint-16-1-milestone-1-complete.md << 'EOF'
# Sprint 16.1 Milestone 1 — Complete

**Completion Date:** 2026-08-17  
**Validation Status:** PASSED / NEEDS WORK  

## Infrastructure Hardening ✅ COMPLETE

All servers configured and hardened according to security requirements.

## Services Deployed ✅ COMPLETE

All 13 services operational and healthy.

## Monitoring Implemented ✅ COMPLETE

Prometheus + Grafana dashboards active and collecting metrics.

## Security Validated ✅ COMPLETE

SSL certificates, security headers, and vulnerability scans completed.

## Backup Verified ✅ COMPLETE

Encrypted backups tested and recoverable.

## Next Milestone

Proceed to Sprint 16.2 — CI/CD Automation

---
Signed Off By: _________________   Date: ___________
DevOps Lead

_____________   Date: ___________
Security Officer
EOF
```

---

## Daily Success Metrics

| Metric | Target | Measurement Method |
|--------|--------|-------------------|
| VPS uptime | ≥ 99.9% | Monitoring dashboard |
| Response time | < 1s | ApacheBench testing |
| Security score | A+ | Vulnerability scans |
| Backup recovery | < 4 hours | DR test execution |
| Alert coverage | ≥ 95% | Prometheus target status |
| Zero critical findings | 100% pass | Security scan reports |

---

## Escalation Path

For issues encountered during these 4 days:

1. **Technical Issue (Day):** Team lead troubleshooting
2. **Blocker (>4 hours):** Escalate to DevOps Lead
3. **Critical Failure:** Page on-call engineer immediately
4. **Security Incident:** Notify Security Officer within 15 minutes

---

## Rollback Procedures

### If Service Failures Occur:
```bash
docker compose -f docker-compose.prod.yml logs --tail 100 <service-name>
docker restart <service-name>
# If continues failing:
docker rm -f <service-name>
docker compose -f docker-compose.prod.yml up -d <service-name>
```

### If VPS Becomes Unreachable:
1. Contact hosting provider support
2. Request console access for emergency recovery
3. Execute recovery procedure from playbook

---

## End-of-Day Reporting

**Each evening at 17:00 UTC:**
1. Update task checklist with completed items
2. Document any blockers or issues
3. Post daily summary to Slack channel #phase-16-daily-sync
4. Update progress tracking in shared doc

**Daily Summary Template:**
```markdown
## Day X Summary - August 14, 2026

### ✅ Completed
- [Item 1]
- [Item 2]

### ⏳ In Progress
- [Item 1] (estimated completion: YYYY-MM-DD HH:MM)

### ❌ Blocked
- [Blocker] → [Escalation action taken/took]

### 📊 Metrics
- Services healthy: X/13
- Critical issues: 0
- Recovery time achieved: N minutes

### 🔜 Next Steps
Tomorrow: [Top 3 priorities]
"""
