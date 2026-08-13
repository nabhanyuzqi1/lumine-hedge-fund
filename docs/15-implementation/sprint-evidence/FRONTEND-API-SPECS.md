# Frontend API Specifications — Backend Reference

**Document Date:** 2026-08-14 (updated — ditambahkan status rekonsiliasi vs backend live)  
**Source:** `frontend/src/lib/api/` + `frontend/src/api/hooks.ts`  
**Phase:** Phase 9 Contract (consumed by Phase 15 Implementation)

---

## Rekonsiliasi vs Backend Live (2026-08-14, sesi lanjutan — RESOLVED)

> **Update sesi lanjutan:** seluruh mismatch pada tabel di bawah **sudah diselesaikan dan diverifikasi live** (E2E 16/16, contract 53/53). Detail: `FRONTEND-BACKEND-ROADMAP-CHECKPOINT.md` + `../IMPLEMENTATION-GAP-INVENTORY.md`.

| Area | Frontend spec (dokumen ini) | Backend live | Catatan |
|------|-----------------------------|--------------|---------|
| Market data | `/api/market/*` (9 endpoint) | ✅ **10 endpoint live** | quote/quotes/ohlcv/symbol/symbols/volatility/correlation/spread/session/features di `routers/market.py` (data deterministik demo) |
| Portfolio | `/api/portfolio/*`, `/api/portfolios/*` | ⚠️ `/summary`, `/positions`, `/positions/{id}`, `/exposure`, **+ `/simulate` live** | CRUD portfolio + export masih belum ada; summary tanpa `{portfolioId}` (frontend sudah selaras) |
| Orders | `/api/orders/*` (4+ endpoint) | ✅ GET list/get, POST, **PATCH (modify)**, DELETE | Cancel selaras `DELETE /orders/{id}`; history + bulk status masih belum ada |
| SSE | `/api/stream/{resourceType}` (4 tipe) | ✅ 6 channel di `/api/v1/streams/*` | Nama channel berbeda dari spec (market-data, analyst-outputs, ic-decisions, cio-proposals, risk-assessments, execution-orders) |
| Envelope | `{data, metadata}` | ✅ `CommonEnvelopeMiddleware` | Sudah sesuai |
| Error | `{data: null, error: {code, message, details}}` | ✅ handler terdaftar | Sudah sesuai |
| Pagination | `PaginatedList` | ✅ `Pagination` dependency | offset/limit (spec lama cursor-based — lihat catatan rest-api.md) |

### ✅ Blocker #1 (Prefix path) — RESOLVED

`core.ts:normalizeApiPath()` kini menulis ulang semua `/api/*` → `/api/v1/*` di satu titik (test: `api.integration.test.ts` — "API version prefix"). HMAC signing juga diwire (env `VITE_LUMINE_API_KEY`/`VITE_LUMINE_API_SECRET`, skema auth.md) — lihat `../IMPLEMENTATION-GAP-INVENTORY.md` F-row.

### ✅ Kontrak yang perlu diselaraskan — RESOLVED

| # | Frontend panggil | Backend sajikan | Status |
|---|------------------|-----------------|--------|
| 1 | `POST /api/rpc/kill-switch {active, tier, reason}` (hooks.ts:402) | `POST /api/v1/admin/kill-switch {armed, reason, tier}` | ✅ Frontend rewire ke admin/kill-switch; backend + field `tier` (persist Redis) |
| 2 | `PATCH /api/orders/{id}/cancel` | `DELETE /api/v1/orders/{order_id}` | ✅ `ordersClient.cancelOrder` → DELETE |
| 3 | `GET /api/portfolio/{id}/summary` | `GET /api/v1/portfolio/summary` (tanpa id) | ✅ `portfolioClient` drop id (summary/positions/exposure) |

---

## Table of Contents

