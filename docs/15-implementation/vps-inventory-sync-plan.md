# VPS Infrastructure Inventory & Sync Plan

**Server:** 166.88.227.177  
**Date:** 2026-08-13  
**Status:** Production Running (13 containers active)  

---

## Current Deployment State

### Container Services (Running)

| Container | Image | Port(s) | Purpose | Repo Location |
|-----------|-------|---------|---------|---------------|
| `backend-api` | Custom (Dockerfile) | 8000 | FastAPI application | `backend/Dockerfile`, `backend/docker-compose.prod.yml` ✓ |
| `backend-postgres` | postgres:16-alpine | 5432 | Primary database | `backend/docker-compose.prod.yml` ✓ |
| `backend-redis` | redis:7-alpine | 6379 | Cache/broker transport | `backend/docker-compose.prod.yml` ✓ |
| `9router` | decolua/9router:latest | 20128 | LLM gateway proxy | **Missing** ✗ |
| `headroom` | ghcr.io/chopratejas/headroom:latest | 8787 | Resource control | **Missing** ✗ |
| `lumine-mt5` | Custom (MT5 Wine) | 5900,6901 | MT5 broker desktop | `scripts/deploy/mt5/` ✓ |
| `control-caddy` | caddy:2 | host network | TLS reverse proxy | `infrastructure/control-plane/caddy/Caddyfile` ✓ |
| `control-authelia` | authelia/authelia:4.39 | host network | SSO authentication | `infrastructure/control-plane/authelia/` ✓ |
| `control-homepage` | gethomepage/homepage:latest | host network | Service dashboard hub | `infrastructure/control-plane/homepage/` ✓ |
| `control-uptime-kuma` | louislam/uptime-kuma:1 | host network | Health monitoring | `infrastructure/control-plane/uptime-kuma/` ✓ |
| `control-landing` | nginx:alpine | 127.0.0.1:8080 → 80 | Marketing landing page | `dashboard/index.html`, `infrastructure/control-plane/landing/` ✓ |
| `control-dozzle` | amir20/dozzle:latest | host network | Log viewer | **Missing** ✗ |
| `hermes` | hermes-agent | - | AI agent messaging | `infrastructure/hermes/docker-compose.yml` ✓ |

---

## Missing Repository Components

The following services are **running on VPS but not committed** to repository:

### 1. 9router Configuration
**Why needed:** External AI agent access point (port 20128)

**Action Required:**
- ✅ Create `backend/docker-compose.9router.yml` or add to prod compose
- ✅ Document in `docs/06-ai/llm-gateway.md`
- ✅ Security controls at `docs/12-security/9router-access.md`

### 2. Headroom (Resource Control)
**Why needed:** Resource management/proxying for LLM calls

**Action Required:**
- ✅ Add to compose configuration
- ✅ Document usage pattern in planning docs
- ✅ Security review for production exposure

### 3. Dozzle Logging
**Why needed:** Real-time container log viewing at `/logs/`

**Action Required:**
- ✅ Add to control-plane compose
- ✅ Document access via Authelia route at `/logs/*`
- ✅ Review log retention/security implications

---

## Additional Configuration Files Needed

### Environment Variables
Current `/opt/lumine/.env` has these keys:

```bash
VPS_HOST=166.88.227.177
VPS_USER=root
VPS_SSH_PORT=22
DB_PASSWORD=<generated>              ← In .gitignore
HMAC_SECRET_KEY=<generated>          ← In .gitignore  
LLM_GATEWAY_API_KEY=PLACEHOLDER      ← Needs UUID update
VNC_PASSWORD=LumineVnc!2026           ← Good practice
GITHUB_BACKUP_TOKEN=<optional>       ← Optional
BACKUP_DIR=/root/lumine-backups
BACKUP_RETENTION_DAYS=7
INSTALL_9ROUTER=true                  ← Currently active
INSTALL_HERMES=true                   ← Currently active
INSTALL_OPENCLAUDE=false             ← Not deployed?
INSTALL_LUMINE=true                   ← Active
INSTALL_DOCKER=true                   ← Pre-installed
```

**Repository Gap:** Need `.env.sample` that reflects ALL variables used, including optional ones.

### Docker Compose Consolidation
Current situation: Multiple compose files scattered across repo

```
/opt/lumine/backend/docker-compose.prod.yml     ← Backend services
/srv/control-plane/docker-compose.yml           ← Control plane (Caddy, Authelia, etc.)
/opt/hermes/hermes-agent/docker-compose.yml     ← Hermes messaging (separate root)
```

**Gap Analysis:**

| Aspect | Status | Action |
|--------|--------|--------|
| Single source-of-truth compose | ❌ Fragmented | Create unified `docker-compose.all.yml` or consolidate references |
| Development override file | ⚠️ Exists but incomplete | Update with all local development overrides |
| Backup volume mounts | ✅ Partially documented | Verify all volumes are mounted correctly |
| Network isolation | ✅ Implemented | Document network topology in infra docs |

---

## Documentation Gaps Identified

### What Should Exist But Doesn't

1. **VPS-Specific Configuration Guide**
   - Where: `docs/14-implementation/vps-setup.md` or extend existing
   - Content: Server requirements, installation commands, post-install verification
   - Priority: High (onboarding blocker)

2. **Control Plane Architecture**
   - Where: `docs/11-infrastructure/control-plane.md` (partially exists)
   - Content: Caddy routing rules, Authelia users/groups, Homepage configuration
   - Priority: High (security critical)

