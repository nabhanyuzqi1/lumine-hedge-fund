# Phase 15 Hardening Completion Checklist

**Date:** 2026-08-13  
**Owner:** DevOps Team  
**Priority:** Critical Blocker for Phase 16  

---

## Executive Summary

Phase 15 (Sprint 7 Audit Hardening + Infrastructure Alignment) belum dapat dianggap selesai karena masih terdapat **critical gaps** antara running VPS infrastructure dan Git-tracked repository. Semua blocking items harus di-resolve sebelum Phase 16 dapat dimulai.

---

## Blocking Items Status

| ID | Item | Status | Required For Phase 16? | Owner | Target Date |
|----|------|--------|------------------------|-------|-------------|
| BLOCK-001 | All services tracked in repo | ❌ Partial | ✅ YES | DevOps Lead | 2026-08-14 |
| BLOCK-002 | Emergency access procedures | ❌ Missing | ✅ YES | Security Officer | 2026-08-14 |
| BLOCK-003 | DR test validated | ❌ Not performed | ✅ YES | Operations Lead | 2026-08-15 |
| BLOCK-004 | Secrets properly managed | ⚠️ Partial | ✅ YES | Security Engineer | 2026-08-14 |
| BLOCK-005 | Security audit completed | ❌ Not performed | ✅ YES | Internal Auditor | 2026-08-16 |
| BLOCK-006 | Landing page sync functional | ❌ Not automated | ⚠️ HIGH | DevOps Engineer | 2026-08-15 |
| BLOCK-007 | Backup automation operational | ⚠️ Manual only | ⚠️ HIGH | DevOps Engineer | 2026-08-15 |
| BLOCK-008 | Health monitoring active | ❌ None | ⚠️ MEDIUM | DevOps Engineer | 2026-08-16 |

---

## Current Critical Gaps

### Gap 1: Untracked Services (Critical)

Services running on VPS but NOT in repository:

1. **9router** (`decolua/9router:latest`)
   - Running on port :20128
   - Public external access point
   - **No compose file in repo** ❌
   - **No documentation in repo** ❌

2. **Headroom** (`ghcr.io/chopratejas/headroom:latest`)
   - Resource management proxy
   - Running on port 8787
   - **No compose file in repo** ❌
   - **No service definition in repo** ❌

3. **Dozzle** (`amir20/dozzle:latest`)
   - Container log viewer at `/logs/`
   - Running via control-plane compose
   - **Not in repo docker-compose.yml** ❌
   - **No logging runbook** ❌

**Impact:** Without tracking these services, any disaster recovery operation will fail silently. No way to redeploy exactly matching production state without accessing VPS directly.

### Gap 2: Environment Variables Incomplete (High)

Current `.env.sample` does NOT include:

```bash
# Missing from template but used in VPS:
INSTALL_9ROUTER=true          ← Active but undocumented
INSTALL_HERMES=true           ✓ Documented
INSTALL_OPENCLAUDE=false      ← Configured but unused
INSTALL_LUMINE=true           ✓ Documented  
INSTALL_DOCKER=true           ✓ Documented
GITHUB_BACKUP_REPO=nabhanyuzqi1/lumine-backups
AUTHERIA_SESSION_SECRET       ← Needed but not in .env.vps
AUTHERIA_STORAGE_ENCRYPTION_KEY ← Needed but not in .env.vps
```

**Impact:** New operators cannot recreate environment from documentation alone. Potential configuration drift.

### Gap 3: No Disaster Recovery Validation (Critical)

Despite having backups at `/root/lumine-backups/`, NO one has ever tested:

```bash
# This has NEVER been executed:
./restore.sh /root/lumine-backups/<backup-file>.tar.gz
```

**Impact:** Compliance requirement failed. Cannot claim "disaster prepared" status. Unknown if backup files are valid/restorable.

### Gap 4: Security Audit Never Performed (Critical)

Internal or external security audit has NEVER been conducted on running system:

- [ ] SSH key rotation reviewed
- [ ] Firewall rules validated  
- [ ] Certificate lifecycle checked
- [ ] Secret exposure scan
- [ ] Access control matrix verified
- [ ] Logging retention confirmed

**Impact:** Operating without security validation. Compliance gap. Risk unknown.

---

## Immediate Action Required (Next 7 Days)

