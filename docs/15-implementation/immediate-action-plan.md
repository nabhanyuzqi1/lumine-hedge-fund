# Phase 15 Completion - Immediate Action Plan

**Date:** 2026-08-13  
**Owner:** DevOps Team + Engineering Lead  
**Deadline:** All critical items by 2026-08-20 (7 days)  

---

## Critical Blockers to Clear Before Phase 16

### BLOCKER-001: Complete Sprint 7 TCA Integration 🔴 URGENT

**Current Status:** TCA calculation EXISTS but not integrated into production pipeline

#### Tasks Breakdown:

**Task 1.1: Integrate TCA into Execution Router (4h)**
```python
# File: backend/src/lumine/trade_core/execution_router.py
# Add after fill persistence, before commit:
await persist_tca(
    session=session,
    fill=fill,
    decision_ts=tca_context.decision_ts or command.timestamp,
    regime_id=tca_context.regime_id,
    broker_id=tca_context.broker_id,
    account_id=tca_context.account_id,
    pip_value=tca_context.pip_value,
    pip_size=tca_context.pip_size,
    calendar=tca_context.calendar,
)
```

**Task 1.2: Ensure Fill Creation with TCA Context (2h)**
```python
# In orchestrator dispatch, ensure context populated:
if ctx.broker_id and ctx.account_id and ctx.pip_value:
    tca_context = TcaDispatchContext(...)
else:
    # Fail fast if missing required context
    raise ValueError("TCA context incomplete")
```

**Task 1.3: Create End-to-End Integration Tests (3h)**
- Test filled order creates both Fill AND TcaRecord
- Verify slippage calculation accuracy
- Validate benchmark selection logic

**Deliverable:** 
- `backend/tests/integration/test_tca_integration.py`
- Manual verification: Check database has both fills and tca_records joined correctly

**Acceptance Criteria:**
✅ Integration test passes  
✅ Database query shows Fill + TcaRecord relationship  
✅ Manual test execution produces correct slippage metrics

---

### BLOCKER-002: Encrypt All Existing Backups 🔴 URGENT

**Current State:** `/root/lumine-backups/` contains plaintext secrets

#### Tasks Breakdown:

**Task 2.1: Generate Encryption Key Securely (1h)**
```bash
# On SECURE machine (NOT VPS)
openssl rand -base64 32 > backup-encryption.key
chmod 600 backup-encryption.key
# Store key in password manager or hardware token
```

**Task 2.2: Encrypt Backup Archive (2h)**
```bash
ssh root@166.88.227.177 << 'EOF'
cd /root/lumine-backups
for file in *.tar.gz; do
    sops --encrypt --age age://... "$file" > "${file}.sops"
    sops --decrypt "${file}.sops" > /dev/null && echo "✓ $file encrypted successfully"
done
# Verify all files encrypted
ls -lh *.sops
EOF
```

**Task 2.3: Update CI Workflow for Encrypted Backups (1h)**
- Modify `.github/workflows/backup-to-github.yml` to use SOPS encryption
- Add decryption step for restore operations

**Task 2.4: Document Recovery Procedure (1h)**
```markdown
# Backup Recovery Steps with Encryption
1. Download .sops file from GitHub backup repo
2. Decrypt using stored key: `sops --decrypt file.sops > file.tar.gz`
3. Extract and verify contents
4. Restore to staging environment first
5. Validate data integrity
6. Only then restore to production
```

**Deliverable:**
- All backups now in `.sops` format
- Key stored securely (password manager/hardware token)
- Recovery procedure documented and tested

**Acceptance Criteria:**
✅ No plaintext secrets in any backup archive  
✅ Successful decrypt → extract → restore cycle verified  
✅ Documentation complete and accessible to ops team

---

### BLOCKER-003: Execute First DR Test 🔴 URGENT

**Current State:** Playbook exists but never tested

#### Tasks Breakdown:

**Preparation (Day 1):**
```bash
# Create isolated test environment
mkdir -p /tmp/dr-test-{staging,data}
cp /opt/lumine/docker-compose.prod.yml /tmp/dr-test-staging/
scp root@166.88.227.177:/root/lumine-backups/*.sops /tmp/dr-test-data/
```