3. **Backup & Restore Procedures**
   - Where: `docs/11-infrastructure/backup-dr.md` (exists but incomplete)
   - Content: Full restore procedures, recovery time objectives, backup validation tests
   - Priority: Critical (DR compliance)

4. **Emergency Access Runbook**
   - Where: `docs/90-governance-and-operations/emergency-access.md`
   - Content: SSH key rotation, lost credentials recovery, emergency escalation paths
   - Priority: Critical (operational safety)

5. **Feature Justification Matrix**
   - Where: New document linking each service to business value
   - Content: Why 9router? Why Dozzle? Cost-benefit analysis for each added service
   - Priority: Medium (governance requirement)

---

## Phase 15 Compliance Checklist

### Completed (Already in Plans/Docs)
- [x] Core backend services (Postgres, Redis, API)
- [x] MT5 integration via Wine
- [x] Git-based deployment structure
- [x] Authelia + Caddy security layer
- [ ] 9router external gateway (MISSING FROM PLANS)
- [ ] HermeS agent framework (INCOMPLETE DOCUMENTATION)
- [ ] Monitoring stack (partial - dozzle missing from plan)

### Requires Planning Addition
- [ ] Add 9router to Phase 6 AI strategy docs
- [ ] Add headroom resource control to documentation
- [ ] Add dozzle logging to observability section
- [ ] Update Phase 11 infrastructure inventory
- [ ] Update deployment topologies

---

## Immediate Actions Required

### Priority 1: Repository Sync
1. Copy VPS configurations to git-tracked files:
   ```bash
   scp root@166.88.227.177:/opt/lumine/.env /tmp/current-env
   scp root@166.88.227.177:/srv/control-plane/docker-compose.yml ./backups/control-plane.yml.backup
   ```
2. Create comprehensive `.env.example` with ALL variables
3. Document why each service exists in comments within compose files

### Priority 2: Documentation Updates
1. Extend `docs/14-implementation/onboarding.md` to include VPS connection guide
2. Create `docs/11-infrastructure/vps-inventory.md` showing current state
3. Update `README.md` with complete architecture diagram

### Priority 3: CI/CD Automation
1. Add workflow to auto-sync landing page changes from local → VPS
2. Add scheduled backup upload to GitHub
3. Implement health check verification step in deploy pipeline

### Priority 4: Cleanup & Simplification
1. Audit unused installations (`INSTALL_OPENCLAUDE` set true but no evidence of deployment?)
2. Consolidate compose file references to single source
3. Remove backup copy files (`*.bak-*`) from repository tracking

---

## Risk Assessment

### Current Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| No versioned backup of VPS config | HIGH | Implement automated config backups to repo |
| Secrets in untracked files | MEDIUM | Standardize on tracked `.env.template` + ignore actual `.env` |
| Landing page not synced from code | MEDIUM | Add CI workflow for automated sync |
| No disaster recovery test performed | HIGH | Schedule quarterly DR drill |
| Feature creep without approval | LOW | Create feature justification matrix |

---

## Timeline for Resolution

| Milestone | Target Date | Owner |
|-----------|-------------|-------|
| Complete .env.example | 2026-08-13 | DevOps Lead |
| Document all compose services | 2026-08-14 | System Architect |
| Update Phase 15 plans | 2026-08-15 | Product Owner |
| Create CI/CD sync workflow | 2026-08-16 | Automation Engineer |
| Full DR test execution | 2026-08-20 | Operations Team |
| Feature justification complete | 2026-08-22 | Technical Steering Committee |

---

## Verification Steps

After sync completion, verify:

```bash
# 1. Check all env vars are documented
grep -r "ENV\[" docs/*.md scripts/**/*.sh

# 2. Verify compose files match running containers
docker ps -a --format "{{.Names}}" > /tmp/running.txt
git grep -l "services:" backend/*.yml infrastructure/*/compose* | xargs grep -oP 'service:\s+\w+' > /tmp/composed.txt
diff <(sort /tmp/running.txt) <(sort /tmp/composed.txt)  # Should show only intentional differences

# 3. Confirm landing page can be rebuilt from repo
cd frontend && npm run build && ls -la dist/
scp dist/* root@166.88.227.177:/tmp/test-build/

# 4. Validate backup automation works
./scripts/deploy/backup.sh --test-run
cat /tmp/lumine-backup-*/backup-*.tar.gz | tar tzf - | wc -l  # Should show content

# 5. Test DR recovery procedure (off-hours!)
ssh root@166.88.227.177 "sudo /opt/lumine/scripts/deploy/restore.sh /root/lumine-backups/backup-test.tar.gz"
# Monitor for successful rollback

# 6. Verify health checks respond
curl https://166.88.227.177/api/health 2>/dev/null || echo "Health endpoint not exposed yet"
```

---

**Conclusion:** The VPS deployment represents a **functional production system** that exceeds initial Phases 14 scope but hasn't been fully documented or planned for. This creates operational risk (no version control on configs) and governance gaps (features deployed without formal approval).

**Resolution Strategy:**
1. **Capture current state** via comprehensive inventory
2. **Document decisions** explaining why each service exists
3. **Automate synchronization** so repo ↔ VPS stay aligned
4. **Add governance** process for future feature additions
5. **Test recovery** to validate backup & DR procedures

**Next Meeting Item:** Present this inventory to technical steering committee for phase 15 plan updates and approval of additional services.
