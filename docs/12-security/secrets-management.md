# Secrets Management

- **Status:** active
- **Owner:** architects / devops
- **Last-reviewed:** 2026-08-02
- **Review-cadence:** 90

## Loading order (precedence high → low)
1. Process environment (production runtime).
2. Secrets manager (prod: cloud secrets manager / Phase 11).
3. `.env` file (dev only; gitignored).
4. Defaults: none. No secret ever has a default value.

A secret missing at load time is a **fatal startup error**. The process
exits; it never runs with a placeholder.

## Per-environment matrix
| Env | Secrets source | Isolation |
|-----|-----------------|-----------|
| dev | `.env` (gitignored), `.env.example` committed | local |
| staging | secrets manager, separate credentials | separate account/namespace |
| prod | secrets manager, separate credentials, CIO-gated rotation | separate account |

Credentials are **never shared** across environments.

## Secret classes & rotation
| Class | Example | Rotation cadence | Rotation runbook |
|-------|---------|-------------------|------------------|
| LLM provider keys | 9router / provider API keys | 90 days | rotate in secrets manager → redeploy |
| DB credentials | Postgres app/audit roles | 90 days | rotate → update app config → redeploy |
| Broker credentials | MT5 login | per broker policy | coordinate with broker |
| SSH keys (ADR-0002) | CI deploy + admin | 180 days | `docs/12-security/ssh-access.md` |
| HMAC signing keys | API request signing | 90 days | rotate → parallel-accept old+new → drop old |
| WORM anchor creds | S3 Object Lock | 90 days | rotate access keys |

Rotation is a **tested operation** — every class has a runbook and is
drilled at least once before it's needed in anger.

## `.env.example`
- Committed for both workspaces: `backend/.env.example`, `frontend/.env.example`.
- Contains only keys + a placeholder (`<set-in-secrets-manager>`), never real values.
- CI `gitleaks` scans for committed secrets (`supply-chain.yml`).

## Config module contract
`backend/src/lumine/shared/config.py` is the single loader. It:
- Reads in the order above.
- Validates required keys at startup (fail fast).
- Exposes typed accessors; no `os.environ` reads elsewhere in the codebase.
- Records a redacted config fingerprint in the startup log (keys present,
  values never).

## Phase boundary
This fixes the secrets contract. Physical secret storage is Phase 11
infrastructure; the loading contract is consumed by Phase 14 code.
