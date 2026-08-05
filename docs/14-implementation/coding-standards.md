# Coding Standards

## Overview

Python and TypeScript coding standards with tool-level enforcement.
All linting, formatting, and type-checking rules are enforced in CI
as blocking gates. Review-level rules are enforced by the operator
during code review.

## Python standards

### Toolchain

| Tool | Purpose | Enforcement |
|------|---------|-------------|
| `ruff` | Linting + formatting | CI blocking |
| `mypy` | Static type checking (strict) | CI blocking |
| `pytest` | Testing | CI blocking |
| `pytest-cov` | Coverage reporting | CI advisory |

### `ruff` configuration

```toml
# backend/pyproject.toml

[tool.ruff]
line-length = 100
target-version = "py312"

[tool.ruff.lint]
select = ["ALL"]
ignore = [
    "D203",   # no-blank-line-before-class (conflicts with D211)
    "D213",   # multi-line-summary-second-line (prefer D212)
    "ANN101", # missing-type-self (too noisy)
    "S101",   # assert (needed for tests)
    "PLR0913", # too-many-arguments (acceptable with clear signatures)
    "PLR0912", # too-many-branches (acceptable in complex validators)
    "PLR0915", # too-many-statements (acceptable in decision engine)
]

[tool.ruff.lint.per-file-ignores]
"tests/**/*" = [
    "S101",   # assert
    "PLR2004", # magic-value-comparison
    "D100",   # missing-module-docstring
    "D103",   # missing-function-docstring
    "D104",   # missing-package-docstring
]
"src/lumine/autogen_pipeline/**/*" = [
    "ANN001", # missing-type-function-argument
    "ANN201", # missing-return-type
]

[tool.ruff.format]
quote-style = "double"
indent-style = "space"
```

### `mypy` configuration

```toml
# backend/pyproject.toml

[tool.mypy]
strict = true
python_version = "3.12"

# AutoGen types are dynamic — strict mode causes false positives
exclude = ["src/lumine/autogen_pipeline/"]

# Third-party packages without type stubs
[[tool.mypy.overrides]]
module = [
    "autogen_agentchat.*",
    "autogen_ext.*",
    "redis.*",
]
ignore_missing_imports = true
```

### Naming

| Element | Convention | Example |
|---------|------------|---------|
| Module file | `snake_case` | `risk_validator.py` |
| Package | `snake_case` | `trade_core/` |
| Class | `PascalCase` | `RiskValidator` |
| Function/method | `snake_case` | `check_exposure()` |
| Variable | `snake_case` | `max_position_size` |
| Constant | `UPPER_CASE` | `MAX_EXPOSURE_PCT` |
| Private member | `_leading_underscore` | `_validate_threshold()` |
| Type variable | `PascalCase` | `OrderState` |

### Imports

```python
# 1. Standard library
import asyncio
from datetime import datetime, timezone

# 2. Third-party
import structlog
from pydantic import BaseModel
from sqlalchemy import select

# 3. Internal
from lumine.trade_core.risk_validator import RiskValidator
from lumine.shared.errors import ValidationError
from lumine.data.models import LineageRecord
```

- No `import *` — always explicit.
- No relative imports across package boundaries — use absolute imports
  from the `lumine` package root.
- Relative imports permitted within the same package (`from .helpers import ...`).

### Docstrings

