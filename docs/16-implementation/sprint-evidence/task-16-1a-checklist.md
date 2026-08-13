# Sprint 16.1 Task Checklist

**Task:** 16.1.A — VPS Configuration & Hardening  
**Owner:** Platform Engineer + Security Engineer  
**Duration:** Day 1-2 (Aug 13-14, 2026)  
**Status:** IN PROGRESS  

## Current State (Verified Aug 13)
```bash
VPS: host1785957413 (166.88.227.177)
Docker: All 13 services UP and HEALTHY
SSL Certificates: Active and auto-renewing
Backup Encryption: Operational (AES-256-CBC)
Monitoring: Basic uptime check active
```

## Tasks to Complete Today

### ✓ Task 1: Connect and Verify
- [x] SSH connected successfully
- [x] Docker Engine verified (v29.x installed)
- [x] Container status confirmed (all healthy)
- [x] Disk space adequate (87% free)

### ⏳ Task 2: OS Updates & Patching
- [ ] Run system updates: `apt update && apt upgrade -y`
- [ ] Install security packages: `fail2ban`, `ufw`, `auditd`
- [ ] Configure automatic security updates

### ⏳ Task 3: Firewall Configuration
- [ ] Verify UFW status
- [ ] Allow only essential ports: 22, 80, 443, 20128
- [ ] Deny all other incoming traffic
- [ ] Configure rate limiting for SSH

### ⏳ Task 4: System Hardening
- [ ] Disable root login (use sudo)
- [ ] Configure SSH key-only authentication
- [ ] Set up automatic log rotation
- [ ] Enable audit logging for sensitive operations

### ⏳ Task 5: Documentation
- [ ] Document current baseline configuration
- [ ] Record firewall rules applied
- [ ] Log hardening changes made

## Expected Outcome

By end of Day 2:
- ✅ VPS fully hardened against common threats
- ✅ Minimal attack surface exposed
- ✅ Comprehensive logging enabled
- ✅ Baseline documented for future reference

## Success Criteria

| Criterion | Target | Measurement |
|-----------|--------|-------------|
| Port exposure | ≤ 4 ports | External scan verifies |
| SSH security | Key-only | Password auth disabled |
| Logging coverage | Critical events | Audit logs present |
| Update status | Current | No pending patches |

## Blockers/Issues

None identified so far. Proceeding as planned.

---

**Next Review:** End of Day 2 (Aug 14, 17:00 UTC)  
**Sign-off Required:** Security Officer before proceeding to service deployment