**Execution (Day 2):**
```bash
# STEP 1: Deploy fresh VPS instance (or use cloud VM)
# STEP 2: Download encrypted backup
wget https://github.com/nabhanyuzqi1/lumine-hedge-fund-backup/raw/main/backups/<latest>.sops

# STEP 3: Decrypt and restore
sops --decrypt --age age://... lumines*.sops > restore.tar.gz
tar xzf restore.tar.gz -C /opt/lumine/

# STEP 4: Start services
cd /opt/lumine/backend
docker compose -f docker-compose.prod.yml up -d

# STEP 5: Verify health
curl http://localhost:8000/health
docker logs -f backend-api-1
```

**Validation Checklist (Day 3):**
```markdown
- [ ] API responds correctly
- [ ] Database connected and accessible
- [ ] Redis operational
- [ ] MT5 container started (if applicable)
- [ ] 9router accessible
- [ ] Headroom service responding
- [ ] Dozzle showing logs
- [ ] Authentication working
- [ ] All health checks passing

Time taken: _______ minutes (Target: < 4 hours)
Data integrity: ________% verified (Query DB row counts vs expected)
```

**Documentation Deliverable:**
- Time-stamped test results with screenshots
- Any issues encountered and resolutions applied
- Updated playbook based on lessons learned

**Acceptance Criteria:**
✅ Full restoration completed within 4-hour RTO target
✅ All services healthy after restore
✅ Data integrity ≥ 99% verified
✅ Team members trained on procedure

---

### BLOCKER-004: Security Remediation (SOC 2 Compliance) 🟠 HIGH PRIORITY

**Critical Findings to Fix Within 48 Hours:**

#### Finding SEC-001: SSH Key Rotation (Due: 48h)

```bash
# Generate new ED25519 key pair
ssh-keygen -t ed25519 -f ~/.ssh/lumine_prod_new -C "rotation-2026-08-15" -N ""

# Replace old keys on VPS
ssh root@166.88.227.177 << 'EOF'
rm /root/.ssh/id_rsa  # Old RSA key
mv id_ed25519_new.pub authorized_keys.new
cat authorized_keys.new > authorized_keys
systemctl restart sshd
EOF

# Rotate on all systems
ssh-copy-id -i id_ed25519_new.pub root@166.88.227.177
```

**Deliverable:**
- New keys deployed across all infrastructure
- Old keys revoked
- Rotation schedule documented (quarterly minimum)
- Automated alerting for key age > 90 days

#### Finding SEC-004: Logging Aggregation (Due: 72h)

```bash
# Deploy Loki stack for centralized logging
kubectl apply -f https://raw.githubusercontent.com/grafana/loki/main/operations/k8s/loki-simple-scalable.yaml

# Configure Promtail on all containers
cat << EOF > promtail-config.yaml
server:
  http_listen_port: 9080
  grpc_listen_port: 0

positions:
  filename: /tmp/positions.yaml

clients:
  - url: http://loki:3100/loki/api/v1/push

scrape_configs:
  - job_name: system
    static_configs:
      - targets: ['localhost']
        labels:
          job: varlogs
          __path__: /var/log/*log
EOF

docker run -d \
  -v /var/log:/var/log:ro \
  -v $(pwd)/promtail-config.yaml:/etc/promtail/config.yml \
  grafana/promtail:latest
```

**Deliverable:**
- Loki instance running and collecting logs
- Grafana dashboards configured for security monitoring
- Alert rules for critical events configured
- Log retention policy documented (30 days operational, 365 security)

#### Finding SEC-005: Backup Encryption Already Done Above ✅ IN PROGRESS

**Status:** Covered under BLOCKER-002

#### Finding SEC-006: Access Control Matrix (Due: 5 days)

```markdown
| System | User | Role | Permissions | Justification | Expiry |
|--------|------|------|-------------|---------------|--------|
| VPS SSH | devops-lead | full-access | Read/write admin | Primary operator | Never expires (rotated quarterly) |
| VPS SSH | security-officer | read-only | Audit log review | Compliance reviews | 90 days |
| Docker | api-service-user | service-account | Container lifecycle | Internal service | N/A |
| PostgreSQL | luminous-app | app-user | CRUD business data | Application needs | Never expires |
```

**Deliverable:** Complete access matrix documenting who can access what and why

---

## Task Tracking Dashboard

Use this dashboard to track progress against deadlines:

| Task ID | Description | Owner | Due Date | Status | Blocker? |
|---------|-------------|-------|----------|--------|----------|
| TASK-001 | Integrate TCA to production pipeline | Backend Team | Aug 15 | ❌ Not Started | YES - Phase 15 completion blocker |
| TASK-002 | Encrypt existing backups | DevOps Lead | Aug 15 | ⏳ Pending | YES - Compliance critical |
| TASK-003 | Execute DR test drill | Operations Lead | Aug 16 | ❌ Not Started | YES - Cannot prove recovery capability |
| TASK-004 | SSH key rotation | Security Officer | Aug 15 | ⏳ Pending | NO - High priority compliance |
| TASK-005 | Deploy logging aggregation | DevOps Engineer | Aug 16 | ❌ Not Started | NO - Medium priority |
| TASK-006 | Create access control matrix | Security Officer | Aug 18 | ❌ Not Started | NO - Documentation improvement |
| TASK-007 | Update Phase 15 docs to match reality | Tech Writer | Aug 17 | ⏳ Pending | NO - Accuracy fix |
| TASK-008 | Document feature justifications | Product Owner | Aug 19 | ❌ Not Started | NO - Governance requirement |

**Daily Standup Requirement:**
- Review status of all TASK-* items
- Unblock blockers immediately
- Report risks to leadership

---

## Verification Steps (Before Phase 16 Kickoff)

Run these commands to verify completion:

```bash
#!/bin/bash
# verify-phase-15-completion.sh

echo "=== PHASE 15 COMPLETION VERIFICATION ==="

# 1. Check TCA integration exists
if grep -q "persist_tca" backend/src/lumine/trade_core/execution_router.py; then
  echo "✅ TCA integration present"
else
  echo "❌ TCA integration MISSING - BLOCKED"
  exit 1
fi

# 2. Verify backup encryption
if ls /root/lumine-backups/*.sops >/dev/null 2>&1; then
  echo "✅ Backups encrypted"
else
  echo "❌ Plaintext backups found - NON-COMPLIANT"
  exit 1
fi

# 3. Test DR procedure
echo "Testing DR restore..."
# (execute recovery steps here and verify success)
if ./test-dr-procedure.sh; then
  echo "✅ DR test passed"
else
  echo "❌ DR test failed - CANNOT PROCEED TO PHASE 16"
  exit 1
fi

# 4. Check key rotation
LAST_ROTATION=$(find ~/.ssh -name "*.pub" -mtime -90 | wc -l)
if [ "$LAST_ROTATION" -gt 0 ]; then
  echo "✅ Keys rotated within 90 days"
else
  echo "⚠️  Key rotation overdue - Schedule ASAP"
fi

# 5. Validate logging
if curl -sf http://localhost:3100/api/v1/targets >/dev/null; then
  echo "✅ Logging aggregation operational"
else
  echo "⚠️  Logging not fully operational yet"
fi

# 6. Check documentation accuracy
PHASE_README_VERSION=$(grep "Last-reviewed:" docs/15-implementation/README.md | cut -d: -f2 | xargs)
CURRENT_DATE=$(date +%Y-%m-%d)
if [ "$PHASE_README_VERSION" == "$CURRENT_DATE" ]; then
  echo "✅ Documentation current"
else
  echo "⚠️  Documentation outdated - requires update"
fi

echo ""
echo "=== VERIFICATION COMPLETE ==="
echo "All checks passed! Ready for Phase 16 kickoff." || echo "ISSUES FOUND - ADDRESS BEFORE PHASE 16"

exit $?
```

---

## Escalation Path

If blockers cannot be resolved within timeframe:

1. **Within 24h:** Discuss with DevOps Lead and Engineering Manager
2. **Within 48h:** Escalate to Technical Director with detailed risk assessment
3. **Within 72h:** Present to CTO with recommendation to defer Phase 16 until critical items resolved

**Never proceed to Phase 16 while blocking items remain open.** This compromises:
- Security posture
- Compliance status
- Team ability to recover from disasters
- Stakeholder trust in delivery estimates

---

## Success Criteria for Phase 15 Sign-off

Phase 15 is considered COMPLETE when ALL of the following are met:

- [ ] Sprint 7 TCA integration functional AND tested
- [ ] Disaster recovery procedure executed and validated
- [ ] All backups encrypted with proven recovery capability
- [ ] SSH key rotation policy implemented and enforced
- [ ] Security audit findings ≥ 70% remediated
- [ ] Documentation accurately reflects current state
- [ ] Feature creep justified and approved
- [ ] All stakeholders satisfied with readiness level

**Sign-off Required From:**
1. DevOps Lead
2. Security Officer  
3. Engineering Manager
4. Product Owner

**Document:** `docs/15-implementation/phases-15-signoff-form.md` (created upon completion)

---

**This document requires daily review until all blockers cleared.**

Next review scheduled: Tomorrow at 10:00 AM UTC
