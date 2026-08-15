# Lumine Hedge Fund — Complete Phase 16 Plan & Gap Analysis

**Date:** 2026-08-15
**Status:** Zero-Demo Complete, Phase 16 Ready, AutoGen Studio Integration Pending
**Git Branch:** `dev` (synced local ↔ VPS ↔ GitHub)

---

## Executive Summary

Lumine telah mencapai milestone **ZERO-DEMO** — semua data fiktif dihapus, sistem berjalan dengan data real dari MT5 dan PostgreSQL. Fokus sekarang: (1) Selesaikan gap Phase 16 yang tersisa, (2) Integrate AutoGen Studio untuk visual agent management, (3) Sinkronisasi penuh VPS ↔ Repo.

---

## Part 1: Current System Status (2026-08-15)

### A. VPS Services (Live & Healthy)

```
✅ backend-api-1         (healthy, port 8000)
✅ backend-frontend-1    (healthy, port 80)
✅ lumine-mt5            (healthy, EA bridge active)
✅ backend-caddy-1       (healthy, ports 80/443)
✅ backend-postgres-1    (healthy, port 5432)
✅ backend-redis-1       (healthy, port 6379)
✅ 9router               (healthy, port 20128 — LLM gateway)
✅ headroom              (healthy, port 8787 — resource monitor)
✅ backend-dozzle-1      (healthy, port 8080 — log viewer)
✅ backend-mt5-bridge-1  (healthy, port 8000)
✅ backend-redis-http-proxy-1 (port 8765)
```

### B. Database State (Real Data, Zero Demo)

| Table | Count | Status |
|-------|-------|--------|
| `bars_1m` | 4,001 bars | ✅ Real MT5 data (3 days) |
| `bars_1h` | 5,000 bars | ✅ Real MT5 data (10 months) |
| `bars_1d` | 2,283 bars | ✅ Real MT5 data (9 years) |
| `orders` | 19 total (5 filled, 14 pending) | ✅ Real MT5 executions |
| `positions` | 0 | ❌ **GAP** — Need backfill from filled orders |
| `lineage_records` | 5 | ✅ Committee decisions recorded |

### C. Git Sync Status

- **Local Repo:** `dev` branch, clean (commits pushed)
- **VPS `/opt/lumine`:** `dev` branch, 5 untracked files (backup scripts, watchdogs)
- **GitHub:** `dev` branch, all commits synced

**Recent Commits (Aug 2026):**
- Zero-demo + market calendar (holiday pause)
- SSE payload fix + tick_worker
- Journal/lineage DB-backed
- MT5 EA bridge E2E fixes
- Security audit (HSTS, headers)

---

## Part 2: Completed Work (Sprint Evidence)

### Sprint 7 — Audit & Hardening ✅ COMPLETE

| Component | Status | Evidence |
|-----------|--------|----------|
| Hash chain verifier | ✅ | `backend/src/lumine/security/verifier.py` |
| TCA calculation | ✅ | `backend/src/lumine/trade_core/tca.py` (193 lines) |
| Prompt registry | ✅ | `prompts/registry.py` (250 lines, hash validation) |
| Database migrations | ✅ | `0009_add_tca_and_accounts.py` |
| Unit tests | ✅ | 18 tests passing |
| Integration tests | ✅ | 4 tests passing |

**File:** `docs/15-implementation/sprint-evidence/sprint-7-audit-hardening-complete.md`

### Frontend Sprints 1-6 ✅ COMPLETE

| Sprint | Deliverable | Status |
|--------|-------------|--------|
| F-Sprint-1 | Scaffold & routing | ✅ 10 routes implemented |
| F-Sprint-2 | Design system primitives | ✅ 8 components complete |
| F-Sprint-3 | Realtime data layer (SSE) | ✅ useSSE + Zustand |
| F-Sprint-4 | Charts (candlestick, equity, etc.) | ✅ 7 chart types |
| F-Sprint-5 | Surfaces (positions, orders, risk) | ✅ Tables + dialogs |
| F-Sprint-6 | A11y & performance | ✅ Virtualization, lazy load |

**Files:** `docs/15-implementation/sprint-evidence/f-sprint-*.md`

