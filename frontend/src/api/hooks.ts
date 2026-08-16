import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { get } from "@/api/client";
import type { Timeframe } from "@/components/charts/candlestick-chart";
import { useUiStore } from "@/stores/uiStore";
import * as adminClient from "@/lib/api/clients/adminClient";
import * as ordersClient from "@/lib/api/clients/ordersClient";
import * as portfolioClient from "@/lib/api/clients/portfolioClient";
import type {
  AdminKey,
  MarketData,
  Order as RestOrder,
  Position as RestPosition,
} from "@/lib/api/types";
import {
  type ApiKeyFixture,
  type ChartBar,
  type CorrelationMatrix,
  type EquityPoint,
  type ExposureItem,
  type JournalPage,
  type LineageFixture,
  type MarketQuote,
  type OrderFixture,
  type PositionFixture,
  type SignalPoint,
  type WorkflowRun,
  generateApiKeys,
  generateBars,
  generateCorrelationMatrix,
  generateEquity,
  generateExposure,
  generateJournalEntries,
  generateLineage,
  generateOrder,
  generateOrders,
  generatePositions,
  generateQuote,
  generateRun,
  generateSignals,
} from "@/data/fixtures";

export const DEFAULT_PORTFOLIO_ID = "default";

const TIMEFRAME_SECONDS: Record<Timeframe, number> = {
  "5m": 300,
  "15m": 900,
  "1H": 3_600,
  "4H": 14_400,
};

export const CORRELATION_SYMBOLS = ["XAUUSD", "XAGUSD", "EURUSD", "GBPUSD", "USOIL", "BTCUSD"];

/* ── Backend REST shapes (backend/src/lumine/api/schemas/api.py) ───────── */

interface RestWorkflowRun {
  run_id: string;
  workflow_name: string;
  status: "pending" | "running" | "completed" | "failed";
  input_payload: Record<string, unknown>;
  output_payload: Record<string, unknown> | null;
  started_at: string;
  finished_at: string | null;
}

interface RestEquityPoint {
  ts: string;
  nav: string;
  equity: string;
  drawdown: string;
}

interface RestJournalEntry {
  entry_id: string;
  trade_id: string;
  agent_name: string;
  reflection: string;
  lesson: string;
  created_at: string;
  symbol?: string | null;
}

interface RestLineageRecord {
  lineage_id: string;
  decision_id: string;
  decision_type: string;
  agent_name: string;
  inputs_hash: string;
  outputs_hash: string;
  policy_version: string;
  created_at: string;
}

interface RestSignal {
  signal_id: string;
  symbol: string;
  analyst: string;
  direction: "bullish" | "bearish" | "neutral";
  confidence: number;
  rationale: string;
  generated_at: string;
}

