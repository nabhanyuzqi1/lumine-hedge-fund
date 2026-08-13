# Frontend Performance Monitoring Plan — Phase 16 Sprint 16.4

**Document Date:** 2026-08-13  
**Phase Status:** In Progress  
**Sprint Owner:** Development Team  

---

## Executive Summary

This plan defines the frontend performance monitoring dashboards and real-time metrics collection for Lumine's institutional trading platform. The monitoring system provides operators visibility into application health, resource usage, and responsiveness during live trading sessions.

---

## Architecture Overview

### Data Flow

```
┌─────────────────────────────────────────────────────────────┐
│                    Browser Runtime                          │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌──────────────┐    ┌──────────────────┐     ┌─────────┐ │
│  │Performance   │    │usePerformance    │     │Metrics  │ │
│  │Observer API  │───▶│ Metrics (hook)   │────▶│ Display │ │
│  │              │    │                  │     │ Widget  │ │
│  └──────────────┘    └──────────────────┘     └─────────┘ │
│          │                   │                         │    │
│          ▼                   ▼                         ▼    │
│  ┌──────────────┐    ┌──────────────────┐     ┌─────────┐ │
│  │Web Vitals:    │    │TanStack Query    │     │Alerts   │ │
│  │FCP, LCP, TTI  │    │Fetch times      │     │(FPS<55) │ │
│  └──────────────┘    └──────────────────┘     └─────────┘ │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## Core Metrics Collection

### 1. Web Vitals (Critical User-Perceived Performance)

| Metric | API | Threshold | Alert Severity |
|--------|-----|-----------|----------------|
| **First Contentful Paint (FCP)** | `PerformanceObserver('paint')` | < 1.5s | info |
| **Largest Contentful Paint (LCP)** | `PerformanceObserver('largest-contentful-paint')` | < 2.5s | warn |
| **Time to Interactive (TTI)** | Custom calculation via `longtask` entries | < 3.8s | danger |

### 2. Rendering Performance

| Metric | Collection Method | Threshold |
|--------|-------------------|-----------|
| **Frames Per Second (FPS)** | `requestAnimationFrame` sampling | Maintain 60fps |
| **Render Duration** | React devtools profiling hook per component | < 16ms/frame |
| **Long Tasks** | `PerformanceObserver('longtasks')` | > 50ms alert |

### 3. Memory Usage

| Metric | API | Threshold |
|--------|-----|-----------|
| **Heap Size Used** | `performance.memory.usedJSHeapSize` | < 80MB operational |
| **Memory Pressure Events** | `navigator.deviceMemory` estimate | < 4GB RAM available |

### 4. Network & Data Stream Health

| Metric | Source | Tracking Point |
|--------|--------|----------------|
| **Query Fetch Time** | TanStack Query `onSuccess` hook | Per data source endpoint |
| **SSE Reconnect Count** | useDemoStreams custom event | Cumulative session total |
| **WebSocket Latency** | Ping/pong interval | Average RTT in ms |

---

## UI Components Specification

### PerformanceIndicatorWidget

**Location:** Terminal header (top-right corner, next to workspace rail)

**Visual Design:**
- Compact badge display matching existing `Badge` component pattern
- Dual metric display: FPS counter + memory indicator
- Color-coded by threshold state:
  - Green (fps >= 55): Normal operation
  - Amber (45 <= fps < 55): Degraded performance
  - Red (fps < 45): Critical throttling

**Code Structure:**
```typescript
src/components/monitoring/performance-indicator.tsx
- Props: fps: number, memoryMB: number, showExpanded?: boolean
- Default: compact dual-badge (e.g., "60fps • 72MB")
- Expanded mode: detailed chart panel with 60-second rolling history
```

### BundleStatsDisplay

**Location:** Optional detail page `/stats/bundle` (operators only)

**Visual Design:**
- Card layout matching `ChartCard` pattern
- Treemap visualization of bundle chunk sizes
- Lazy-loaded chunks highlighted separately from main bundle

**Data Sources:**
- Built-in Vite analyzer output (`vite-bundle-visualizer` plugin)
- Runtime chunk load timing from lazy-loaded modules

---

## Implementation Files

### 1. Metrics Collection Layer

**File:** `src/lib/metrics.ts`

**Responsibilities:**
- Initialize all PerformanceObserver instances on module load
- Aggregate long-task detection with 50ms threshold
- Expose raw metrics array with timestamp correlation
- Memory pressure estimation from `navigator.deviceMemory`

**Key Functions:**
```typescript
export function initMetricsCollector(): void
export function getVitalsSummary(): { fcp: number, lcp: number, tti: number }
export function getMemoryReport(): { usedMB: number, estimatedTotalMB: number }
export function getRenderHealth(): { avgFps: number, longTaskCount: number }
```

### 2. React Hook Abstraction

**File:** `src/hooks/usePerformanceMetrics.ts`

**Responsibilities:**
- Subscribe to metrics updates at 250ms intervals
- Provide reactive state for components
- Cleanup observers on unmount
- Memoized selectors to prevent unnecessary re-renders

**Usage Pattern:**
```typescript
const { fps, memoryMB, vitals } = usePerformanceMetrics();
```

### 3. Widget Component

**File:** `src/components/monitoring/performance-indicator.tsx`

**Props Interface:**
```typescript
interface PerformanceIndicatorProps {
  fps: number;
  memoryMB: number;
  showExpanded?: boolean;
  expandedOnInit?: boolean;
}
```

### 4. Bundle Statistics Page

**File:** `src/app/pages/stats/bundle-stats.tsx`

**Content:**
- Route protected by operator-only access control
- Visual treemap of all loaded code bundles
- Load time breakdown per lazy route component
- Comparison against baseline performance budgets

---

## Integration Points

### Terminal Header Modification

**File:** `src/app/pages/terminal.tsx`

Add right-aligned widget to existing header:
```tsx
<header className="flex items-baseline justify-between">
  <div>...</div>
  <div className="flex items-center gap-3">
    <PerformanceIndicator fps={fps} memoryMB={memoryMB} />
  </div>