### Zero-Demo Implementation ✅ COMPLETE (Aug 15, 2026)

| Component | Before | After |
|-----------|--------|-------|
| `/api/v1/portfolio/summary` | NAV 100,000 (fictive) | NAV 0 (real positions) |
| `/api/v1/market/ohlcv` | Random walk bars | [] (DB-backed) |
| `/api/v1/market/quote` | Synthetic ticks | Live MarketService |
| `/api/v1/market/signals` | 3 fake signals | [] (pipeline pending) |
| `/api/v1/portfolio/simulate` | Fictive NAV | Real NAV + live price |
| Contract tests | Demo fixtures | Mock DB/session fixtures |

**Commit:** `b8b16e7` (feat: zero-demo + market calendar)

---

## Part 3: Gap Analysis — Phase 16 Remaining

### A. Backend Gaps

| Gap ID | Component | Status | Priority | Effort |
|--------|-----------|--------|----------|--------|
| **B-16-01** | Positions backfill from orders | ❌ | HIGH | 2h |
| **B-16-02** | Strategy executor (lineage → positions) | ❌ | HIGH | 8h |
| **B-16-03** | P&L calculation (positions + market price) | ❌ | HIGH | 4h |
| **B-16-04** | Feature/Signal polling endpoints | ❌ | MEDIUM | 4h |
| **B-16-05** | AutoGen Studio integration | ❌ | MEDIUM | 6h |
| **B-16-06** | Kill-switch UI confirm modal | ⚠️ Partial | MEDIUM | 2h |
| **B-16-07** | Stream per-status dot + gap banner | ❌ | LOW | 3h |

### B. Frontend Gaps

| Gap ID | Component | Status | Priority | Effort |
|--------|-----------|--------|----------|--------|
| **F-16-01** | Fixture → API rewiring (all pages) | ⚠️ Partial | HIGH | 6h |
| **F-16-02** | FeaturePanel (polling features endpoint) | ❌ | MEDIUM | 3h |
| **F-16-03** | SignalPanel (polling signals endpoint) | ❌ | MEDIUM | 3h |
| **F-16-04** | Research Workspace route | ❌ | LOW | 4h |
| **F-16-05** | Risk Workspace route | ❌ | LOW | 4h |
| **F-16-06** | Ops Workspace route | ❌ | LOW | 4h |
| **F-16-07** | StreamStatusDot per-stream | ❌ | LOW | 2h |
| **F-16-08** | GapBanner (data missed during reconnect) | ❌ | LOW | 2h |

### C. Infrastructure Gaps

| Gap ID | Component | Status | Priority | Effort |
|--------|-----------|--------|----------|--------|
| **I-16-01** | AutoGen Studio container | ❌ | MEDIUM | 3h |
| **I-16-02** | Caddy route for `/autogen-studio` | ❌ | MEDIUM | 1h |
| **I-16-03** | VPS backup scripts (untracked) | ⚠️ | LOW | 1h |
| **I-16-04** | Monitoring dashboard (Grafana?) | ❌ | LOW | 8h |

---

## Part 4: AutoGen Studio Integration Plan

### Current State

**Lumine SUDAH punya AutoGen pipeline:**
```
backend/src/lumine/autogen_pipeline/
├── agents/
│   ├── macro_analyst.py
│   ├── news_analyst.py
│   ├── smc_analyst.py
│   ├── technical_analyst.py
│   └── _base.py
├── cio_proposer.py
├── debate.py
├── ic_forum.py
├── orchestration.py
├── orchestrator.py
├── risk_assessor.py
└── journal.py
```

**TAPI belum ada visual management UI.**

### AutoGen Studio Features (Microsoft)

- Visual agent builder (drag & drop)
- Prompt template management
- Model routing configuration
- Conversation UI
- API key management
- Workflow visualization