1. [Common Patterns](#common-patterns)
2. [Market Data API](#market-data-api)
3. [Portfolio API](#portfolio-api)
4. [Order Management API](#order-management-api)
5. [Server-Sent Events (SSE)](#server-sent-events-sse)
6. [Mock/Fixture Fallback Layer](#mockfixture-fallback-layer)

---

## Common Patterns

### Base URL Configuration

| Environment | Variable | Default |
|-------------|----------|---------|
| Dev | `VITE_API_URL` | `http://localhost:8000` |
| Docker Compose | (internal service) | `http://backend:8000` |

### Response Envelope Format

All JSON responses MUST follow this structure:

```json
{
  "data": <payload>,
  "metadata": {
    "timestamp": "ISO-8601",
    "request_id": "uuid"
  }
}
```

### Error Handling Contract

All errors return envelope with error payload:

```json
{
  "data": null,
  "error": {
    "code": "ERROR_CODE",
    "message": "Human-readable description",
    "details": { ... } // Optional structured data
  },
  "metadata": { ... }
}
```

### Timeout Configuration

| Operation | Default Timeout |
|-----------|-----------------|
| GET requests | 30 seconds |
| POST/PUT/PATCH | 30 seconds |
| DELETE | 30 seconds |
| SSE connection | 15 seconds |
| SSE reconnect delay | 1 second |
| Max SSE reconnect attempts | 3 (configurable) |

---

## Market Data API

Base path: `/api/market/*`

### Get Real-Time Quote

**Endpoint:** `GET /api/market/quote/{symbol}`

**Path Parameters:**
- `symbol` (string): Trading symbol (e.g., XAUUSD, EURUSD)

**Response:** `MarketQuote`

```typescript
interface MarketQuote {
  symbol: string;
  bid: number;      // Bid price
  ask: number;      // Ask price
  mid: number;      // Mid price = (bid + ask) / 2
  last: number;     // Last traded price
  timestamp: string; // ISO-8601
  volume_24h?: number; // 24h volume (optional)
}
```

**Status Codes:**
- `200`: Success
- `404`: Symbol not found
- `429`: Rate limit exceeded

---

### Batch Fetch Quotes

**Endpoint:** `GET /api/market/quotes?symbols={s1,s2,...}`

**Query Parameters:**
- `symbols` (comma-separated): List of trading symbols

**Response:** `Record<string, MarketQuote>`

```typescript
{
  "XAUUSD": { /* MarketQuote */ },
  "EURUSD": { /* MarketQuote */ },
  "GBPUSD": { /* MarketQuote */ }
}
```

---

### Get OHLCV Data

**Endpoint:** `GET /api/market/ohlcv/{symbol}`

**Path Parameters:**
- `symbol` (string): Trading symbol

**Query Parameters:**
- `timeframe` (required): One of `m1`, `m5`, `m15`, `m30`, `h1`, `h4`, `d1`, `w1`
- `limit` (optional, default: 100): Number of candles (max: 10000)
- `since` (optional): Start timestamp (ISO-8601)

**Response:** `OHLCVPoint[]`

```typescript
interface OHLCVPoint {
  timestamp: string; // ISO-8601 start of candle
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}
```

**Example Request:**
```
GET /api/market/ohlcv/XAUUSD?timeframe=m5&limit=100&since=2026-08-13T00:00:00Z
```

---

### Get Symbol Configuration

**Endpoint:** `GET /api/market/symbol/{symbol}`

**Path Parameters:**
- `symbol` (string): Trading symbol

**Response:** `SymbolConfig`

```typescript
interface SymbolConfig {
  symbol: string;
  description: string;          // e.g., "Gold vs US Dollar"
  base_asset: string;           // e.g., "XAU"
  quote_currency: string;       // e.g., "USD"
  tick_size: number;            // Min price increment (e.g., 0.01)
  lot_size: number;             // Standard contract size (e.g., 1.0)
  min_lot_size: number;         // Minimum order volume (e.g., 0.01)
  max_lot_size: number;         // Maximum order volume (e.g., 100.0)
  is_active: boolean;           // Is this symbol tradable?
}
```

---

### List Available Symbols

**Endpoint:** `GET /api/market/symbols`

**Query Parameters:**
- `asset_class` (optional): Filter by asset class (e.g., "forex", "commodities")
- `exchange` (optional): Filter by exchange/broker
- `include_inactive` (optional, default: false): Include disabled symbols

**Response:** `SymbolConfig[]`

---

### Get Volatility Metrics

**Endpoint:** `GET /api/market/volatility/{symbol}`

**Path Parameters:**
- `symbol` (string): Trading symbol

**Query Parameters:**
- `window` (optional, default: 14): Rolling window in days

**Response:** `VolatilityMetrics`

```typescript
interface VolatilityMetrics {
  volatility: number;           // Annualized volatility percentage (e.g., 0.12 = 12%)
  atr: number;                  // Average True Range
  historical_volatility: number; // Historical volatility over window
  implied_volatility?: number;  // From options (if available)
  vol_regime: "low" | "normal" | "high"; // Current volatility regime
}
```

---

### Get Correlation Matrix

**Endpoint:** `GET /api/market/correlation`

**Query Parameters:**
- `q` (multiple): Symbol names (e.g., `q=XAUUSD&q=EURUSD`)
- `window` (optional, default: 30): Correlation window in days

**Response:** `CorrelationMatrix`

```typescript
interface CorrelationMatrix {
  "XAUUSD": {
    "XAUUSD": 1.0,
    "EURUSD": 0.12,
    "GBPUSD": 0.08
  },
  "EURUSD": {
    "XAUUSD": 0.12,
    "EURUSD": 1.0,
    "GBPUSD": 0.85
  }
}
```

---

### Get Spread Metrics

**Endpoint:** `GET /api/market/spread/{symbol}`

**Path Parameters:**
- `symbol` (string): Trading symbol

**Query Parameters:**
- `period` (optional, default: 60): Calculation period in seconds

**Response:** `SpreadMetrics`

```typescript
interface SpreadMetrics {
  avg_spread: number;           // Average spread width
  avg_pct_spread: number;       // Average percent spread
  min_spread: number;           // Minimum observed spread
  max_spread: number;           // Maximum observed spread
  spread_history?: Array<{      // Per-period spread history
    timestamp: string;
    spread: number;
  }>
}
```

---

### Get Session Timezone Data

**Endpoint:** `GET /api/market/session/{symbol}`

**Path Parameters:**
- `symbol` (string): Trading symbol

**Response:** `SessionData`

```typescript
interface SessionData {
  current_session: string;           // "asian" | "european" | "american" | "mixed"
  next_session: string;              // Next session name
  time_until_next: number;           // Seconds until next session
  is_trading_open: boolean;          // Is market currently open?
  trading_hours?: {                  // Local market hours
    asian_start: string;
    asian_end: string;
    european_start: string;
    european_end: string;
    american_start: string;
    american_end: string;
  }
}
```

---

## Portfolio API

Base path: `/api/portfolio/*` and `/api/portfolios/*`

### Get Portfolio Summary

**Endpoint:** `GET /api/portfolio/{portfolioId}/summary`

**Path Parameters:**
- `portfolioId` (UUID string): Portfolio identifier

**Response:** `PortfolioSummary`

```typescript
interface PortfolioSummary {
  portfolio_id: string;
  nav: number;              // Net Asset Value in base currency
  cash: number;             // Available cash balance
  margin_used: number;      // Total margin utilization
  open_pnl: number;         // Unrealized P&L from open positions
  closed_pnl: number;       // Realized P&L from closed trades
  timestamp: string;        // Snapshot timestamp (ISO-8601)
}
```

---

### List Portfolios

**Endpoint:** `GET /api/portfolios`

**Query Parameters:**
- `ids` (optional): Comma-separated portfolio IDs
- `status` (optional): `active` \| `inactive` \| `all`
- `sort` (optional): `name` \| `nav` \| `created_at` (default: name)
- `order` (optional): `asc` \| `desc` (default: asc)
- `limit` (optional, default: 50): Page size
- `offset` (optional, default: 0): Offset for pagination

**Response:** `PaginatedPortfolioList`

```typescript
interface PaginatedPortfolioList {
  items: Array<{
    id: string;
    name: string;
    nav: number;
    created_at: string;     // ISO-8601
  }>;
  total: number;           // Total count for pagination UI
}
```

---

### Get Position List

**Endpoint:** `GET /api/portfolio/{portfolioId}/positions`

**Path Parameters:**
- `portfolioId` (UUID string): Portfolio identifier

**Response:** `Position[]`

```typescript
interface Position {
  position_id: string;     // UUID
  portfolio_id: string;    // Parent portfolio UUID
  symbol: string;          // Trading symbol
  direction: "long" | "short";
  volume: number;          // Trade volume/contract size
  entry_price: number;     // Entry price at position open
  current_price: number | null; // Current market price (null if unavailable)
  stop_loss?: number;      // Stop loss level (optional)
  take_profit?: number;    // Take profit level (optional)
  unrealized_pnl: number;  // Calculated P&L
  opened_at: string;       // ISO-8601 timestamp
  leverage?: number;       // Leverage used (e.g., 1.0, 10.0, 100.0)
}
```

---

### Get Position Detail

**Endpoint:** `GET /api/portfolio/{portfolioId}/positions/{positionId}`

**Path Parameters:**
- `portfolioId` (UUID string): Portfolio identifier
- `positionId` (UUID string): Position identifier

**Response:** Single `Position` object

---

### Get Exposure Data

**Endpoint:** `GET /api/portfolio/{portfolioId}/exposure`

**Path Parameters:**
- `portfolioId` (UUID string): Portfolio identifier

**Response:** `ExposureSummary[]`

```typescript
interface ExposureSummary {
  symbol: string;          // Symbol or risk bucket name
  notional: number;        // Notional exposure value
  pct_of_nav: number;      // Percentage of total NAV
  correlated_symbols?: string[]; // Related correlated symbols
  sector?: string;         // Sector classification (e.g., "forex", "commodities")
}
```

---

### Simulate Trade (What-If Analysis)

**Endpoint:** `POST /api/portfolio/{portfolioId}/simulate`

**Path Parameters:**
- `portfolioId` (UUID string): Portfolio identifier

**Request Body:**

```typescript
interface SimulateTradeRequest {
  symbol: string;
  side: "buy" | "sell";
  volume: number;
  price: number;
}
```

**Response:** `SimulatedTradeResult`

```typescript
interface SimulatedTradeResult {
  projected_nav: number;   // NAV after simulated trade
  margin_required: number; // Additional margin required
  pnl_change: number;      // Expected P&L change
}
```

**Use Case:** Pre-trade risk check — simulate impact before order submission.

---

### Create Portfolio

**Endpoint:** `POST /api/portfolios`

**Request Body:**

```typescript
interface CreatePortfolioRequest {
  name: string;
  description?: string;
  currency?: string;       // Base currency (e.g., "USD", "EUR")
  base_currency?: string;  // Alias for currency
}
```

**Response:** `CreatePortfolioResult`

```typescript
interface CreatePortfolioResult {
  id: string;              // New portfolio UUID
  name: string;
  created_at: string;
}
```

---

### Update Portfolio Metadata

**Endpoint:** `PUT /api/portfolio/{portfolioId}`

**Path Parameters:**
- `portfolioId` (UUID string): Portfolio identifier

**Request Body:**

```typescript
interface UpdatePortfolioRequest {
  name?: string;
  description?: string;
  currency?: string;
  base_currency?: string;
}
```

**Response:** `void` (204 No Content on success)

---

### Delete Portfolio (Soft Delete)

**Endpoint:** `DELETE /api/portfolio/{portfolioId}`

**Path Parameters:**
- `portfolioId` (UUID string): Portfolio identifier

**Response:** `void` (204 No Content on success)

**Note:** Soft delete only — historical data preserved for compliance. Positions cannot be added to deleted portfolios.

---

### Export Transaction History

**Endpoint:** `GET /api/portfolio/{portfolioId}/transactions/export`

**Path Parameters:**
- `portfolioId` (UUID string): Portfolio identifier

**Response:** `application/csv` — CSV download blob

**Columns:**
- timestamp
- type (trade/deposit/withdrawal/dividend/etc.)
- symbol
- side (if trade)
- volume
- price
- pnl_realized
- fees
- running_balance
- notes

---

### Bulk Get Portfolio Summaries

**Endpoint:** `GET /api/portfolios/bulk`

**Query Parameters:**
- `ids` (multiple): Comma-separated portfolio UUIDs

**Response:** `Record<string, PortfolioSummary>`

```typescript
{
  "uuid-1": { /* PortfolioSummary */ },
  "uuid-2": { /* PortfolioSummary */ }
}
```

**Use Case:** Dashboard overview fetching multiple portfolios efficiently.

---

## Order Management API

Base path: `/api/orders/*`

### Place New Order

**Endpoint:** `POST /api/orders`

**Request Body:** `CreateOrderRequest`

```typescript
interface CreateOrderRequest {
  symbol: string;
  side: "BUY" | "SELL";
  volume: number;
  order_type: "market" | "limit" | "stop" | "stop_limit";
  
  // Limit-only fields
  limit_price?: number;
  
  // Stop-only fields
  stop_price?: number;
  
  // Risk management
  stop_loss?: number;
  take_profit?: number;
  
  // Optional metadata
  portfolio_id?: string;   // Required for non-demo orders
  client_order_id?: string; // Client-provided ID for dedup
  notes?: string;          // Human-readable reason
  time_in_force?: "GTC" | "IOC" | "FOK"; // Default: GTC
}
```

**Response:** `Order`

```typescript
interface Order {
  id: string;              // Order UUID (assigned by backend)
  status: OrderStatus;     // Current lifecycle state
  symbol: string;
  side: "BUY" | "SELL";
  quantity: number;
  filled_quantity: number; // Filled portion (partial fills supported)
  
  // Price fields
  order_type: string;
  order_price?: number;    // Limit/stop price
  trigger_price?: number;  // For triggered orders
  
  // Execution prices
  avg_fill_price?: number; // Weighted average fill price
  commission?: number;     // Total fees paid
  
  // Lifecycle timestamps
  created_at: string;      // ISO-8601
  updated_at: string;      // ISO-8601
  filled_at?: string;      // ISO-8601 (when fully filled)
  cancelled_at?: string;   // ISO-8601
  
  // Risk/reason codes
  rejection_reason?: string;
  validation_errors?: string[];
  
  // Audit trail
  workflow_run_id?: string; // AutoGen workflow instance that approved
}
```

**Order Status Enum:**
- `RECEIVED` — Order received, queued for validation
- `VALIDATED` — Passed basic validation
- `RISK_CHECK` — Running pre-trade risk checks
- `ACTIVE` — Sent to broker/exchange
- `FILLED` — Completely executed
- `PARTIALLY_FILLED` — Partially executed (see `filled_quantity`)
- `CANCELLED` — Cancelled by user/workflow
- `REJECTED` — Rejected by risk/validation

---

### Get Order By ID

**Endpoint:** `GET /api/orders/{orderId}`

**Path Parameters:**
- `orderId` (UUID string): Order identifier

**Response:** Full `Order` object including execution state

---

### Get Orders List

**Endpoint:** `GET /api/orders`

**Query Parameters:**
- `portfolioId` (optional): Filter by portfolio UUID
- `symbol` (optional): Filter by symbol (e.g., XAUUSD)
- `status` (optional): Filter by one or more statuses
- `orderType` (optional): `market` \| `limit` \| `stop`
- `from` (optional): Start timestamp (ISO-8601)
- `to` (optional): End timestamp (ISO-8601)
- `limit` (optional, default: 100): Page size
- `offset` (optional, default: 0): Offset for pagination

**Response:** `PaginatedOrderList`

```typescript
interface PaginatedOrderList {
  items: Order[];
  total: number;
}
```

---

### Cancel Order

**Endpoint:** `DELETE /api/orders/{orderId}`

**Path Parameters:**
- `orderId` (UUID string): Order identifier

**Request Body (optional):**

```typescript
interface CancelOrderRequest {
  reason?: string; // For audit trail
}
```

**Response:** `Order` — Returns updated order with `status: CANCELLED`

**Note:** Only works for orders in `ACTIVE` or `RISK_CHECK` state. Filled/cancelled orders reject cancellation.

---

### Modify Order (Modify Replace)

**Endpoint:** `PATCH /api/orders/{orderId}`

**Path Parameters:**
- `orderId` (UUID string): Order identifier

**Request Body:**

```typescript
interface ModifyOrderRequest {
  volume?: number;
  limit_price?: number;
  stop_loss?: number;
  take_profit?: number;
}
```

**Response:** `Order` — Returns updated order

**Note:** Backend creates new order, cancels old one. Preserves full audit trail.

---

## Server-Sent Events (SSE)

Base endpoint: `/api/stream/{resourceType}`

### Connection Requirements

| Parameter | Default | Max | Description |
|-----------|---------|-----|-------------|
| Connect timeout | 15s | 30s | Wait for connection |
| Reconnect delay | 1s | 10s | Backoff between attempts |
| Max reconnect attempts | 3 | ∞ | -1 = infinite retries |

### Event Message Format

All SSE events use JSON envelope:

```json
{
  "event": "event_type_name",
  "data": <payload>,
  "timestamp": "ISO-8601"
}
```

### Available Stream Types

#### Market Data Stream

**Endpoint:** `GET /api/stream/market/{symbol}`

**Subscribed Events:**
- `quote_update` — Real-time bid/ask/mid changes
- `ohlc_snapshot` — Periodic OHLCV snapshot ( configurable interval)
- `spread_alert` — Wide spread warning (>2x normal)

**Event Payload Example:**
```json
{
  "event": "quote_update",
  "data": {
    "symbol": "XAUUSD",
    "bid": 2658.12,
    "ask": 2658.15,
    "mid": 2658.135,
    "last": 2658.14,
    "volume_24h": 1234567
  },
  "timestamp": "2026-08-13T23:30:00Z"
}
```

---

#### Portfolio Stream

**Endpoint:** `GET /api/stream/portfolio/{portfolioId}`

**Subscribed Events:**
- `nav_update` — NAV/cash/margin changes
- `position_open` — New position opened
- `position_close` — Position closed/filled
- `position_update` — Existing position P&L update
- `pnl_update` — Overall P&L change notification

**Event Payload Examples:**

```json
// position_open
{
  "event": "position_open",
  "data": {
    "position_id": "uuid-...",
    "symbol": "XAUUSD",
    "side": "BUY",
    "volume": 1.0,
    "entry_price": 2658.15,
    "opened_at": "2026-08-13T23:30:00Z"
  }
}

// position_update
{
  "event": "position_update",
  "data": {
    "position_id": "uuid-...",
    "current_price": 2658.50,
    "unrealized_pnl": 350.00
  }
}
```

---

#### Order Stream

**Endpoint:** `GET /api/stream/orders`

**Subscribed Events:**
- `order_received` — Order accepted, pending validation
- `order_validated` — Passed validation
- `order_risk_check` — Risk check in progress
- `order_active` — Sent to broker
- `order_partial_fill` — Partial execution
- `order_filled` — Completely filled
- `order_cancelled` — User-cancelled
- `order_rejected` — Rejected with reason

**Event Payload Example:**
```json
{
  "event": "order_partial_fill",
  "data": {
    "order_id": "uuid-...",
    "symbol": "XAUUSD",
    "side": "BUY",
    "quantity": 1.0,
    "filled_quantity": 0.5,
    "avg_fill_price": 2658.20,
    "status": "PARTIALLY_FILLED"
  }
}
```

---

#### Committee/Workflow Stream

**Endpoint:** `GET /api/stream/workflows`

**Subscribed Events:**
- `workflow_started` — AutoGen workflow initialized
- `agent_response` — Agent reasoning/update
- `decision_made` — Investment committee decision
- `execution_triggered` — Order sent for execution
- `workflow_complete` — Workflow finished

**Event Payload Example:**
```json
{
  "event": "agent_response",
  "data": {
    "workflow_id": "wf-uuid-...",
    "agent_role": "TechnicalAnalyst",
    "step": 3,
    "message": "Bullish crossover detected on 1H timeframe",
    "confidence": 0.75
  }
}
```

---

## Mock/Fixture Fallback Layer

**File:** `src/api/hooks.ts`

When backend is not running (Phase 15 pre-backend), all hooks fallback to deterministic seeded fixtures:

| Hook | Query Key | Fixture Source | Stale Time |
|------|-----------|----------------|------------|
| `useMarketBars` | `["market-bars", symbol, timeframe]` | `generateBars()` | 30s |
| `useEquityCurve` | `["equity-curve", portfolioId]` | `generateEquity()` | 60s |
| `useExposure` | `["exposure", portfolioId]` | `generateExposure()` | 60s |
| `useSignals` | `["signals", symbol]` | `generateSignals()` | 30s |
| `useCorrelation` | `["correlation"]` | `generateCorrelationMatrix()` | 60s |
| `useQuote` | `["quote", symbol]` | `generateQuote(symbol)` | 5s |
| `usePositions` | `["positions", portfolioId]` | `generatePositions()` | 30s |
| `useOrders` | `["orders", portfolioId]` | `generateOrders()` | 30s |
| `useOrder` | `["order", orderId]` | `generateOrder(orderId)` | 30s |
| `useRun` | `["run", runId]` | `generateRun(runId)` | 30s |
| `useLineage` | `["lineage", lineageId]` | `generateLineage(lineageId)` | 60s |
| `useJournal` | `["journal", filters]` | `generateJournalEntries()` | 15s |
| `useJournalPage` | `["journal", filters, cursor]` | `generateJournalEntries(cursor)` | 15s |
| `useApiKeys` | `["api-keys"]` | `generateApiKeys()` | 30s |

### Mutation Hooks (Fixture Only Until Backend)

| Hook | Mutation Function | Effect |
|------|------------------|--------|
| `useCreateApiKey` | `generateApiKeySecret(scopes)` | Adds to query cache |
| `useRevokeApiKey` | N/A | Sets `revoked: true` in cache |
| `useCancelOrder` | N/A | Updates order status → CANCELLED |

---

## Integration Notes

### TanStack Query Defaults

| Setting | Value | Reason |
|---------|-------|--------|
| `staleTime` | Varies per hook | Based on data freshness requirements |
| `refetchOnWindowFocus` | `true` | Keep data fresh on user return |
| `retry` | 3 attempts | Network resilience |
| `queryClient` | Singleton | Shared across app |

See `src/api/query-client.ts` for configuration.

### HTTP Client Features

See `src/lib/api/core.ts`:
- Automatic 30s timeout on all requests
- AbortController pooling for cleanup
- Consistent error mapping (`ApiError`, subclasses)
- Response envelope validation
- CORS header handling

---

## Backend TODO Checklist (reconciled 2026-08-14)

Berdasarkan source backend (`backend/src/lumine/api/routers/*`), status implementasi per item spec frontend:

### ✅ Sudah live

- [x] SSE streaming layer — 6 channel di `/api/v1/streams/*` (streams.py)
- [x] Response envelope wrapper — `CommonEnvelopeMiddleware` (app.py:113)
- [x] Error envelope format — handler `LumineError` / validation / HTTP (app.py:124-129)
- [x] Pagination response pattern — `PaginatedList` + `Pagination` dependency (schemas/common.py)
- [x] Request ID tracking — `RequestLoggingMiddleware` echoes `X-Request-ID` (app.py:119)
- [x] Rate limiting — `rate_limit_dependency` per router (middleware/rate_limit.py)
- [x] Admin keys CRUD + kill-switch — `/api/v1/admin/*` (admin.py)
- [x] Journal + lineage + workflows + portfolio (summary/positions/exposure) + orders (list/get/create/delete) + rpc commands (4 POST)

### ⚠️ Mismatch kontrak (perlu diselaraskan)

- [ ] Prefix path: frontend `/api/*` vs backend `/api/v1/*` (BLOCKER)
- [ ] Kill-switch: `POST /api/rpc/kill-switch {active, tier, reason}` vs `POST /api/v1/admin/kill-switch {armed, reason}`
- [ ] Cancel order: frontend `PATCH /api/orders/{id}/cancel` vs backend `DELETE /api/v1/orders/{order_id}`
- [ ] Portfolio summary: frontend `/api/portfolio/{id}/summary` vs backend `/api/v1/portfolio/summary`
- [ ] SSE channel naming: spec `/api/stream/{resourceType}` vs backend `/api/v1/streams/{market-data|analyst-outputs|ic-decisions|cio-proposals|risk-assessments|execution-orders}`

### ❌ Belum ada di backend

- [ ] `PATCH /api/orders/{order_id}` (order modify — ModifyOrderDialog masih fixture)
- [ ] Klaster market: `/quote/{symbol}`, `/quotes`, `/ohlcv/{symbol}`, `/symbol/{symbol}`, `/symbols`, `/volatility/{symbol}`, `/session/{symbol}`, `/features/{symbol}`, `/correlation`, `/spread/{symbol}`
- [ ] `POST /api/portfolio/{id}/simulate` (what-if)
- [ ] Portfolio CRUD: `POST /api/portfolios`, `PUT/DELETE /api/portfolio/{id}`, `GET /api/portfolios/bulk`, export CSV
- [ ] `DELETE /api/portfolio/{portfolio_id}/orders` (cancel-all)
- [ ] `GET /api/orders/{id}/history`, `GET /api/orders/bulk/status`

---

**End of Document**