</header>
```

### TanStack Query Extension

**File:** `src/api/queryClient.ts`

Wrap query execution with timing instrumentation:
```typescript
queryClient.setQueryDefaults(['market-bars'], {
  networkMode: 'always',
  staleTime: 0,
});

// Add fetch timer observer
onSuccess: (data, query) => {
  recordMetric('query-fetch', { queryKey: query.queryKey[0], durationMs: ... });
}
```

---

## Performance Budgets (Baseline Targets)

| Metric | Target | Warning | Critical |
|--------|--------|---------|----------|
| Initial FCP | 1.2s | 1.5s | 2.0s |
| Main bundle size | 200KB gz | 250KB gz | 300KB gz |
| Lazy chunk avg | 50KB gz | 75KB gz | 100KB gz |
| Render FPS | 60fps | 55fps | 45fps |
| Memory usage | 60MB | 80MB | 100MB |
| Query p95 latency | 50ms | 100ms | 200ms |

---

## Operational Workflows

### Daily Operator Checklist

- [ ] Monitor FPS trend over first trading hour after market open
- [ ] Verify memory growth stays flat (<5% per hour) under sustained order flow
- [ ] Confirm no LCP spikes correlate with window focus changes
- [ ] Review query retry counts during periods of high volatility

### Incident Response Triggers

**Trigger Condition → Action:**
- FPS drops below 45 for >10 seconds → Show persistent red banner warning
- Memory growth exceeds 50MB/hour → Flag for investigation (potential leak)
- LCP > 2.5s repeatedly → Enable aggressive caching strategies
- Query fail rate > 5% → Auto-switch to SSE backup streams

---

## Verification Plan

### Automated Tests

**File:** `tests/unit/hooks/usePerformanceMetrics.test.ts`

- Mock `window.performance` API responses
- Verify observer cleanup on hook unmount
- Test threshold logic triggers correct color states

### Manual Validation

**Tools:** Chrome DevTools Performance tab, Lighthouse CI

**Test Scenario 1:** Startup sequence
- Load terminal page fresh
- Compare dashboard FCP reading vs DevTools Waterfall
- Confirm FPS stabilizes at 60 within 2 seconds

**Test Scenario 2:** Sustained streaming
- Keep positions/orders stream active for 15 minutes
- Verify memory curve stays linear (no exponential growth)
- Confirm no memory leaks detected in heap snapshot

---

## Future Enhancements

- [ ] Remote metrics export to Grafana/MetricsDB
- [ ] A/B testing framework for UI refactor impact measurement
- [ ] Session replay integration for performance anomaly correlation
- [ ] Predictive scaling alerts based on historical volatility patterns

---

## Completion Criteria

- ✅ Metrics collector initialized without blocking critical rendering path
- ✅ FPS counter displays smoothly at target frame rate
- ✅ Memory usage tracked accurately vs DevTools comparison
- ✅ Performance widget integrated into terminal header
- ✅ All alerts trigger correctly when thresholds crossed
- ✅ Documentation complete with troubleshooting guide

**Target Completion Date:** 2026-08-16