### Integration Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  Lumine Terminal (frontend)                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
│  │ /terminal    │  │ /dashboard   │  │/autogen-studio│     │
│  │ (trading)    │  │ (analytics)  │  │ (agent mgmt) │     │
│  └──────────────┘  └──────────────┘  └──────────────┘     │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  Caddy Reverse Proxy (lumine.biz.id)                         │
│  - /api/v1/* → backend-api:8000                              │
│  - /autogen-studio/* → autogenstudio:8081                    │
└─────────────────────────────────────────────────────────────┘
                            │
         ┌──────────────────┴──────────────────┐
         ▼                                      ▼
┌──────────────────┐                   ┌──────────────────┐
│  backend-api     │                   │  autogenstudio   │
│  (FastAPI)       │                   │  (AutoGen UI)    │
│  Port: 8000      │                   │  Port: 8081      │
└──────────────────┘                   └──────────────────┘
         │                                      │
         └──────────────────┬──────────────────┘
                            ▼
                   ┌──────────────────┐
                   │  PostgreSQL      │
                   │  (shared DB)     │
                   └──────────────────┘
```

### Implementation Steps

#### Phase 1: Install AutoGen Studio (2h)

```bash
# On VPS
ssh root@166.88.227.177

# Install via pip (Python 3.12)
pip3 install autogenstudio

# Create app directory
mkdir -p /opt/lumine/autogenstudio
cd /opt/lumine/autogenstudio

# Initialize
autogenstudio ui --port 8081 --appdir ./myapp
```

#### Phase 2: Docker Compose Integration (1h)

```yaml
# backend/docker-compose.vps.yml
services:
  autogenstudio:
    image: python:3.12-slim
    container_name: lumine-autogenstudio
    working_dir: /app
    volumes:
      - ./autogenstudio:/app
    command: >
      bash -c "pip install autogenstudio && autogenstudio ui --port 8081 --appdir ./myapp"
    ports:
      - "8081:8081"
    environment:
      - OPENAI_API_KEY=${OPENAI_API_KEY}
      - DATABASE_URL=postgresql://lumine:****@postgres:5432/lumine
    depends_on:
      - postgres
    restart: unless-stopped
```

#### Phase 3: Caddy Route (30 min)

```caddyfile
# backend/Caddyfile.prod
handle /autogen-studio* {
    reverse_proxy autogenstudio:8081
}
```

#### Phase 4: Frontend Embed (1h)

```tsx
// frontend/src/app/pages/autogen-studio.tsx
import { useEffect, useRef } from 'react';

export function AutoGenStudio() {
  const iframeRef = useRef<HTMLIFrameElement>(null);
  
  useEffect(() => {
    // Auto-resize iframe to fit content
    const handleResize = () => {
      if (iframeRef.current) {
        iframeRef.current.style.height = `${window.innerHeight - 64}px`;
      }
    };
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);
  
  return (
    <div className="h-full w-full">
      <iframe
        ref={iframeRef}
        src="/autogen-studio"
        className="w-full h-full border-0"
        title="AutoGen Studio"
      />
    </div>
  );
}
```

#### Phase 5: Connect to Lumine Agents (2h)

```python
# backend/src/lumine/autogen_pipeline/studio_config.py
"""AutoGen Studio configuration for Lumine agents."""

from autogen_agentchat.agents import AssistantAgent
from lumine.autogen_pipeline.agents import (
    MacroAnalyst,
    NewsAnalyst,
    SMCAnalyst,
    TechnicalAnalyst,
)

# Export agents for AutoGen Studio
LUMINE_AGENTS = {
    "macro_analyst": MacroAnalyst,
    "news_analyst": NewsAnalyst,
    "smc_analyst": SMCAnalyst,
    "technical_analyst": TechnicalAnalyst,
}

# Model routing (via 9router)
MODEL_CONFIG = {
    "model": "gpt-4o",
    "api_key": "${NINEROUTER_API_KEY}",
    "base_url": "http://9router:20128/v1",
}
```

---

## Part 5: Priority Task Execution Plan

### Week 1 (Aug 15-21): Critical Path

#### Day 1-2: Positions & P&L (HIGH priority)

**Task B-16-01: Positions Backfill**
```python
# scripts/backfill_positions.py
"""Create positions from filled orders + lineage records."""

import asyncio
from lumine.data.session import get_sessionmaker
from lumine.data.repositories import OrderRepository, PositionRepository
from lumine.data.models import Position
from uuid import uuid4

async def backfill_positions():
    async with get_sessionmaker()() as session:
        order_repo = OrderRepository(session)
        position_repo = PositionRepository(session)
        
        # Get filled orders with mt5_ticket
        filled_orders = await order_repo.list_filled()
        
        for order in filled_orders:
            if order.filled_volume > 0 and order.mt5_ticket:
                # Check if position already exists
                existing = await position_repo.get_by_symbol_book_strategy(
                    symbol=order.symbol,
                    book="default",
                    strategy_id=uuid4()  # Use default strategy
                )
                
                if existing:
                    # Update existing position
                    existing.size += order.filled_volume
                    existing.avg_entry = order.fill_price
                else:
                    # Create new position
                    position = Position(
                        position_id=uuid4(),
                        symbol=order.symbol,
                        book="default",
                        strategy_id=uuid4(),
                        side=order.side,
                        size=order.filled_volume,
                        avg_entry=order.fill_price,
                        opened_at=order.created_at,
                        opened_lineage=order.lineage_id,
                    )
                    session.add(position)
        
        await session.commit()
        print(f"Backfilled positions from {len(filled_orders)} orders")

if __name__ == "__main__":
    asyncio.run(backfill_positions())
```

**Task B-16-03: P&L Calculation**
```python
# backend/src/lumine/trade_core/pnl.py
"""Real-time P&L calculation."""

from decimal import Decimal
from lumine.api.routers.market import get_market_service

async def calculate_pnl(position, current_price=None):
    """Calculate unrealized P&L for a position."""
    if not current_price:
        market_service = get_market_service()
        quote = await market_service.get_quote(position.symbol)
        current_price = quote.bid if position.side == "buy" else quote.ask
    
    if position.side == "buy":
        pnl = (current_price - position.avg_entry) * position.size
    else:
        pnl = (position.avg_entry - current_price) * position.size
    
    return pnl
```

#### Day 3-4: AutoGen Studio Integration (MEDIUM priority)

- Install AutoGen Studio
- Docker Compose integration
- Caddy routing
- Frontend embed

#### Day 5: Frontend Rewiring (HIGH priority)

- Replace fixture imports with API hooks
- Update all pages to use real data

### Week 2 (Aug 22-28): Polish & Testing

#### Day 1-2: Feature/Signal Panels

- Implement `/api/v1/market/features/{symbol}`
- Implement `/api/v1/market/signals/{symbol}`
- Frontend polling components

#### Day 3-4: Testing & Documentation

- Update all sprint evidence
- Run full test suite
- Document new endpoints

#### Day 5: Deployment & Verification

- Deploy to VPS
- End-to-end verification
- Update roadmap

---

## Part 6: Sprint Evidence Requirements

For each completed task, create evidence file with:

1. **Implementation Details**
   - File paths with line numbers
   - Code snippets
   - API endpoints

2. **Verification Results**
   - Test output (pytest, tsc, vitest)
   - Database queries showing data
   - Screenshot/URL for UI components

3. **Quality Gates**
   - Ruff: 0 errors
   - TypeScript: 0 errors
   - Tests: All passing
   - Contract tests: 57/57

**Template:**
```markdown
# Task B-16-01: Positions Backfill — Complete

**Date:** 2026-08-16
**Status:** ✅ COMPLETE

## Implementation

### Files Modified
- `scripts/backfill_positions.py` (new, 85 lines)
- `backend/src/lumine/data/models.py` (added Position.avg_entry calculation)
- `backend/src/lumine/api/routers/portfolio.py` (added P&L endpoint)

### Code Snippet
```python
# scripts/backfill_positions.py:42-58
async def backfill_positions():
    # ... implementation
```

## Verification

### Database Query
```sql
SELECT COUNT(*) FROM positions;
-- Result: 5 positions created
```

### Test Output
```bash
$ pytest tests/unit/test_backfill_positions.py -v
# All 3 tests passing
```

## Quality Gates
- ✅ Ruff: All checks passed
- ✅ Contract tests: 57/57
- ✅ Manual verification: Positions appear in /terminal

## Next Steps
- Implement P&L calculation (B-16-03)
- Connect to AutoGen Studio (B-16-05)
```

---

## Part 7: Sync Checklist (Local ↔ VPS ↔ GitHub)

### Before Starting Work

```bash
# Local machine
cd /c/Users/MANOB_PC2/Documents/GitHub/lumine-hedge-fund
git pull origin dev
git status  # Ensure clean

# VPS
ssh root@166.88.227.177 "cd /opt/lumine && git pull origin dev"
```

### During Work

```bash
# After each significant change
git add -A
git commit -m "feat: [description]"
git push origin dev

# On VPS (after push)
ssh root@166.88.227.177 "cd /opt/lumine && git pull origin dev"
ssh root@166.88.227.177 "cd /opt/lumine/backend && docker compose -f docker-compose.vps.yml build --no-cache [service]"
ssh root@166.88.227.177 "cd /opt/lumine/backend && docker compose -f docker-compose.vps.yml up -d --force-recreate [service]"
```

### End of Session

```bash
# Verify sync
git status
ssh root@166.88.227.177 "cd /opt/lumine && git status"

# Ensure no divergence
git log --oneline -5
ssh root@166.88.227.177 "cd /opt/lumine && git log --oneline -5"
```

---

## Part 8: Success Metrics

### Week 1 Targets

| Metric | Target | Measurement |
|--------|--------|-------------|
| Positions backfilled | ≥ 5 positions | `SELECT COUNT(*) FROM positions` |
| P&L calculation | Real-time | Manual verification in /terminal |
| AutoGen Studio | Running | `curl https://lumine.biz.id/autogen-studio` |
| Frontend rewire | 100% API-backed | No fixture imports in production |
| Test coverage | ≥ 90% | `pytest --cov` |
| Contract tests | 57/57 | `pytest tests/contract` |

### Week 2 Targets

| Metric | Target | Measurement |
|--------|--------|-------------|
| Feature/Signal endpoints | Implemented | API docs + tests |
| Sprint evidence | All tasks documented | `docs/15-implementation/sprint-evidence/` |
| Documentation | Updated roadmap | `docs/00-vision/long-term-roadmap.md` |
| Deployment | Zero downtime | Health checks passing |
| Sync | 100% aligned | `git diff local vps` = empty |

---

## Appendix A: VPS Environment Details

**Server:** 166.88.227.177 (lumine.biz.id)  
**OS:** Ubuntu 24.04 LTS  
**Python:** 3.12.3  
**Docker:** 27.x  
**PostgreSQL:** 16  
**Redis:** 7.x  

**Deploy Directory:** `/opt/lumine`  
**SSH Key:** `~/.ssh/lumine/id_rsa_lumine`  
**Compose File:** `backend/docker-compose.vps.yml`  

**Services Running:**
- api (FastAPI, port 8000)
- frontend (Nginx, port 80)
- mt5 (Wine + MT5, VNC 5900, HTTP 6901)
- caddy (reverse proxy, ports 80/443)
- postgres (port 5432)
- redis (port 6379)
- 9router (LLM gateway, port 20128)
- headroom (resource monitor, port 8787)
- dozzle (log viewer, port 8080)
- mt5-bridge (EA HTTP bridge, port 8000)
- redis-http-proxy (MT5→Redis, port 8765)

---

## Appendix B: Quick Reference Commands

```bash
# Deploy frontend
ssh root@166.88.227.177 "cd /opt/lumine && git pull && cd backend && docker compose -f docker-compose.vps.yml build --no-cache frontend && docker compose -f docker-compose.vps.yml up -d --force-recreate frontend"

# Deploy API
ssh root@166.88.227.177 "cd /opt/lumine && git pull && cd backend && docker compose -f docker-compose.vps.yml build --no-cache api && docker compose -f docker-compose.vps.yml up -d --force-recreate api"

# Check logs
ssh root@166.88.227.177 "docker logs backend-api-1 --tail 50"

# Restart MT5
ssh root@166.88.227.177 "docker restart lumine-mt5"

# Database query
ssh root@166.88.227.177 "docker exec backend-postgres-1 psql -U lumine -d lumine -c 'SELECT COUNT(*) FROM positions;'"

# Run tests locally
cd backend && PYTHONPATH= .venv/Scripts/python.exe -m pytest tests/contract -v
```

---

**End of Document**

**Next Action:** Begin with Task B-16-01 (Positions Backfill) — highest priority, blocks P&L display.