interface RestMarketBar {
  symbol: string;
  timeframe: string;
  timestamp: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

/* ── REST → fixture shape mappers ─────────────────────────────────────────
 * Backend Decimal fields serialize as strings (envelope middleware uses
 * pydantic JSON mode), so every numeric field is coerced with Number().
 */

const num = (v: unknown, fallback = 0): number => {
  const n = typeof v === "number" ? v : Number(v);
  return Number.isFinite(n) ? n : fallback;
};

const epochSec = (iso: string | undefined): number =>
  iso ? Math.floor(Date.parse(iso) / 1000) : 0;

const ORDER_STATUS_MAP: Record<RestOrder["status"], OrderFixture["status"]> = {
  pending: "ACTIVE",
  filled: "FILLED",
  partially_filled: "ACTIVE",
  rejected: "REJECTED",
  cancelled: "CANCELLED",
};

/** ZERO-DEMO: when true, hooks return real/empty data instead of fixtures. */
const USE_REAL_DATA = true;

function toOrderFixture(order: RestOrder): OrderFixture {
  const status = ORDER_STATUS_MAP[order.status] ?? "ACTIVE";
  const entry = num(order.price);
  return {
    id: order.order_id,
    portfolio_id: order.portfolio_id,
    symbol: order.symbol,
    side: order.side === "sell" ? "SELL" : "BUY",
    quantity: num(order.volume),
    type: order.order_type === "market" ? "MARKET" : order.order_type === "stop" ? "STOP" : "LIMIT",
    status,
    entry_price: entry,
    current_price: entry,
    pnl: 0,
    created_at: order.created_at,
    lifecycle: [{ status, timestamp: order.updated_at }],
  };
}

function toPositionFixture(position: RestPosition): PositionFixture {
  return {
    id: position.position_id,
    portfolio_id: position.portfolio_id,
    symbol: position.symbol,
    side: position.direction === "short" ? "SHORT" : "LONG",
    quantity: num(position.volume),
    avg_entry_price: num(position.entry_price),
    current_price: num(position.current_price, num(position.entry_price)),
    unrealized_pnl: num(position.unrealized_pnl),
    updated_at: position.opened_at,
  };
}

function toMarketQuote(quote: MarketData): MarketQuote {
  return {
    symbol: quote.symbol,
    bid: num(quote.bid),
    ask: num(quote.ask),
    last: num(quote.last),
    timestamp: epochSec(quote.timestamp),
  };
}

function toChartBar(bar: RestMarketBar): ChartBar {
  return {
    time: epochSec(bar.timestamp),
    open: num(bar.open),
    high: num(bar.high),
    low: num(bar.low),
    close: num(bar.close),
    volume: num(bar.volume),
  };
}

function toWorkflowRun(run: RestWorkflowRun): WorkflowRun {
  const status: WorkflowRun["status"] =
    run.status === "running" ? "data_gathering" : run.status === "pending" ? "init" : run.status;
  return {
    id: run.run_id,
    workflow_id: run.run_id,
    workflow_name: run.workflow_name,
    status,
    started_at: run.started_at,
    completed_at: run.finished_at ?? undefined,
    model: "—",
    cost_usd: 0,
    error: undefined,
    stages: [{ stage: "init", timestamp: run.started_at }],
  };
}

function toLineageFixture(record: RestLineageRecord): LineageFixture {
  return {
    lineage_id: record.lineage_id,
    run_id: record.decision_id,
    workflow_id: "wf-api",
    model: "—",
    cost_usd: 0,
    created_at: record.created_at,
    root: {
      id: "decision",
      type: "decision",
      label: `${record.decision_type} — ${record.agent_name}`,
      detail: `inputs ${record.inputs_hash.slice(0, 12)} · outputs ${record.outputs_hash.slice(0, 12)} · policy ${record.policy_version}`,
    },
  };
}

function toJournalEntry(entry: RestJournalEntry): JournalPage["entries"][number] {
  return {
    id: entry.entry_id,
    timestamp: entry.created_at,
    portfolio_id: "portfolio-demo",
    kind: entry.agent_name.includes("risk") ? "risk" : "note",
    actor: entry.agent_name,
    summary: entry.reflection || entry.lesson,
    reason: entry.reflection || undefined,
    lesson: entry.lesson || undefined,
    symbol: entry.symbol ?? undefined,
  };
}

function toApiKeyFixture(key: AdminKey): ApiKeyFixture {
  return {
    key_id: key.key_id,
    prefix: `sk-${key.key_id}`,
    scopes: key.scopes,
    created_at: key.created_at,
    last_used_at: null,
    revoked: key.revoked,
  };
}

/**
 * Query hooks with fixture fallback (legacy). ZERO-DEMO mode disables
 * fixtures and returns real/empty data when the backend returns nothing.
 */

export function useMarketBars(symbol: string, timeframe: Timeframe) {
  return useQuery({
    queryKey: ["market-bars", symbol, timeframe],
    queryFn: async (): Promise<ChartBar[]> => {
      try {
        const bars = await get<RestMarketBar[]>(`/market/ohlcv/${symbol}`, {
          timeframe: timeframe.toLowerCase(),
          limit: "200",
        });
        if (Array.isArray(bars) && bars.length > 0) return bars.map(toChartBar);
      } catch {
        // fall through to empty / fixture
      }
      if (USE_REAL_DATA) return [];
      return generateBars({ intervalSec: TIMEFRAME_SECONDS[timeframe] });
    },
    staleTime: 30_000,
  });
}

export function useEquityCurve(portfolioId: string = DEFAULT_PORTFOLIO_ID) {
  return useQuery({
    queryKey: ["equity-curve", portfolioId],
    queryFn: async (): Promise<EquityPoint[]> => {
      try {
        // Backend: GET /api/v1/portfolio/{id}/equity → PaginatedList of
        // {ts, nav, equity, drawdown} (B-06). Mapped to the chart shape.
        const res = await get<{ items: RestEquityPoint[] }>(`/portfolio/${portfolioId}/equity`, {
          limit: "240",
          offset: "0",
        });
        if (Array.isArray(res?.items) && res.items.length > 0 && typeof res.items[0]?.nav === "string") {
          return res.items.map((p) => ({
            time: new Date(p.ts).getTime() / 1000,
            value: num(p.nav, 0),
          }));
        }
      } catch {
        // fall through to fixture
      }
      if (USE_REAL_DATA) return [];
      return generateEquity();
    },
    staleTime: 60_000,
  });
}

export function useExposure(portfolioId: string = DEFAULT_PORTFOLIO_ID) {
  return useQuery({
    queryKey: ["exposure", portfolioId],
    queryFn: async (): Promise<ExposureItem[]> => {
      try {
        const page = await get<{ items: Array<{ symbol: string; pct_of_nav: number; correlated_bucket?: string | null }> }>(
          `/portfolio/exposure`
        );
        if (Array.isArray(page?.items) && page.items.length > 0) {
          return page.items.map((item) => ({
            symbol: item.symbol,
            assetClass: item.correlated_bucket ?? "other",
            weight: num(item.pct_of_nav),
          }));
        }
      } catch {
        // fall through to fixture
      }
      if (USE_REAL_DATA) return [];
      return generateExposure();
    },
    staleTime: 60_000,
  });
}

export function useSignals(symbol: string) {
  return useQuery({
    queryKey: ["signals", symbol],
    queryFn: async (): Promise<SignalPoint[]> => {
      try {
        // B-06: per-symbol endpoint is live; fall back to the global one.
        const page = await get<{ items: RestSignal[] }>(`/market/signals/${symbol}`);
        if (Array.isArray(page?.items) && page.items.length > 0) {
          return page.items.map((signal) => ({
            time: epochSec(signal.generated_at),
            analyst: signal.analyst,
            confidence: num(signal.confidence),
            direction: signal.direction,
            rationale: signal.rationale,
          }));
        }
      } catch {
        // fall through
      }
      try {
        const page = await get<{ items: RestSignal[] }>(`/market/signals`);
        if (Array.isArray(page?.items) && page.items.length > 0) {
          return page.items.map((signal) => ({
            time: epochSec(signal.generated_at),
            analyst: signal.analyst,
            confidence: num(signal.confidence),
            direction: signal.direction,
            rationale: signal.rationale,
          }));
        }
      } catch {
        // fall through to fixture
      }
      if (USE_REAL_DATA) return [];
      return generateSignals();
    },
    staleTime: 30_000,
  });
}

export interface MarketIndicators {
  volatility: number;
  spread: number;
  session: string;
  features: Record<string, number>;
}

/**
 * F-06: volatility/spread/session/features indicators — all endpoints live
 * (market/volatility/{s}, spread/{s}, session/{s}, features/{s}).
 */
export function useMarketIndicators(symbol: string) {
  return useQuery({
    queryKey: ["market-indicators", symbol],
    queryFn: async (): Promise<MarketIndicators> => {
      const [vol, spread, session, features] = await Promise.all([
        get<{ volatility: string | number }>(`/market/volatility/${symbol}`),
        get<{ spread: string | number }>(`/market/spread/${symbol}`),
        get<{ session: string }>(`/market/session/${symbol}`),
        get<Record<string, number>>(`/market/features/${symbol}`),
      ]);
      return {
        volatility: num(vol?.volatility, 0),
        spread: num(spread?.spread, 0),
        session: String(session?.session ?? "unknown"),
        features: features ?? {},
      };
    },
    staleTime: 60_000,
    retry: false,
  });
}

/**
 * Correlation matrix — no backend contract exists yet (see
 * docs/15-implementation/sprint-evidence/f-sprint-4-charts.md, open item), so
 * this hook is fixture-only until the API is extended.
 */
export function useCorrelation() {
  return useQuery({
    queryKey: ["correlation"],
    queryFn: async (): Promise<{ symbols: string[]; matrix: CorrelationMatrix }> => {
      try {
        // Backend: GET /api/v1/market/correlation?symbols=..&window=.. →
        // Record<symbol, Record<symbol, float>> (symmetric). G4: backend
        // HANYA mengembalikan symbol dengan data bars — symbols diambil
        // dari response (bukan hardcoded 6) agar heatmap tidak menampilkan
        // cell 0.0 yang menyesatkan untuk symbol tanpa data.
        const matrixMap = await get<Record<string, Record<string, number>>>(
          "/market/correlation",
          { symbols: CORRELATION_SYMBOLS, window: "30" }
        );
        const activeSymbols =
          matrixMap && typeof matrixMap === "object"
            ? Object.keys(matrixMap).filter((s) => matrixMap[s] && typeof matrixMap[s] === "object")
            : [];
        if (activeSymbols.length > 0) {
          return {
            symbols: activeSymbols,
            matrix: activeSymbols.map((a) =>
              activeSymbols.map((b) => num(matrixMap[a]?.[b], 0))
            ),
          };
        }
      } catch {
        // fall through to fixture
      }
      if (USE_REAL_DATA) {
        return { symbols: CORRELATION_SYMBOLS, matrix: [] };
      }
      return {
        symbols: CORRELATION_SYMBOLS,
        matrix: generateCorrelationMatrix(CORRELATION_SYMBOLS),
      };
    },
    staleTime: 60_000,
  });
}

/* ── F-Sprint 5 surface hooks ────────────────────────────────────────── */

export function useQuote(symbol: string) {
  return useQuery({
    queryKey: ["quote", symbol],
    queryFn: async (): Promise<MarketQuote> => {
      try {
        const quote = await get<MarketData>(`/market/quote/${symbol}`);
        if (typeof quote?.symbol === "string") return toMarketQuote(quote);
      } catch {
        // fall through to empty / fixture
      }
      if (USE_REAL_DATA) {
        return { symbol, bid: 0, ask: 0, last: 0, timestamp: 0 };
      }
      return generateQuote(symbol);
    },
    staleTime: 5_000,
  });
}

export function usePositions(portfolioId: string = DEFAULT_PORTFOLIO_ID) {
  return useQuery({
    queryKey: ["positions", portfolioId],
    queryFn: async (): Promise<PositionFixture[]> => {
      try {
        const page = await get<{ items: RestPosition[] }>(`/portfolio/positions`);
        if (Array.isArray(page?.items)) {
          return page.items.map(toPositionFixture);
        }
      } catch {
        // fall through to empty / fixture
      }
      if (USE_REAL_DATA) return [];
      return generatePositions();
    },
    staleTime: 30_000,
  });
}

export function useOrders(portfolioId: string = DEFAULT_PORTFOLIO_ID) {
  return useQuery({
    queryKey: ["orders", portfolioId],
    queryFn: async (): Promise<OrderFixture[]> => {
      try {
        const page = await get<{ items: RestOrder[] }>(`/orders`);
        if (Array.isArray(page?.items)) {
          return page.items.map(toOrderFixture);
        }
      } catch {
        // fall through to empty / fixture
      }
      if (USE_REAL_DATA) return [];
      return generateOrders();
    },
    staleTime: 30_000,
  });
}

export function useOrder(orderId: string) {
  return useQuery({
    queryKey: ["order", orderId],
    queryFn: async (): Promise<OrderFixture> => {
      try {
        const order = await get<RestOrder>(`/orders/${orderId}`);
        if (typeof order?.order_id === "string") return toOrderFixture(order);
      } catch {
        // fall through to fixture
      }
      if (USE_REAL_DATA) {
        const err = new Error(`order not found: ${orderId}`);
        err.name = "NotFoundError";
        throw err;
      }
      return generateOrder(orderId);
    },
    staleTime: 30_000,
  });
}

export function useRun(runId: string) {
  return useQuery({
    queryKey: ["run", runId],
    queryFn: async (): Promise<WorkflowRun> => {
      try {
        const run = await get<RestWorkflowRun>(`/workflows/${runId}`);
        if (typeof run?.run_id === "string") return toWorkflowRun(run);
      } catch {
        // fall through to fixture
      }
      if (USE_REAL_DATA) {
        const err = new Error(`run not found: ${runId}`);
        err.name = "NotFoundError";
        throw err;
      }
      return generateRun(runId);
    },
    staleTime: 30_000,
  });
}

export function useLineage(lineageId: string) {
  return useQuery({
    queryKey: ["lineage", lineageId],
    queryFn: async (): Promise<LineageFixture> => {
      try {
        const lineage = await get<RestLineageRecord>(`/lineage/${lineageId}`);
        if (typeof lineage?.lineage_id === "string") return toLineageFixture(lineage);
      } catch {
        // fall through to fixture
      }
      if (USE_REAL_DATA) {
        const err = new Error(`lineage not found: ${lineageId}`);
        err.name = "NotFoundError";
        throw err;
      }
      return generateLineage(lineageId);
    },
    staleTime: 60_000,
  });
}

export interface JournalFilters {
  symbol?: string;
  portfolioId?: string;
  kind?: string;
}

export function useJournal(filters: JournalFilters = {}) {
  return useQuery({
    queryKey: ["journal", filters],
    queryFn: async (): Promise<JournalPage> => {
      try {
        const page = await get<{ items: RestJournalEntry[]; total: number }>("/journal", {
          limit: "50",
          ...(filters.symbol ? { symbol: filters.symbol } : {}),
          ...(filters.portfolioId ? { portfolio_id: filters.portfolioId } : {}),
          ...(filters.kind ? { kind: filters.kind } : {}),
        });
        if (Array.isArray(page?.items)) {
          return {
            entries: page.items.map(toJournalEntry),
            cursor: page.total > page.items.length ? String(page.items.length) : null,
            has_more: page.total > page.items.length,
          };
        }
      } catch {
        // fall through to fixture
      }
      if (USE_REAL_DATA) return { entries: [], cursor: null, has_more: false };
      return generateJournalEntries();
    },
    staleTime: 15_000,
  });
}

/**
 * Fetches a specific cursor page. Returns `null` when the cursor is
 * exhausted — callers hide the Load more button on `has_more === false`.
 */
export function useJournalPage(cursor: string | null, filters: JournalFilters = {}) {
  return useQuery({
    queryKey: ["journal", filters, cursor],
    queryFn: async (): Promise<JournalPage> => {
      if (cursor === null) return { entries: [], cursor: null, has_more: false };
      try {
        const page = await get<{ items: RestJournalEntry[]; total: number }>("/journal", {
          limit: "50",
          offset: cursor,
        });
        if (Array.isArray(page?.items)) {
          const seen = Number.parseInt(cursor, 10) + page.items.length;
          return {
            entries: page.items.map(toJournalEntry),
            cursor: page.total > seen ? String(seen) : null,
            has_more: page.total > seen,
          };
        }
      } catch {
        // fall through to fixture
      }
      if (USE_REAL_DATA) return { entries: [], cursor: null, has_more: false };
      return generateJournalEntries(cursor);
    },
    staleTime: 15_000,
    enabled: cursor !== null,
  });
}

export function useApiKeys() {
  return useQuery({
    queryKey: ["api-keys"],
    queryFn: async (): Promise<ApiKeyFixture[]> => {
      try {
        const items = await get<AdminKey[]>("/admin/keys");
        if (Array.isArray(items)) return items.map(toApiKeyFixture);
      } catch {
        // fall through to fixture
      }
      if (USE_REAL_DATA) return [];
      return generateApiKeys();
    },
    staleTime: 30_000,
  });
}

/**
 * Mutation hooks below call the live REST backend (admin/orders routers)
 * and write the server-confirmed result into the query cache. When the
 * backend is unreachable the error propagates to the caller, which is
 * responsible for surfacing it (toast / inline error).
 */

export function useCreateApiKey() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (
      scopes: string[]
    ): Promise<{ key_id: string; prefix: string; secret: string; scopes: string[] }> => {
      const keyId = `key-${Date.now().toString(36)}`;
      const created = await adminClient.createApiKey({
        key_id: keyId,
        name: "web console",
        scopes,
      });
      const shape = {
        key_id: created.key_id,
        prefix: `sk-${created.key_id}`,
        secret: created.secret,
        scopes: created.scopes,
      };
      queryClient.setQueryData<ApiKeyFixture[]>(["api-keys"], (current) => [
        {
          key_id: created.key_id,
          prefix: shape.prefix,
          scopes: created.scopes,
          created_at: created.created_at,
          last_used_at: null,
          revoked: false,
        },
        ...(current ?? []),
      ]);
      return shape;
    },
  });
}