### Day 1-2: Repository Synchronization (Blocking Phase 16 Entry)

#### Task 1.1: Update docker-compose.prod.yml
Add missing services exactly as they run on VPS:

**File:** `backend/docker-compose.prod.yml`

Changes needed:
- Keep existing services intact (Postgres, Redis, API, MT5)
- Add 9router service definition
- Add headroom service definition
- Match environment variables from live `.env`
- Preserve volume mounts and network settings

**Verification Command:**
```bash
# After update, compare against VPS
diff backend/docker-compose.prod.yml <(ssh root@166.88.227.177 'cat /opt/lumine/backend/docker-compose.prod.yml')
# Must show zero differences
```

#### Task 1.2: Update control-plane docker-compose.yml
Add Dozzle service:

**File:** `infrastructure/control-plane/docker-compose.yml`

Changes needed:
- Add dozzle container definition
- Ensure Caddy routing handles `/logs/*` path
- Verify authelia integration works for `/logs/*`

**Verification Command:**
```bash
# Check service can start
cd infrastructure/control-plane && docker compose config --services | grep dozzle
# Should output: "dozzle"
```

#### Task 1.3: Complete .env Template
Add ALL variables currently in use:

**File:** `scripts/deploy/.env.template`

Changes needed:
- Add INSTALL_* flags documented above
- Add GITHUB_BACKUP_REPO variable
- Add AUTHERIA_SESSION_SECRET placeholder  
- Add AUTHERIA_STORAGE_ENCRYPTION_KEY placeholder
- Mark sensitive vs non-sensitive clearly

**Verification:**
```bash
grep -E "^[A-Z_]+=" scripts/deploy/.env.template | wc -l
# Should match number of grep lines from actual VPS .env
```

---

### Day 3: Documentation Creation

#### Task 2.1: Emergency Access Runbook
**File:** `docs/90-governance-and-operations/emergency-access.md`

Required sections:
1. SSH key rotation procedure
2. Lost credentials recovery steps  
3. Emergency escalation contacts (phone numbers)
4. Out-of-band communication channels
5. Access log review procedures
6. Incident reporting templates

**Validation:** Review by Security Officer + sign-off required

#### Task 2.2: Disaster Recovery Playbook
**File:** `docs/11-infrastructure/disaster-recovery-playbook.md`

Required sections:
1. Backup schedule and retention policy
2. Restore step-by-step procedures
3. Validation steps after restore
4. Known issues and workarounds
5. Rollback procedures if restore fails
6. Contact list for support escalation

**Validation:** Live DR test MUST be executed and documented

---

### Day 4: Automation Implementation

#### Task 3.1: Landing Page Auto-Sync Workflow
**File:** `.github/workflows/ci-cd-sync.yml`

Features:
- Trigger: PR merge to main OR manual workflow_dispatch
- Build frontend automatically
- SCP artifacts to `/var/www/lumine` on VPS
- In-place update (preserve inode)
- Health check verification step
- Alert on failure

**Validation:**
```bash
# Simulate deployment
git checkout -b test-sync
echo "<html>TEST</html>" > frontend/index.html
git commit -m "test"
git push origin test-sync
# Then trigger workflow manually
gh workflow run ci-cd-sync.yml
# Monitor https://github.com/nabhanyuzqi1/lumine-hedge-fund/actions
```

#### Task 3.2: Configuration Backup Automation
**File:** `.github/workflows/config-backup.yml`

Features:
- Schedule: Daily at 02:00 UTC
- Pull configs from VPS
- Store in separate branch (`refs/heads/config-backups`)
- Create comparison diff alerting
- Retain last 30 days snapshots

**Validation:**
```bash
# Wait for scheduled run or trigger manually
gh workflow run config-backup.yml
# Check new branch created
git ls-remote --heads origin config-backups
```

---

### Day 5-6: Testing & Validation

#### Task 4.1: Full DR Restore Test (ON STAGING ENVIRONMENT ONLY!)
**WARNING:** This MUST NOT be performed on production without coordination

Procedure:
1. Export current config state to isolated test directory
2. Download latest backup from `/root/lumine-backups/`
3. Attempt full restore in staging environment
4. Verify all containers come up healthy
5. Confirm data integrity (DB queries, etc.)
6. Document any errors encountered and resolved

**Deliverable:** Signed test report with screenshots/logs