Google-style for public API (functions and classes exported from a
module's `__all__`). Internal helpers use inline comments only.

```python
def check_exposure(
    proposal: Proposal,
    current_exposure: float,
    max_exposure_pct: float = 0.02,
) -> RiskDecision:
    """Validate a proposal against position exposure limits.

    Args:
        proposal: The CIO proposal to validate.
        current_exposure: Current total exposure as fraction of equity.
        max_exposure_pct: Maximum allowed exposure as fraction of equity.

    Returns:
        RiskDecision with verdict and reason.

    Raises:
        ValidationError: If proposal is missing required fields.
    """
    ...
```

### Error handling

Custom exception hierarchy in `shared/errors.py`:

```python
class LumineError(Exception):
    """Base exception for all Lumine errors."""

class ValidationError(LumineError):
    """Input validation failure — invalid data, missing fields."""

class ConfigurationError(LumineError):
    """System configuration error — missing env var, invalid setting."""

class LineageWriteError(LumineError):
    """Lineage record write failure — database unavailable."""

class ExecutionError(LumineError):
    """Order execution failure — MT5 rejected, network error."""

class KillSwitchActiveError(LumineError):
    """Operation blocked by active kill-switch."""

class BudgetExceededError(LumineError):
    """LLM budget exceeded — circuit breaker tripped."""
```

Rules:
- No bare `except:` — always catch specific exception types.
- No `except Exception:` in production code — catch specific subtypes.
- Always include context in re-raised exceptions (`raise ... from e`).
- Log at the boundary (API handler, workflow entry point), not at every
  internal call site.

### Logging

```python
import structlog

logger = structlog.get_logger(__name__)

# Usage
logger.info("decision_cycle_started", symbol="XAUUSD", trigger="schedule")
logger.warning("exposure_limit_breached", current=0.025, max=0.02)
logger.error("lineage_write_failed", lineage_id=str(lineage_id), error=str(e))
```

- `structlog` with JSON renderer in production, console renderer in dev.
- `trace_id` bound to every log line via middleware context.
- No `print()` in production code.

### Configuration

```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Database
    database_url: str = "postgresql+asyncpg://lumine:lumine@localhost:5432/lumine"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # LLM
    llm_gateway_url: str = "http://localhost:8081"
    llm_daily_budget_usd: float = 50.0

    # MT5
    mt5_connect_mode: str = "paper"

    # Feature flags
    lumine_feature_debate: bool = False
    lumine_feature_backtest: bool = False

    model_config = {"env_prefix": "LUMINE_", "case_sensitive": False}


settings = Settings()
```

## TypeScript standards

### Toolchain

| Tool | Purpose | Enforcement |
|------|---------|-------------|
| `biome` | Linting + formatting | CI blocking |
| `tsc --noEmit` | Static type checking | CI blocking |
| `vitest` | Testing | CI blocking |

### `biome.json`

```json
{
  "$schema": "https://biomejs.dev/schemas/1.9.4/schema.json",
  "organizeImports": { "enabled": true },
  "linter": {
    "enabled": true,
    "rules": {
      "recommended": true
    }
  },
  "formatter": {
    "enabled": true,
    "indentStyle": "space",
    "indentWidth": 2,
    "lineWidth": 100
  },
  "javascript": {
    "formatter": {
      "quoteStyle": "single",
      "trailingCommas": "all",
      "semicolons": "always"
    }
  }
}
```

### `tsconfig.json`

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "lib": ["ES2022", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "moduleResolution": "bundler",
    "jsx": "react-jsx",
    "strict": true,
    "noUncheckedIndexedAccess": true,
    "noEmit": true,
    "isolatedModules": true,
    "skipLibCheck": true,
    "paths": {
      "@/*": ["./src/*"]
    }
  },
  "include": ["src"]
}
```

### Naming

| Element | Convention | Example |
|---------|------------|---------|
| Module file | `camelCase` | `useMarketStream.ts` |
| Component file | `PascalCase` | `PriceChart.tsx` |
| Component | `PascalCase` | `function PriceChart()` |
| Hook | `use` prefix, camelCase | `useStream()` |
| Store | `Store` suffix, camelCase | `marketStore.ts` |
| Variable/function | `camelCase` | `currentPrice` |
| Constant | `UPPER_CASE` | `MAX_RECONNECT_DELAY` |
| Type/interface | `PascalCase` | `OrderFill` |
| Test file | `.test.ts` suffix | `Button.test.tsx` |

### Exports

**Named exports only.** No `export default`.

```typescript
// Correct
export function PriceChart({ symbol }: PriceChartProps) { ... }
export type { PriceChartProps };

// Incorrect
export default function PriceChart({ symbol }: PriceChartProps) { ... }
```

Rationale:
- Default exports break IDE auto-import.
- Default exports allow the importing file to rename arbitrarily,
  making refactoring fragile.
- Named exports are grep-friendly.

### Components

```typescript
// Functional component with explicit Props type
interface PriceChartProps {
  symbol: string;
  timeframe: Timeframe;
  onCrosshairMove?: (price: number) => void;
}

