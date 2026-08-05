# Engineering Standards

- **Status:** active
- **Owner:** architects
- **Last-reviewed:** 2026-08-02
- **Review-cadence:** 180

Permanent cross-cutting standards. Promoted from phase docs so they live in
one place rather than scattered. Phase docs remain the design source; these
are the operating standards.

- [`coding-standards.md`](coding-standards.md) — Python (ruff), TypeScript (eslint/prettier), SQL conventions.
- [`api-standards.md`](api-standards.md) — REST/SSE conventions, versioning, error contract, OpenAPI.
- [`db-standards.md`](db-standards.md) — naming, migrations, partitioning, index, retention.
- [`prompt-standards.md`](prompt-standards.md) — prompt file format, versioning, hashing, eval binding.
- [`security-standards.md`](security-standards.md) — secrets, encryption, SSH, supply chain, audit.

Standards differ from phase docs: a phase doc says *what we designed for
this phase*; a standard says *how we do things across all phases*.
