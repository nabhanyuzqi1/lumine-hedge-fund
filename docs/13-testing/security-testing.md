# Security Testing

## Overview

Security testing architecture per D13-5. Three layers: automated CI
scans (every push), config audit (staging + monthly cron), and manual
penetration test (pre-launch + quarterly). Phase 12 defines what is
secured; Phase 13 defines how it is tested.

## Layer 1 — Automated CI scans

Run on every push. All stages execute in parallel with unit, integration,
contract, and system tests. Total wall-clock time: < 5 minutes.

### SAST (Static Application Security Testing)

**Bandit (Python AST analysis):**

| Rule category | Examples |
|---------------|----------|
| SQL injection | String formatting in SQL queries, bare `execute()` calls |
| Code execution | `exec()`, `eval()`, `subprocess` with shell=True |
| Hardcoded secrets | Password, API key, token strings in source |
| Weak cryptography | MD5, SHA1, DES, insufficient key lengths |
| File operations | World-writable files, unsafe tempfile usage |
| Network | Unverified SSL contexts, socket binding |

Gate: **high severity → block merge.** Medium/low → annotation.

**Semgrep (multi-language):**

| Rule set | Coverage |
|----------|----------|
| OWASP Top 10 | Injection, broken auth, sensitive data exposure, XXE, broken access control, security misconfig, XSS, insecure deserialization, vulnerable components, insufficient logging |
| Custom Lumine rules | `.env` file access patterns, HMAC key handling, scope check bypass, lineage write bypass |

Gate: **error severity → block merge.** Warning → annotation.

### Secret scanning

**Gitleaks:**
- Scans all commits, working tree, and staged files.
- Entropy-based detection + regex patterns (AWS keys, GitHub tokens,
  private keys, API keys, database URLs with credentials).
- Exception: `.env.enc` (SOPS encrypted — intentional, not a leak).

Gate: **any finding → block merge + alert operator.**

### Dependency audit

Per Phase 12 D12-5. Already defined in `docs/12-security/supply-chain.md`.
Phase 13 integrates it into the testing gate matrix.

| Tool | Scope | Gate |
|------|-------|------|
| `pip-audit` | Python dependencies | Critical/high → block |
| `npm audit` | Frontend dependencies | Critical/high → block |

### Container scanning

**Trivy:**
- Filesystem scan of built Docker images.
- Detects: OS package vulnerabilities, application library CVEs,
  misconfigurations (root user, privileged mode, exposed ports).

Gate: **critical → block, high → block.**

### CI gate enforcement matrix (security)

| Scan | Tool | Severity to block | Runtime |
|------|------|-------------------|---------|
| Python SAST | Bandit | High | < 30s |
| Multi-language SAST | Semgrep | Error | < 60s |
| Secret scanning | Gitleaks | Any | < 30s |
| Python deps | pip-audit | Critical, High | < 30s |
| Frontend deps | npm audit | Critical, High | < 30s |
| Container scan | Trivy | Critical, High | < 3m |

## Layer 2 — Config audit

### Staging deploy validation

Runs automatically on every staging deploy:

| Check | Method | Gate |
|-------|--------|------|
| Caddy config syntax | `caddy validate --config Caddyfile` | Syntax error → block deploy |
| Caddy TLS | `curl -v https://staging.lumine.internal` | TLS < 1.2 → block |
| Caddy CORS header | `curl -I -H "Origin: https://evil.com"` | Allow-Origin not wildcard |
| Docker daemon config | Check `daemon.json` for `iptables: false`, `userland-proxy: false` | Mismatch → block |
| No privileged ports exposed | `docker compose ps` | Extra ports → block |

### Monthly cron audit

Runs on the first day of each month:

| Check | Method | Alert on failure |
|-------|--------|-----------------|
| UFW rules match spec | `ufw status verbose` vs expected rules | Critical |
| SSH config matches spec | `sshd -T` vs expected config (D12-2) | Critical |
| No unauthorized SSH keys | Parse `~/.ssh/authorized_keys` | Critical |
| Backup encryption active | Verify rclone remote uses `crypt` | Critical |
| Disk encryption active | `lsblk -f` shows LUKS | Critical |

## Layer 3 — Manual penetration test

### Methodology

**Type:** Grey-box. Tester has access to:
- API documentation (Phase 9 REST + SSE contracts).
- Network diagram and security boundaries (Phase 12).
- No source code access.

**Duration:** 3 days.

**Frequency:** Pre-launch (mandatory) + quarterly thereafter.

### Scope

#### Phase 1: Reconnaissance (day 1)

