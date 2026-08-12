# SSH Key Rotation Policy & Procedure

**Last Rotation:** 2026-08-06 (7 days ago - within acceptable window)  
**Next Rotation Due:** Quarterly (next: 2026-11-06)  

## Current Key Inventory
```bash
# On VPS 166.88.227.177:
ls -la /root/.ssh/id_*
```

## Key Details
- **Algorithm:** ED25519 (recommended, modern standard)
- **Passphrase:** None (automated deployments require passphrase-less keys)
- **Authorized Users:** DevOps team only
- **Key Age:** 7 days old (within 90-day compliance window)

## Rotation Schedule
- **Quarterly automated rotation** (every 90 days minimum)
- **Immediate rotation required if:**
  - Any suspected compromise
  - Personnel change with access
  - System breach detected

## Automated Monitoring
Set up alert at Day 60 of key age to trigger quarterly rotation workflow.

## Compliance Note
Meets SOC 2 CC6.1 and ISO 27001 A.9.2.3 requirements with documented schedule.
