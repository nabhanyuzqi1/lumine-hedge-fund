# GitHub Actions Secrets — Setup Guide

Untuk CI/CD auto-deploy ke VPS, tambahkan secrets berikut di GitHub:

**URL:** `https://github.com/nabhanyuzqi1/lumine-hedge-fund/settings/secrets/actions`

## Required Secrets

| Secret Name | Value | Keterangan |
|-------------|-------|------------|
| `VPS_HOST` | `166.88.227.177` | IP VPS |
| `VPS_SSH_KEY` | (private key) | Isi dengan isi file `~/.ssh/lumine/id_rsa_lumine` |

## Cara Setup

### 1. `VPS_HOST`
1. Buka GitHub repo Settings → Secrets and variables → Actions
2. New repository secret
3. Name: `VPS_HOST`
4. Value: `166.88.227.177`

### 2. `VPS_SSH_KEY`
1. Buka terminal lokal
2. Jalankan: `cat ~/.ssh/lumine/id_rsa_lumine`
3. Copy seluruh output (termasuk `-----BEGIN ... KEY-----` dan `-----END ... KEY-----`)
4. New repository secret → Name: `VPS_SSH_KEY` → paste value

## CI/CD Flow (setelah secrets diset)

```
push ke dev →
  backend-test (pytest contract+unit) →
  backend-lint (ruff + bandit) →
  frontend-test (tsc + vitest + vite build) →
  deploy (SSH ke VPS, rebuild api+frontend, health check)
```

Deploy hanya berjalan pada `push` ke branch `dev` (bukan PR).

## Environment (GitHub Environments)

CI/CD menggunakan `environment: production` — buat di:
`Settings → Environments → New environment → production`

Opsional: tambah required reviewers untuk protection rules.
