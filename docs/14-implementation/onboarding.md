# Lumine Onboarding — VPS Setup & Secrets Management

**Phase:** 14 Implementation  
**Owner:** DevOps / operators  
**Version:** 1.0 (2026-08-13)  

---

## Quick Start

### 1. Clone Repository & Extract SSH Key

```bash
git clone git@github.com:nabhanyuzqi1/lumine-hedge-fund.git
cd lumine-hedge-fund

# SSH key sudah ada di root folder sebagai `id_rsa` (private)
# Public key (id_rsa.pub) sudah ditambahkan ke ~/.ssh/authorized_keys di VPS
# Gunakan:
eval "$(ssh-agent -s)"
ssh-add id_rsa  # load private key to agent
```

### 2. Copy & Configure Secret Files

```bash
cd scripts/deploy

# Template → actual credential mapping (edit ini sekali!)
cp .env.sample .env
$EDITOR .env

# Isi variabel berikut:
VPS_HOST=166.88.227.177      ← IP VPS production
VPS_USER=root                ← user SSH (default root)
VPS_SSH_PORT=22              ← port SSH

DB_PASSWORD=<generate-strong-password>       ← password PostgreSQL
HMAC_SECRET_KEY=<generate-secure-secret>     ← API HMAC signing key
LLM_GATEWAY_API_KEY=<9router-API-key>       ← gateway authentication key
VNC_PASSWORD=<min-6-characters>              ← MT5 desktop access password
```

**Generate strong values:**
```bash
# PostgreSQL password (random 32 char)
openssl rand -base64 32

# HMAC secret (random 64 char hex)
openssl rand -hex 64

# 9router API key (gunakan UUID atau generate via 9router interface)
uuidgen

# VNC password (minimal 6 alphanumeric chars)
echo "MySecureVnc123"
```

**Jangan pernah commit file `.env`!** Sudah ada di `.gitignore`.

### 3. Deploy Stack

```bash
# Local deployment test (optional — hanya deploy frontend landing)
./deploy-site.sh

# Full stack deployment (backend services + MT5 container)
./deploy-stack.sh

# Export state untuk migrasi lokal → remote (optional)
./export-state.sh state-exports/<timestamp>.tar.gz
```

### 4. Verify Deployment

```bash
# SSH ke VPS
ssh root@166.88.227.177

# Check all containers running healthy
cd /opt/lumine/backend
docker compose -f docker-compose.prod.yml ps

# Health check API endpoint
curl http://localhost:8000/health

# Access MT5 noVNC desktop (via browser)
http://166.88.227.177:6901/vnc.html
# Password = value VNC_PASSWORD dari .env

# Control plane dashboard (via Caddy + Authelia login)
https://166.88.227.177/
```

---

## Production Environment Architecture

### Service Topology

| Root Directory | Compose Stack | Services |
|---|---|---|
| `/srv/control-plane/` | `control-plane` | caddy, authelia, homepage, uptime-kuma, landing, dozzle |
| `/opt/lumine/backend/` | `backend` | postgres, redis, api, mt5, headroom, 9router |
| `/opt/hermes/hermes-agent/` | `hermes-agent` | hermes |

### Network Binding Rules

| Port | Service | Public/Private | Purpose |
|---|---|---|---|
| :443 | Caddy | **PUBLIC** | TLS termination, reverse proxy |
| :80 | Caddy | **PUBLIC** | HTTP redirect, ACME challenge |
| :22 | SSH | **PUBLIC** | Administration (ED25519 keys only) |
| :20128 | 9router | **PUBLIC** | External AI agent gateway (plain HTTP) |
| :8000 | API | Private (loopback) | Entry via Caddy only |
| :5900 | MT5 VNC | Private (loopback) | Entry via Caddy + Authelia |
| :6901 | MT5 noVNC | Private (loopback) | Entry via Caddy + Authelia |
| :9091 | Authelia | Private (loopback) | SSO authentication |
| :3000 | Homepage | Private (loopback) | Service hub |
| :3001 | Uptime Kuma | Private (loopback) | Health monitoring |

**Exception:** Only `9router` binds public port :20128 for external AI agents. All other services are loopback-only and accessed via Caddy reverse proxy.

### Firewall (UFW Configuration)

```bash
sudo ufw allow ssh       # port 22 (SSH)
sudo ufw allow http      # port 80 (Caddy ACME)
sudo ufw allow https     # port 443 (Caddy HTTPS)
sudo ufw allow 20128/tcp # 9router (public egress gateway)
sudo ufw enable          # apply rules
```

---

## CI/CD Pipeline Overview

### Backend Workflow (`.github/workflows/ci.yml`)

```yaml
on:
  push:
    branches: [main]
    paths: ["backend/**", ".github/workflows/ci.yml"]
  pull_request:
    branches: [main]
    paths: ["backend/**", ".github/workflows/ci.yml"]

jobs:
  lint:             # ruff check format validation
  type-check:       # mypy strict mode
  security:         # bandit semgrep gitleaks pip-audit
  unit-tests:       # pytest with coverage gate 80%
  integration-tests: # testcontainers PG+Redis
  contract-tests:   # API contract validation
  openapi-diff:     # drift detection against docs/09-api/openapi.yaml
  system-tests:     # full decision cycle tests
  container-scan:   # trivy CRITICAL/HIGH scan
```

### Frontend Workflow (`.github/workflows/ci-frontend.yml`)

```yaml
on:
  push:
    branches: [main]
    paths: ["frontend/**", ".github/workflows/ci-frontend.yml"]
  pull_request:
    branches: [main]
    paths: ["frontend/**", ".github/workflows/ci-frontend.yml"]

jobs:
  guard:            # skip if frontend/package.json missing
  lint:            # eslint biome
  typecheck:        # tsc --noEmit
  test:            # vitest suite
  build:           # vite production build
  lighthouse:      # performance audit
```

