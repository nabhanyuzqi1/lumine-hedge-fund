# SSH & Access Control

## Overview

Access control architecture per D12-2. Two SSH keys with strict separation
of concerns: one for automated CI deploy, one for human operator
administration. Both ed25519, no password authentication, no root login.

## Key architecture

| Key | User | Scope | sudo | Storage |
|-----|------|-------|------|---------|
| Deploy key | `lumine-deploy` | `/srv/lumine/` only | No | GitHub Actions secret (`SSH_DEPLOY_KEY`) |
| Admin key | `lumine-admin` | Full system | Yes | Operator password manager |

## SSH daemon configuration

```
# /etc/ssh/sshd_config (Phase 14+)
PermitRootLogin no
PasswordAuthentication no
ChallengeResponseAuthentication no
PubkeyAuthentication yes
AuthenticationMethods publickey
AllowUsers lumine-deploy lumine-admin
MaxAuthTries 3
ClientAliveInterval 300
ClientAliveCountMax 2
```

## Deploy key (CI)

### Key generation & distribution

1. Generate: `ssh-keygen -t ed25519 -C "lumine-ci-deploy" -f lumine-deploy`
2. Public key → `/home/lumine-deploy/.ssh/authorized_keys` on VPS
3. Private key → GitHub Actions secret `SSH_DEPLOY_KEY`

### `authorized_keys` restriction

```
command="cd /srv/lumine && exec $SSH_ORIGINAL_COMMAND",no-port-forwarding,no-X11-forwarding,no-agent-forwarding,no-pty ssh-ed25519 AAA... lumine-ci-deploy
```

The `command=` directive enforces:
- All commands run from `/srv/lumine/` only
- No port forwarding, no X11, no SSH agent forwarding
- No PTY allocation (no interactive shell)

### Permitted CI operations

The deploy key can only execute commands that `docker compose` and `sops`
support within `/srv/lumine/`:

- `docker compose pull`
- `docker compose up -d --remove-orphans`
- `docker compose run --rm migrate`
- `sops -d secrets.env > /srv/lumine/.env`
- `docker compose restart <service>`

It cannot: install packages, modify users, read other home directories,
access `/etc/`, or escalate to root.

### Compromise response

If the deploy key is compromised:
1. Remove the public key from `authorized_keys`
2. Revoke the GitHub Actions secret
3. Generate a new key pair
4. Update `authorized_keys` and GH Actions secret
5. Audit `security_events` for unauthorized deploy activity

The blast radius is limited: even with the key, the attacker can only
manipulate docker compose in `/srv/lumine/`. They cannot gain root, read
other data, or persist beyond the VPS.

## Admin key (operator)

### Key management

- Generated per operator: `ssh-keygen -t ed25519 -C "lumine-admin-<name>"`
- Public key → `/home/lumine-admin/.ssh/authorized_keys`
- Private key stored in operator's password manager; never in CI, never
  in repo, never on shared storage

### Permitted operations

Full sudo access. Used for:
- DR runbook execution (backup-dr.md)
- System package updates (`apt update && apt upgrade`)
- Docker daemon configuration changes
- Log inspection and debugging
- Manual database access for incident response
- Key rotation procedures

### Multiple operators

Each operator gets their own key in `authorized_keys`. No shared keys.
When an operator leaves, remove their key — no other key rotation needed.

## Access control matrix

| Resource | `lumine-deploy` | `lumine-admin` | Other |
|----------|-----------------|----------------|-------|
| `/srv/lumine/` | Read, write (via compose/sops) | Full | None |
| `/etc/` | None | Full (sudo) | None |
| `/home/*` | None | Full (sudo) | None |
| Docker socket | Via compose commands only | Full (sudo) | None |
| PostgreSQL | Via compose service (app user) | Direct (psql, sudo) | None |
| System packages | None | Full (sudo) | None |

## What this document does NOT define

- Concrete `sshd_config` file and deployment method (Phase 14+).
- User account creation scripts (Phase 14+).
- Operator onboarding/offboarding procedure (Phase 14+ operational
  policy).
- Key rotation automation (Phase 14+).

## Phase boundary

SSH architecture and access control rules are fixed here. Configuration
files and automation belong to Phase 14+.