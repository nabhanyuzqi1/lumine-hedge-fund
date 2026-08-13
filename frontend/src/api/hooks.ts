import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { get } from "@/api/client";
import type { Timeframe } from "@/components/charts/candlestick-chart";
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
  generateApiKeySecret,
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

export const DEFAULT_PORTFOLIO_ID = "portfolio-demo";

const TIMEFRAME_SECONDS: Record<Timeframe, number> = {
  "5m": 300,
  "15m": 900,
  "1H": 3_600,
  "4H": 14_400,
};

export const CORRELATION_SYMBOLS = ["XAUUSD", "XAGUSD", "EURUSD", "GBPUSD", "USOIL", "BTCUSD"];

/**
 * Query hooks with fixture fallback: the Phase 9 backend is not implemented
 * yet, so every hook tries the REST contract first and falls back to a
 * deterministic seeded fixture on error/empty. Same seed ⇒ identical chart
 * output across sessions and tests.
 */

export function useMarketBars(symbol: string, timeframe: Timeframe) {
  return useQuery({
    queryKey: ["market-bars", symbol, timeframe],
    queryFn: async (): Promise<ChartBar[]> => {
      try {
        const bars = await get<ChartBar[]>(`/market/quotes/${symbol}`);
        if (bars.length > 0 && typeof bars[0]?.open === "number") return bars;
      } catch {
        // fall through to fixture
      }
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
        const points = await get<EquityPoint[]>(`/portfolio/${portfolioId}/equity`);
        if (points.length > 0 && typeof points[0]?.value === "number") return points;
      } catch {
        // fall through to fixture
      }
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
        const items = await get<ExposureItem[]>(`/portfolio/${portfolioId}/exposure`);
        if (items.length > 0 && typeof items[0]?.weight === "number") return items;
      } catch {
        // fall through to fixture
      }
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
        const points = await get<SignalPoint[]>(`/market/signals/${symbol}`);
        if (points.length > 0 && typeof points[0]?.confidence === "number") return points;
      } catch {
        // fall through to fixture
      }
      return generateSignals();
    },
    staleTime: 30_000,
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
    queryFn: async (): Promise<{ symbols: string[]; matrix: CorrelationMatrix }> => ({
      symbols: CORRELATION_SYMBOLS,
      matrix: generateCorrelationMatrix(CORRELATION_SYMBOLS),
    }),
    staleTime: 60_000,
  });
}

/* ── F-Sprint 5 surface hooks ────────────────────────────────────────── */

export function useQuote(symbol: string) {
  return useQuery({
    queryKey: ["quote", symbol],
    queryFn: async (): Promise<MarketQuote> => {
      try {
        const quote = await get<MarketQuote>(`/market/quotes/${symbol}/latest`);
        if (typeof quote?.last === "number") return quote;
      } catch {
        // fall through to fixture
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
        const items = await get<PositionFixture[]>(`/portfolio/${portfolioId}/positions`);
        if (items.length > 0 && typeof items[0]?.avg_entry_price === "number") return items;
      } catch {
        // fall through to fixture
      }
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
        const items = await get<OrderFixture[]>(`/portfolio/${portfolioId}/orders`);
        if (items.length > 0 && typeof items[0]?.entry_price === "number") return items;
      } catch {
        // fall through to fixture
      }
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
        const order = await get<OrderFixture>(
          `/portfolio/${DEFAULT_PORTFOLIO_ID}/orders/${orderId}`
        );
        if (typeof order?.id === "string") return order;
      } catch {
        // fall through to fixture
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
        const run = await get<WorkflowRun>(`/workflows/runs/${runId}`);
        if (typeof run?.id === "string") return run;
      } catch {
        // fall through to fixture
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
        const lineage = await get<LineageFixture>(`/lineage/${lineageId}`);
        if (typeof lineage?.lineage_id === "string") return lineage;
      } catch {
        // fall through to fixture
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
        const page = await get<JournalPage>("/journal", {
          ...(filters.symbol ? { symbol: filters.symbol } : {}),
          ...(filters.portfolioId ? { portfolio_id: filters.portfolioId } : {}),
          ...(filters.kind ? { kind: filters.kind } : {}),
        });
        if (Array.isArray(page?.entries)) return page;
      } catch {
        // fall through to fixture
      }
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
        const page = await get<JournalPage>("/journal", { cursor });
        if (Array.isArray(page?.entries)) return page;
      } catch {
        // fall through to fixture
      }
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
        const items = await get<ApiKeyFixture[]>("/admin/keys");
        if (Array.isArray(items) && items.length > 0) return items;
      } catch {
        // fall through to fixture
      }
      return generateApiKeys();
    },
    staleTime: 30_000,
  });
}

/**
 * Mutation hooks below are fixture-backed: no backend exists yet, so they
 * resolve against the deterministic generator and write the result into the
 * query cache (single source of truth for the page). Swap the body for the
 * real REST call once Phase 9 ships.
 */

export function useCreateApiKey() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (
      scopes: string[]
    ): Promise<{ key_id: string; prefix: string; secret: string; scopes: string[] }> => {
      const created = generateApiKeySecret(scopes);
      await delay(250);
      queryClient.setQueryData<ApiKeyFixture[]>(["api-keys"], (current) => [
        {
          key_id: created.key_id,
          prefix: created.prefix,
          scopes: created.scopes,
          created_at: new Date().toISOString(),
          last_used_at: null,
          revoked: false,
        },
        ...(current ?? []),
      ]);
      return created;
    },
  });
}

export function useRevokeApiKey() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (keyId: string): Promise<void> => {
      await delay(250);
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
      await delay(250);
      queryClient.setQueryData<OrderFixture>(["order", orderId], (current) =>
        current ? { ...current, status: "CANCELLED" } : current
      );
      queryClient.invalidateQueries({ queryKey: ["orders"] });
    },
  });
}

/** Minimal latency so mutation feedback (toast + cache update) is observable. */
function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