### Deploy Workflow (`.github/workflows/deploy.yml`)

```yaml
on:
  push:
    branches: [main]
  workflow_dispatch:

jobs:
  check-secrets:    # validate DEPLOY_HOST DEPLOY_USER DEPLOY_SSH_KEY exist
  deploy:           # conditional on check-secrets output configured=true
    steps:
      - checkout
      - setup_ssh_key (from GITHUB_SECRETS)
      - make_deploy_scripts_executable
      - run_deploy_site_script
```

**Deployment Steps:**

1. Checkout repository at `main` branch SHA
2. Write SSH deploy key to runner workspace
3. Execute `deploy-site.sh` via SSH connection
4. Build frontend locally or use artifact from ci-frontend workflow
5. SCP build artifacts to VPS (`/tmp/lumine-dist/`)
6. In-place copy to `/var/www/lumine` (preserves bind mount inode)
7. Health check via `curl 127.0.0.1:8080/`
8. Cleanup SSH key from runner

**GitHub Secrets Required:**

| Secret | Purpose |
|---|---|
| `DEPLOY_HOST` | VPS hostname/IP |
| `DEPLOY_USER` | SSH username |
| `DEPLOY_SSH_KEY` | ED25519 private key in PEM format |
| `STAGING_HOST` | Staging server host (future) |
| `STAGING_USER` | Staging SSH user (future) |
| `STAGING_SSH_KEY` | Staging deploy key (future) |
| `PRODUCTION_HOST` | Production host (future) |
| `PRODUCTION_USER` | Production SSH user (future) |
| `PRODUCTION_SSH_KEY` | Production deploy key (future) |
| `GHCR_TOKEN` | GitHub Container Registry token (for future Docker image pushes) |

**Security Notes:**

- Deploy SSH key has `command=` restriction to prevent privilege escalation
- SSH agent forwarding is disabled; deploy key extracted directly
- Secrets never stored in logs, artifacts, or workspace after job completes
- Images tagged with git SHA (immutable) + latest pointer

---

## Git Security Practices

### What NOT to Commit

❌ `.env`, `.env.*`, `*.env.enc`  
❌ `id_rsa`, `id_ed25519` (private keys)  
❌ `secrets.env`, `credentials.yml.enc`  
❌ `*.pem`, `*.key` files  
❌ Database dumps with plaintext passwords  
❌ Backup archives without encryption indicator  

### What SHOULD Be Committed

✅ `.env.sample` (template only)  
✅ `id_rsa.pub` (public keys only — document separately)  
✅ Dockerfiles, compose files (without secrets interpolation)  
✅ Documentation and deployment scripts  
✅ Automated test fixtures (sanitized data)  

### Git Ignore Checklist

```gitignore
.env
*.env.enc
secrets.env
*.pem
*.key
id_rsa
*.db
backup_*.tar.gz
state-exports/
```

---

## Troubleshooting

### SSH Connection Issues

```bash
# Test key authentication manually
ssh -v -i id_rsa root@166.88.227.177

# Check authorized_keys on VPS (requires prior access)
cat ~/.ssh/authorized_keys

# Regenerate key pair if needed
ssh-keygen -t ed25519 -f ~/lumine_deploy -C "lumine-ci-deploy"
ssh-copy-id -i ~/lumine_deploy.pub root@166.88.227.177
```

### Docker Not Running After Deploy

```bash
# SSH to VPS
ssh root@166.88.227.177
cd /opt/lumine/backend

# Check Docker service status
sudo systemctl status docker

# View failed container logs
docker compose -f docker-compose.prod.yml logs --tail 100 api
docker compose -f docker-compose.prod.yml logs --tail 100 postgres
docker compose -f docker-compose.prod.yml logs --tail 100 mt5

# Restart specific service
docker compose -f docker-compose.prod.yml restart api
```

### Health Check Failing

```bash
# Manual health check on VPS
curl http://localhost:8000/health

# Check container health status
docker inspect --format='{{.State.Health.Status}}' api

# Verify database connectivity
docker exec -it lumines-postgres pg_isready -U lumine -d lumine
```

### Migration Errors

```bash
# Run migrations explicitly (safe rollback available)
docker compose -f docker-compose.prod.yml run --rm api alembic upgrade head

# Check migration history
docker compose -f docker-compose.prod.yml run --rm api alembic history

# Rollback last migration if needed
docker compose -f docker-compose.prod.yml run --rm api alembic downgrade -1
```

---

## Next Steps

1. **Verify VPS accessibility:** Run `./deploy-site.sh` with local `.env` populated
2. **Review control-plane Caddyfile:** `infrastructure/control-plane/caddy/Caddyfile`
3. **Configure Authelia:** `infrastructure/control-plane/authelia/configuration.yml`
4. **Test 9router gateway:** Confirm external AI agents can reach port :20128
5. **Validate backup script:** Run `/opt/lumine/backup.sh` via cron
6. **Document recovery procedures:** Add DR checklist to `docs/11-infrastructure/backup-dr.md`

---

**Questions?** See also:

- [`docs/11-infrastructure/topology.md`](docs/11-infrastructure/topology.md) — runtime architecture
- [`docs/11-infrastructure/build-deploy.md`](docs/11-infrastructure/build-deploy.md) — pipeline mechanics
- [`docs/adr/0047-cicd-github-actions-ghcr-ssh-deploy.md`](docs/adr/0047-cicd-github-actions-ghcr-ssh-deploy.md) — CI/CD decisions
- [`scripts/deploy/VPS-GUIDE.md`](scripts/deploy/VPS-GUIDE.md) — detailed VPS installation guide
