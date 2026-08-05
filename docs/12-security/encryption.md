# Encryption & Key Management

## Overview

Encryption architecture per D12-3. Three independent layers — disk,
column, and backup — each with its own key, no circular dependency. This
document also defines the key custody model for SOPS + age (D11-6) and
the rotation procedure.

## Three-layer encryption

### Layer 1 — Disk (LUKS2/dm-crypt)

| Property | Value |
|----------|-------|
| Algorithm | aes-xts-plain64 |
| Key size | 512-bit |
| Scope | Entire VPS root volume |
| Key custody | Passphrase in operator password manager |
| Unlock | Manual at boot (no TPM/network) |
| LUKS header backup | Operator password manager |

**Applied during VPS provisioning**, before Docker or any application is
installed. The LUKS passphrase is independent of all application secrets —
no circular dependency during recovery. If `.env.enc` is lost, the disk
can still be unlocked for data recovery.

### Layer 2 — Column (pgcrypto)

| Property | Value |
|----------|-------|
| Algorithm | `pgp_sym_encrypt` with AES-256 |
| Scope | `secret_hash`, `credentials`, `personal_data` columns |
| Key custody | `APP_ENCRYPTION_KEY` in `.env` (SOPS-encrypted) |
| Encrypt/decrypt | Application layer, not PostgreSQL |

**Encrypted columns:**

| Column | Table (indicative) | Rationale |
|--------|---------------------|-----------|
| `secret_hash` | `api_keys` | HMAC signing key hash |
| `credentials` | `broker_accounts` | MT5 credentials, API keys |
| `personal_data` | (future) | Any PII if added later |

Encrypt/decrypt happens in the application, not in SQL queries.
PostgreSQL never sees plaintext for these columns. A database dump or
compromised DB connection does not expose secrets.

### Layer 3 — Backup (rclone crypt)

| Property | Value |
|----------|-------|
| Algorithm | NaCl secretbox (XSalsa20 + Poly1305) |
| Scope | All backup data leaving the VPS |
| Key custody | `RCLONE_CRYPT_PASSWORD` in `.env` (SOPS-encrypted) |
| Encryption point | Client-side, before upload |

All data is encrypted before it leaves the VPS. The object storage
provider (B2/S3) never sees plaintext. The crypt password is a separate
secret from the disk passphrase and the application encryption key.

## Key dependency graph

```
Operator password manager
  ├── LUKS passphrase ──► disk unlock
  └── Age private key ──► decrypt .env.enc
                            │
                            └──► /srv/lumine/.env
                                   ├── APP_ENCRYPTION_KEY ──► pgcrypto
                                   ├── RCLONE_CRYPT_PASSWORD ──► backup encryption
                                   ├── DB_PASSWORD
                                   └── ...all other runtime secrets

GitHub Actions secret
  └── Age private key ──► decrypt .env.enc (CI deploy only)
```

No single key unlocks everything. No circular dependency:
- LUKS passphrase can unlock the disk without `.env`
- Age key can decrypt `.env` without LUKS passphrase
- Application key and rclone password are in `.env`, not on disk directly

## Secrets flow (from D11-6)

```
┌─ Repo ──────────────────────────────────────────────────┐
│  .env.enc (SOPS + age, encrypted)                        │
│  .sops.yaml (age public key fingerprint)                 │
└──────────────────────────────────────────────────────────┘
                    │
                    │ CI deploy: SSH to VPS
                    ▼
┌─ VPS ───────────────────────────────────────────────────┐
│  sops -d .env.enc → /srv/lumine/.env                     │
│  docker compose up -d                                    │
│    ├── lumine-trade-core ← env: DB_PASSWORD, APP_KEY...  │
│    ├── lumine-llm-gateway ← env: 9ROUTER_API_KEY...      │
│    └── ...all services ← env vars from .env              │
│                                                          │
│  No secrets in:                                          │
│  - Image layers                                          │
│  - Container logs                                        │
│  - CI runner workspace                                   │
│  - Docker compose output                                 │
└──────────────────────────────────────────────────────────┘
```

## Key rotation

### Rotate age key pair

1. Generate new key: `age-keygen -o new-key.txt`
2. Extract public key → update `.sops.yaml`
3. Re-encrypt: `sops updatekeys .env.enc`
4. Update GitHub Actions secret and operator password manager with new private key
5. Commit updated `.sops.yaml` and `.env.enc`
6. Deploy — new key active immediately
7. Revoke old key after confirming deploy success

### Rotate application encryption key

1. Generate new key: `openssl rand -hex 32`
2. Update `APP_ENCRYPTION_KEY` in `.env`
3. Re-encrypt `.env.enc`: `sops updatekeys` then edit
4. Run migration script to re-encrypt affected columns with new key, old key
   still valid during transition
5. Deploy
6. Run cleanup script to re-encrypt remaining rows with new key only

### Rotate rclone crypt password

1. Generate new password
2. Update `RCLONE_CRYPT_PASSWORD` in `.env`
3. Re-encrypt `.env.enc`
4. Create new rclone crypt remote with new password
5. Full backup to new remote
6. Deploy with new remote config
7. Delete old backup data after new backup verified

## What this document does NOT define

- Concrete LUKS setup commands, `pgcrypto` migration SQL, rclone
  configuration files (Phase 14+).
- Key rotation automation scripts (Phase 14+).
- Access policy: who may hold age key, approval for rotation
  (Phase 14+ operational policy).

## Phase boundary

Encryption architecture, key custody, and rotation procedures are fixed
here. Implementation scripts and configuration files belong to Phase 14+.