#### Task 4.2: Landing Page Deployment Test
**Procedure:**
1. Make intentional change to local frontend code
2. Trigger deploy-workflow
3. Verify change appears on VPS landing page
4. Revert change to confirm rollback capability
5. Document success/failure points

**Deliverable:** Deployment procedure walkthrough video or GIF

---

### Day 7: Security Audit Preparation

#### Task 5.1: Pre-Audit Self-Check
Run through all checklist items and document findings BEFORE formal audit:

```markdown
### SSH Key Audit
[ ] All private keys stored securely (encrypted or hardware token)
[ ] All public keys registered in authorized_keys inventory
[ ] Key rotation scheduled within 90-day window
[ ] Unused keys identified and marked for removal

### Firewall Audit
[ ] Only ports 22, 80, 443, 20128 open externally
[ ] All internal service ports bound to localhost only
[ ] UFW rules documented and consistent across systems
[ ] Regular firewall rule review scheduled

### Certificate Audit
[ ] All SSL certificates renewed within validity period
[ ] Auto-renewal configured for Caddy Let's Encrypt certs
[ ] Manual override procedures documented
[ ] Expiration alerts set for 30-day advance warning

### Secret Exposure Audit
[ ] No secrets committed to git history (verified with trufflehog)
[ ] No secrets in Docker images (trivy scan passed)
[ ] Secrets encrypted before storage (.sops enabled)
[ ] Rotation procedure documented for each secret type
```

**Deliverable:** Completed self-check report identifying ANY findings (no matter how minor)

---

## Completion Criteria (Phase 15 Sign-Off)

None of the following can be marked incomplete:

✅ **Repository Alignment**
- All 13 containers have corresponding compose definitions
- All environment variables documented in .env.example
- Zero untracked services or configs in git history

✅ **Documentation Completeness**
- Emergency access procedures signed off by Security Officer
- Disaster recovery playbook includes tested restore procedure  
- Feature justification matrix complete for all additions
- Onboarding guide updated with all current services

✅ **Automation Functional**
- Landing page auto-sync workflow runs successfully
- Configuration backup automation operational
- Health monitoring dashboard shows all green indicators
- Alert notifications working end-to-end

✅ **Security Validated**
- Internal security audit completed with findings addressed
- All certificate lifecycles verified current
- SSH key rotation performed within last quarter
- Secret exposure scan passed (zero findings)

✅ **Quality Gates Passed**
- CI/CD pipeline runs green (all tests pass)
- Ruff lint clean (zero warnings/errors)
- MyPy type checks pass (zero errors)
- Coverage minimum met (80%+)
- No new vulnerabilities introduced (Trivy clean)

---

## Rollback Plan (If Issues Arise)

Should any task introduce breaking changes:

1. **Immediate:** Stop deployment process
2. **Rollback:** Use git revert to return to last known good commit
3. **Verify:** Confirm services back to previous stable state
4. **Investigate:** Analyze what caused issue
5. **Fix:** Correct issue in separate branch with thorough testing
6. **Reapply:** After sign-off from Architecture + Security leads

---

## Success Metrics

| Metric | Current | Target | Delta |
|--------|---------|--------|-------|
| Service coverage in repo | 67% | 100% | +33% |
| Documentation completeness | 70% | 100% | +30% |
| DR test validity | 0% | 100% | +100% |
| Automation jobs | 0 | 3 | +3 |
| Security audit status | N/A | Pass | Initial |

---

## Approval Requirements

Before marking Phase 15 Complete and transitioning to Phase 16:

1. **DevOps Lead Sign-off** → Confirms technical alignment complete
2. **Security Officer Approval** → Validates security posture acceptable
3. **System Architect Review** → Approves infrastructure design decisions  
4. **Product Owner Acceptance** → Confirms feature scope aligned
5. **Compliance Representative** → Signs off on regulatory requirements (if applicable)

**All signatures required on:** `docs/15-implementation/phases-15-signoff-form.md`

---

**Current Status:** PHASE 15 INCOMPLETE - BLOCKED BY CRITICAL GAPS  
**Target Completion:** 2026-08-20 (1 week from audit date)  
**Blocker Resolution Owner:** DevOps Team (with Engineering Support)

---

*This document requires revision each time a blocking item is resolved or a new blocker is identified.*
