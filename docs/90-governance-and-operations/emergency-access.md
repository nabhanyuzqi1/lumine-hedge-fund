# Emergency Access Procedures — Lumine Production Infrastructure

**Version:** 1.0  
**Date:** 2026-08-13  
**Classification:** INTERNAL - OPERATORS ONLY  
**Review Cycle:** Every 90 days or after any access procedure change  

---

## Purpose

This document provides authorized personnel with step-by-step procedures for emergency access to the Lumine production infrastructure in situations including but not limited to:

- Lost credentials (SSH keys, passwords)
- Security breach requiring immediate key rotation
- System unresponsive and requiring out-of-band access
- Disaster recovery requiring emergency deployment access
- Compliance incident requiring immediate system lockdown

**IMPORTANT:** This document itself should NEVER be committed to public repositories. Keep offline or in secure, encrypted storage only.

---

## Authorized Personnel

Only the following roles are authorized to perform emergency access procedures:

| Role | Contact Method | Authorization Level | Approval Required |
|------|----------------|---------------------|-------------------|
| DevOps Lead | Phone + PagerDuty | Full infrastructure access | None (own authority) |
| Security Officer | Phone + Encrypted Signal | Read-only + audit access | Security Director |
| Operations Manager | Email + PagerDuty | Limited operational access | DevOps Lead |
| External Support | Pre-approved ticket | No direct access (supervised) | CTO + Legal |

**ALL emergency access must be logged immediately after execution.**

---

## SSH Key Emergency Rotation

### Scenario: Lost Private Keys or Compromised Credentials

#### Step 1: Generate New Key Pair
```bash
# On LOCAL MACHINE (secure, isolated)
ssh-keygen -t ed25519 -f ~/.ssh/lumine_emergency_$(date +%Y%m%d) -C "emergency-access-$(date +%Y%m%d)" -N ""

# Verify generated files
ls -la lumine_emergency_*
```

#### Step 2: Upload Public Key to VPS
```bash
# Via existing authorized mechanism (email/encrypted message from previous key holder)
# Send this command to ops team via secure channel:
echo "PASTE_PUBLIC_KEY_HERE" > /tmp/new_key.pub

# Execute on VPS (using existing backup access or pre-provisioned alternate method)
ssh root@166.88.227.177 << 'EOF'
  cat /tmp/new_key.pub >> /root/.ssh/authorized_keys
  chmod 600 /root/.ssh/authorized_keys
  systemctl restart sshd
EOF
```

#### Step 3: Revoke Old Keys
```bash
# Review all authorized_keys entries
ssh root@166.88.227.177 "grep -n '^#' /root/.ssh/authorized_keys || echo 'No comments found'; grep -v '^#' /root/.ssh/authorized_keys > /tmp/all_keys.txt; wc -l /tmp/all_keys.txt"

# Comment out or remove compromised keys
# IMPORTANT: Document which keys were revoked with timestamp
```

#### Step 4: Distribution of New Private Key
```bash
# Encrypt private key with strong passphrase
openssl aes-256-cbc -salt -in ~/.ssh/lumine_emergency_*.pem -out ~/lumine_emergency_encrypted.key.enc

# Transfer encrypted key via secure channel ONLY:
# - Physical handoff (recommended)
# - Encrypted email with password sent separately
# - Hardware token delivery if available
```

#### Step 5: Verification
```bash
# Test new key works before revoking old ones
ssh -i ~/.ssh/lumine_emergency_new_ed25519 root@166.88.227.177 "hostname && docker ps --format '{{.Names}}'"

# Confirm all services still running correctly
ssh -i ~/.ssh/lumine_emergency_new_ed25519 root@166.88.227.177 "docker compose -f /opt/lumine/backend/docker-compose.prod.yml ps"
```

#### Documentation Requirements
```markdown
- Timestamp of rotation: YYYY-MM-DD HH:MM UTC
- Reason for rotation: [Specific reason]
- Who performed rotation: [Name, role]
- Who witnessed rotation: [Name, role]  
- Old key hash(es) removed: [SHA256 hashes]
- New key hash added: [SHA256 hash]
- Verification complete: YES/NO
- Incident report filed: YES/NO
```

---

## Lost Root Password Recovery

### Scenario: Cannot authenticate as root user

#### Option A: Single-User Mode (Requires Console Access)

1. **Reboot server via console management interface** (IPMI/iLO/Datadog):
   ```
   At boot menu, add "single" or "init=/bin/bash" to kernel parameters
   Press Enter to boot into single-user mode
   ```

2. **Remount filesystem read-write**:
   ```bash
   mount -o remount,rw /
   
   # If using LUKS encryption, unlock first
   cryptsetup luksOpen /dev/sdaX cryptroot
   mount /dev/mapper/cryptroot /mnt
   mount --bind /dev /mnt/dev
   mount --bind /proc /mnt/proc
   mount --bind /sys /mnt/sys
   chroot /mnt
   ```

3. **Reset root password**:
   ```bash
   passwd root
   # Follow prompts to enter new password
   ```

4. **Verify and exit**:
   ```bash
   touch /.autorelabel  # If SELinux enabled
   reboot -f
   ```

#### Option B: Rescue Environment (Recommended for Production)

1. **Boot from rescue disk** via cloud provider console:
   - AWS: Instance > Actions > Reset instance password
   - GCP: Serial console access
   - Azure: Reset password via portal

2. **Attach original disk as secondary volume**, mount, and recover:
   ```bash
   # In rescue environment
   mkdir /mnt/original
   mount /dev/sda1 /mnt/original
   
   # Edit shadow file or reset password
   chroot /mnt/original passwd root
   
   # Backup shadow changes
   cp /mnt/original/etc/shadow /backup/root_shadow_backup_$(date +%Y%m%d)
   ```

