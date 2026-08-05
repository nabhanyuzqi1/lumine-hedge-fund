# Security Standards

- **Status:** active
- **Owner:** architects
- **Last-reviewed:** 2026-08-02
- **Review-cadence:** 90
- **Source:** promoted from `docs/12-security/`

## Threat model
- V1 scope per ADR-0001: network-layer access, replay, brute force, credential
  exposure, dependency compromise, SSH brute force.
- Prompt injection explicitly IN scope (ADR-0018) — application-layer via data ingestion.
- Out of scope V1: insider, physical, compliance, multi-tenant, DDoS.

## Secrets management (`docs/12-security/secrets-management.md`)
- `.env*` gitignored (except `.env.example`). Never commit secrets.
- Loading order: env → `.env` (dev) → secrets manager (prod).
- Rotation runbook per secret class; rotation is a tested operation.
- Per-env matrix: dev / staging / prod with isolated credentials.

## Encryption
- At rest: Postgres TDE / disk encryption; S3 SSE; reasoning traces encrypted
  (may contain position data).
- In transit: TLS 1.3 everywhere; no TLS 1.1/1.2.

## SSH (ADR-0002)
- ed25519-only; 2 keys (CI deploy + admin); password auth disabled; root disabled.

## Network / firewall
- Per `docs/12-security/network-firewall.md`. Least-egress; deny by default.

## Supply chain
- `pip-audit`, `osv-scanner`, `gitleaks`, SBOM in CI
  (`.github/workflows/supply-chain.yml`).
- No unpinned dependencies in production. `uv.lock` is the source of truth.

## Audit tamper-evidence (ADR-0017)
- Journal is hash-chained; anchored to WORM (S3 Object Lock Compliance).
- App role has INSERT-only on append-only tables.
- Daily chain-verification job; failure pages.

## Prompt injection defense (ADR-0018)
- News = untrusted input; structured extraction; instruction hierarchy;
  output validation; source allow-listing; red-team eval suite.

## Incident response
- See `94-runbooks/incident-response.md`.
- Security incidents follow `SECURITY.md` disclosure policy.
