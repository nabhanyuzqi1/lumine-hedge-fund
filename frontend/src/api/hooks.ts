import { useQuery } from '@tanstack/react-query';

import { get } from '@/api/client';
import {
  generateBars,
  generateCorrelationMatrix,
  generateEquity,
  generateExposure,
  generateSignals,
  type ChartBar,
  type CorrelationMatrix,
  type EquityPoint,
  type ExposureItem,
  type SignalPoint,
} from '@/data/fixtures';
import type { Timeframe } from '@/components/charts/candlestick-chart';

export const DEFAULT_PORTFOLIO_ID = 'portfolio-demo';

const TIMEFRAME_SECONDS: Record<Timeframe, number> = {
  '5m': 300,
  '15m': 900,
  '1H': 3_600,
  '4H': 14_400,
};

export const CORRELATION_SYMBOLS = ['XAUUSD', 'XAGUSD', 'EURUSD', 'GBPUSD', 'USOIL', 'BTCUSD'];

/**
 * Query hooks with fixture fallback: the Phase 9 backend is not implemented
 * yet, so every hook tries the REST contract first and falls back to a
 * deterministic seeded fixture on error/empty. Same seed ⇒ identical chart
 * output across sessions and tests.
 */

export function useMarketBars(symbol: string, timeframe: Timeframe) {
  return useQuery({
    queryKey: ['market-bars', symbol, timeframe],
    queryFn: async (): Promise<ChartBar[]> => {
      try {
        const bars = await get<ChartBar[]>(`/market/quotes/${symbol}`);
        if (bars.length > 0 && typeof bars[0]?.open === 'number') return bars;
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
    queryKey: ['equity-curve', portfolioId],
    queryFn: async (): Promise<EquityPoint[]> => {
      try {
        const points = await get<EquityPoint[]>(`/portfolio/${portfolioId}/equity`);
        if (points.length > 0 && typeof points[0]?.value === 'number') return points;
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
    queryKey: ['exposure', portfolioId],
    queryFn: async (): Promise<ExposureItem[]> => {
      try {
        const items = await get<ExposureItem[]>(`/portfolio/${portfolioId}/exposure`);
        if (items.length > 0 && typeof items[0]?.weight === 'number') return items;
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
    queryKey: ['signals', symbol],
    queryFn: async (): Promise<SignalPoint[]> => {
      try {
        const points = await get<SignalPoint[]>(`/market/signals/${symbol}`);
        if (points.length > 0 && typeof points[0]?.confidence === 'number') return points;
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
    queryKey: ['correlation'],
    queryFn: async (): Promise<{ symbols: string[]; matrix: CorrelationMatrix }> => ({
      symbols: CORRELATION_SYMBOLS,
      matrix: generateCorrelationMatrix(CORRELATION_SYMBOLS),
    }),
    staleTime: 60_000,
  });
}