3. **Detach rescue disk, attach original, reboot normally**

4. **Test new credentials immediately**

---

## Emergency Deployment Lockdown

### Scenario: Suspected security breach requiring immediate isolation

#### Step 1: Isolate Network Access
```bash
# Block all external traffic except SSH from whitelisted IPs
ssh root@166.88.227.177 << 'EOF'
  ufw disable
  
  # Allow SSH only from known trusted networks
  ufw allow from 10.0.0.0/8 to any port 22
  ufw allow from 192.168.0.0/16 to any port 22
  
  # Block all other incoming traffic
  ufw default deny incoming
  ufw default allow outgoing
  
  ufw enable
  ufw status verbose
EOF
```

#### Step 2: Stop Non-Essential Services
```bash
ssh root@166.88.227.177 << 'EOF'
  docker stop 9router dozzle homepage 2>/dev/null || true
  
  # Keep essential services running
  docker restart api postgres redis 2>/dev/null || true
EOF
```

#### Step 3: Enable Enhanced Logging
```bash
ssh root@166.88.227.177 << 'EOF'
  # Capture full system state
  tar czf /tmp/emergency_state_$(date +%Y%m%d_%H%M%S).tar.gz \
    /var/log/auth.log \
    /var/log/syslog \
    /root/.ssh/authorized_keys \
    /opt/lumine/.env
  
  # Copy to secure off-site location immediately
  scp /tmp/emergency_state_*.tar.gz backup-team@secure-server:/incoming/
EOF
```

#### Step 4: Notify Stakeholders
```markdown
Immediate notifications required:
- Engineering lead: Slack #incident-response
- Security team: Slack #security-alerts
- Management: Email summary within 15 minutes
- External auditors: If compliance triggered
```

---

## Credential Recovery Checklist

Use this checklist to verify no steps missed during credential recovery:

- [ ] Generated new SSH key pair with ED25519 algorithm
- [ ] Tested new key connectivity before removing old access
- [ ] Rotated all service passwords (Postgres, Redis, Authelia, etc.)
- [ ] Updated all deployed configuration files
- [ ] Verified all containers can authenticate with new credentials
- [ ] Tested API endpoints respond correctly
- [ ] Checked monitoring systems show healthy status
- [ ] Confirmed backups can restore with new credentials
- [ ] Documented all changes in incident log
- [ ] Scheduled follow-up review within 7 days
- [ ] Conducted post-incident analysis if breach suspected
- [ ] Notified affected users if data privacy impacted

---

## Contact Information (Secure Storage Required)

Store these contacts in ENCRYPTED form, accessible only to authorized personnel:

| Service | Primary Contact | Alternate Contact | Phone | Slack Channel |
|---------|-----------------|------------------|-------|---------------|
| DevOps Lead | [Name Redacted] | [Name Redacted] | +[Redacted] | @devops-emergency |
| Security Officer | [Name Redacted] | [Name Redacted] | +[Redacted] | @security-emergency |
| Network Admin | [Name Redacted] | N/A | +[Redacted] | @network-emergency |
| Cloud Provider Support | AWS/GCP/Azure | Account ID: [Redacted] | 1-[Redacted] | N/A |
| Hardware Vendor | [Vendor Name] | RMA#: [Redacted] | 1-[Redacted] | N/A |

**DO NOT store contacts in plain text anywhere accessible to general team.**

---

## Testing Schedule

Emergency procedures must be tested:

- **Quarterly:** Full drill involving at least 2 team members
- **After major changes:** Whenever infrastructure architecture changes
- **After actual incidents:** Immediately post-incident

### Quarterly Drill Checklist

- [ ] Rotate test SSH key (development environment only)
- [ ] Practice password recovery on staging
- [ ] Simulate network lockdown and recovery
- [ ] Test emergency communication channels work
- [ ] Verify documentation up-to-date
- [ ] Update contact information if changed
- [ ] Document lessons learned

---

## Incident Reporting Template

Use this template for ALL emergency access events:

```markdown
# Incident Report: Emergency Access Event

**Incident ID:** EMERGENCY-[YYYYMMDD]-[NNN]  
**Date/Time:** YYYY-MM-DD HH:MM UTC  
**Severity:** Critical / High / Medium / Low  

## Summary
[Brief description of what happened]

## Authorization
Performed by: [Name, Role]  
Witnessed by: [Name, Role] (if applicable)  
Approved by: [Name, Role]  

## Root Cause
[What led to need for emergency access]

## Actions Taken
[Step-by-step technical actions performed]

1. ...
2. ...
3. ...

## Outcome
[Result of actions taken]  
[Current system status]  
[Any ongoing issues]

## Lessons Learned
[What we learned from this incident]  
[Improvements needed to prevent recurrence]

## Attachments
[Logs, screenshots, evidence collected]
```

---

## Compliance Notes

All emergency access procedures must comply with:

1. **Internal Security Policy:** Section 4.2 (Emergency Response)
2. **SOC 2 Type II Controls:** CC6.1 (Access Management), CC6.6 (Logical Access)
3. **ISO 27001:** A.9.2.3 (Authentication Information Protection)
4. **GDPR (if applicable):** Article 32 (Security of Processing)
5. **PCI DSS (if applicable):** Requirement 7 (Access Control)

**Every emergency access event MUST be reported to compliance officer within 24 hours.**

---

**Document Owner:** DevOps Team  
**Last Review Date:** 2026-08-13  
**Next Review Due:** 2026-11-13  
**Classification:** CONFIDENTIAL - RESTRICTED ACCESS