export function PriceChart({ symbol, timeframe, onCrosshairMove }: PriceChartProps) {
  // ...
}
```

- Functional components only — no class components.
- Props type always exported (may be needed by parent).
- Callback props use `on` prefix.
- No inline styles for layout — use CSS Modules or Tailwind utilities.

### State management

```typescript
// Zustand store per SSE stream (D10-3)
import { create } from 'zustand';

interface MarketState {
  lastTick: Tick | null;
  tickHistory: Tick[];
  updateTick: (tick: Tick) => void;
}

export const useMarketStore = create<MarketState>((set) => ({
  lastTick: null,
  tickHistory: [],
  updateTick: (tick) =>
    set((state) => ({
      lastTick: tick,
      tickHistory: [...state.tickHistory.slice(-999), tick],
    })),
}));
```

- TanStack Query for all REST data fetching.
- Zustand stores for SSE stream state.
- No prop drilling past 2 levels — compose with hooks.

### Error handling

```typescript
// API client returns discriminated union
type ApiResult<T> =
  | { ok: true; data: T }
  | { ok: false; error: ApiError };

interface ApiError {
  code: string;
  message: string;
  traceId: string;
}
```

- API calls return `ApiResult<T>` — never throw from the API layer.
- Components handle both `ok` and error states explicitly.
- `trace_id` from Phase 9 error envelope is surfaced in the ActivityLog.

## Git conventions

### Branch naming

```
feat/<slug>       # Feature work
fix/<slug>        # Bug fix
docs/<slug>       # Documentation only
refactor/<slug>   # Code restructuring, no behavior change
test/<slug>       # Test additions or fixes
chore/<slug>      # Tooling, dependencies, configuration
ci/<slug>         # CI/CD pipeline changes
```

### Commit format

```
<type>: <description>

[optional body]

[optional footer]
```

Examples:
```
feat: add ATR-based trailing stop to execution router
fix: prevent duplicate order dispatch on Redis reconnect
docs: update Phase 14 sprint plan with Sprint 3 details
refactor: extract HMAC verifier to shared security module
```

### Pull requests

- Required for all changes to main.
- Author cannot merge own PR without review.
- Squash merge — one commit per PR.
- PR title becomes the squash commit message.
- CI must pass before merge.

### Feature flags

```python
# Backend
if settings.lumine_feature_debate:
    await debate_round.run(analyst_outputs)

# Frontend
if (import.meta.env.VITE_FEATURE_BACKTEST) {
  return <BacktestPanel />;
}
```

- `LUMINE_FEATURE_<NAME>` for backend.
- `VITE_FEATURE_<NAME>` for frontend (Vite-exposed env vars).
- Feature flags are removed when the feature is complete and stable.
- No feature flag should live longer than one sprint after completion.

## Dockerfile standards

```dockerfile
# Multi-stage build
FROM python:3.12-slim@sha256:<digest> AS builder
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN --mount=from=ghcr.io/astral-sh/uv,source=/uv,target=/usr/local/bin/uv \
    uv sync --frozen --no-dev --no-install-project

FROM python:3.12-slim@sha256:<digest> AS runner
RUN useradd --create-home --shell /bin/bash lumine
USER lumine
WORKDIR /app
COPY --from=builder /app/.venv .venv
COPY src/ src/
COPY alembic/ alembic/
ENV PATH="/app/.venv/bin:$PATH"
EXPOSE 8000
CMD ["uvicorn", "lumine.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
```

- Multi-stage: builder compiles, runner executes.
- SHA-pinned base images (Phase 12 D12-5).
- Non-root user (`lumine`).
- No secrets in image layers — use environment variables.

## What this document does NOT define

- Concrete `pyproject.toml` or `package.json` with version-pinned
  dependencies (Phase 15 — lockfiles are the source of truth).
- `ruff` rule justifications beyond the ignore list (Phase 15).
- `mypy` override justification per module (Phase 15).
- Vitest configuration and test setup (Phase 15).

## Phase boundary

Coding standards are fixed. Tool configuration files, lockfiles, and
concrete enforcement are implemented in Phase 15 Sprint 1.