export function useRevokeApiKey() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (keyId: string): Promise<void> => {
      await adminClient.revokeApiKey(keyId);
      queryClient.setQueryData<ApiKeyFixture[]>(["api-keys"], (current) =>
        (current ?? []).map((key) => (key.key_id === keyId ? { ...key, revoked: true } : key))
      );
    },
  });
}

export function useCancelOrder() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (orderId: string): Promise<void> => {
      await ordersClient.cancelOrder(orderId);
      queryClient.setQueryData<OrderFixture>(["order", orderId], (current) =>
        current ? { ...current, status: "CANCELLED" } : current
      );
      queryClient.invalidateQueries({ queryKey: ["orders"] });
    },
  });
}

/**
 * Modify an existing order (price/volume adjustment before fill).
 *
 * PATCH `/api/v1/orders/:id` per ordersClient.modifyOrder — backend
 * routers/orders.py. The server-confirmed order is mapped back into the
 * fixture shape and written into the detail + list caches.
 */
export function useModifyOrder() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({
      orderId,
      price,
      volume,
    }: {
      orderId: string;
      price?: number;
      volume?: number;
    }): Promise<OrderFixture> => {
      const updatedRest = await ordersClient.modifyOrder(orderId, { price, volume });
      const updated = toOrderFixture(updatedRest);
      queryClient.setQueryData<OrderFixture>(["order", orderId], updated);
      queryClient.setQueryData<OrderFixture[]>(["orders", DEFAULT_PORTFOLIO_ID], (list) =>
        (list ?? []).map((order) => (order.id === orderId ? updated : order))
      );
      queryClient.invalidateQueries({ queryKey: ["orders"] });
      return updated;
    },
  });
}