| Test | Method | Expected result |
|------|--------|-----------------|
| Port scan | `nmap -p- <VPS_IP>` | Only 80, 443, 22 open |
| DNS enumeration | `dig`, `host`, subdomain brute force | Only production domain resolves |
| CORS probing | `curl -H "Origin: https://preview.vercel.app"` | 403 or CORS header missing |
| SSH fingerprint | `ssh-keyscan` | ed25519 key only |
| TLS audit | `testssl.sh` | TLS ≥ 1.2, no weak ciphers |
| HTTP headers | `curl -I` | HSTS, CSP, no server version leak |

#### Phase 2: API attack surface (day 1–2)

| Attack | Method | Expected result |
|--------|--------|-----------------|
| Replay attack | Capture signed request, resend | 401 (timestamp expired or nonce reused) |
| Brute force | Rapid auth attempts from single IP | Rate limited; alert fired |
| Scope escalation | `read:market` key → `write:orders` endpoint | 403 INSUFFICIENT_SCOPE |
| Malformed JSON | Oversized body, nested objects, SQL injection | 400/422; no crash |
| Timestamp manipulation | Expired timestamp, future timestamp, missing | 401 |
| HMAC manipulation | Tampered signature, wrong key ID, missing header | 401 |
| SSE hijack | Connect without auth; subscribe to unauthorized stream | 401/403 |
| Method enumeration | POST to GET-only; OPTIONS; DELETE on readonly | 405 |
| Path traversal | `/api/v1/../../../etc/passwd` | 404 |
| Header injection | `X-Forwarded-For`, `X-Real-IP` manipulation | No effect on auth |

#### Phase 3: Infrastructure (day 2)

| Test | Method | Expected result |
|------|--------|-----------------|
| Grafana access | Try from non-allowlisted IP | 403 |
| Docker socket | Try `docker -H tcp://<VPS>:2375 ps` | Connection refused |
| PostgreSQL direct | Try `psql -h <VPS> -p 5432` | Connection refused |
| Redis direct | Try `redis-cli -h <VPS> -p 6379` | Connection refused |
| SSH brute force | Rapid key attempts | Rate limited (ufw limit 22) |
| Container escape | If access gained, try to read host filesystem | Non-root user; no host mounts |

#### Phase 4: Supply chain (day 2)

| Review | Method | Expected result |
|--------|--------|-----------------|
| CI pipeline logs | Check for secrets in build output | No secrets in logs |
| GHCR images | Check production compose for SHA tags | SHA-pinned, not `latest` |
| Dependabot | Check for unresolved critical/high alerts | None open |
| Repository | Check for `.env` plaintext in history | None found |

#### Phase 5: Report (day 3)

**Classification:**

| Severity | Definition | Action |
|----------|------------|--------|
| Critical | Remote code execution, auth bypass, data exfiltration | Fix immediately |
| High | Scope escalation, information disclosure, denial of service | Fix before launch |
| Medium | Defense-in-depth gaps, best practice deviations | Fix before next release |
| Low | Informational, hardening suggestions | Acknowledge; fix at discretion |
| Info | Observations, no security impact | Documented |

**Acceptance criteria:** No Critical or High findings open at launch.

### Quarterly pentest

After launch, the penetration test is repeated quarterly. Focus areas
rotate:

| Quarter | Focus |
|---------|-------|
| Q1 | API and auth surface (any new endpoints, scope changes) |
| Q2 | Infrastructure and network (any config changes, new services) |
| Q3 | Supply chain and dependencies (new libraries, base image updates) |
| Q4 | Full scope (all areas) |

Each quarterly pentest is a 1-day engagement (reduced scope per quarter).

## Pre-commit hooks

```yaml
# .pre-commit-config.yaml (Phase 14+)
repos:
  - repo: https://github.com/gitleaks/gitleaks
    rev: v8
    hooks:
      - id: gitleaks
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.x
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format
  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.x
    hooks:
      - id: mypy
        args: [--strict]
```

Gitleaks blocks secrets before they enter git history. Ruff and mypy
are quality gates (not security per se, but catch logic errors that
could become vulnerabilities).

## What this document does NOT define

- Concrete CI workflow YAML for security jobs (Phase 14+).
- Semgrep custom rule implementations (Phase 14+).
- Bandit configuration and baseline (Phase 14+).
- Trivy configuration and ignore policy (Phase 14+).
- Monthly cron audit script implementation (Phase 14+).
- Penetration test execution checklist and reporting template
  (Phase 14+ operations runbook).
- Bug bounty program — not in V1 scope.

## Phase boundary

Security testing architecture, tools, gate policies, audit schedule,
and pentest methodology are fixed here. Implementation and configuration
belong to Phase 14+.