export type KillSwitchTier = "global" | "book" | "strategy";

export interface KillSwitchPayload {
  active: boolean;
  tier: KillSwitchTier;
  reason?: string;
}

/**
 * Engage/release the kill switch with an audit trail (tier + reason).
 *
 * POST `/api/v1/admin/kill-switch {armed, reason, tier}` per routers/admin.py.
 * The ui store is updated from the server-confirmed status; the tier field
 * is persisted backend-side and echoed back in KillSwitchStatus.
 */
export function useKillSwitch() {
  const setKillSwitch = useUiStore((s) => s.setKillSwitch);
  return useMutation({
    mutationFn: async ({ active, tier, reason }: KillSwitchPayload): Promise<void> => {
      const status = await adminClient.setKillSwitch({
        armed: active,
        reason: reason ?? "",
        tier,
      });
      setKillSwitch(status.armed);
    },
  });
}

export interface SimulateParams {
  symbol: string;
  side: "buy" | "sell";
  volume: number;
  price: number;
}

export interface SimulateResult {
  projected_nav: number;
  margin_required: number;
  pnl_change: number;
}

/**
 * What-if projection (F-03): POST /api/v1/portfolio/{id}/simulate with the
 * trade params and surface the NAV/margin impact BEFORE execution.
 */
export function useSimulateTrade() {
  return useMutation({
    mutationFn: async (params: SimulateParams): Promise<SimulateResult> => {
      const result = await portfolioClient.simulateTrade({
        portfolioId: "default",
        ...params,
      });
      return {
        projected_nav: num(result.projected_nav, 0),
        margin_required: num(result.margin_required, 0),
        pnl_change: num(result.pnl_change, 0),
      };
    },
  });
}

export interface WorkflowRunsPage {
  items: WorkflowRun[];
  total: number;
  limit: number;
  offset: number;
}

/**
 * Paginated workflow run list (F-01): GET /api/v1/workflows?limit&offset,
 * REST-first with fixture fallback (offset/limit contract, not cursor).
 */
export function useWorkflowRuns(limit = 20, offset = 0) {
  return useQuery({
    queryKey: ["workflow-runs", limit, offset],
    queryFn: async (): Promise<WorkflowRunsPage> => {
      try {
        const res = await get<{ items: RestWorkflowRun[]; total: number; limit: number; offset: number }>(
          "/workflows",
          { limit: String(limit), offset: String(offset) }
        );
        if (Array.isArray(res?.items)) {
          return {
            items: res.items.map(toWorkflowRun),
            total: res.total,
            limit: res.limit,
            offset: res.offset,
          };
        }
      } catch {
        // fall through to fixture
      }
      const fixture = Array.from({ length: Math.min(limit, 20) }, (_, i) =>
        generateRun(`run-${offset + i + 1}-fixture`, 61 + offset + i)
      );
      return { items: fixture, total: 100, limit, offset };
    },
    staleTime: 30_000,
  });
}
