import { useEffect, useState } from 'react';

import { useMarketStore, type MarketTick } from '@/stores';
import { generatePnl, mulberry32, type EquityPoint } from '@/data/fixtures';

const DEMO_SEED = 999;

export interface DemoStreams {
  lastTick: { last: number } | null;
  pnlSeries: EquityPoint[];
}

/**
 * Local demo market stream — pushes one tick per second into the market
 * store (seeded walk so behavior is reproducible) and appends a P&L point.
 * This is a stopgap until the backend SSE `/streams/market-data` endpoint
 * runs; swap for `useSSE` when the API is live (see evidence doc).
 */
export function useDemoStreams(
  enabled: boolean,
  symbol = 'XAUUSD',
  intervalMs = 1_000,
): DemoStreams {
  const upsertTick = useMarketStore((state) => state.upsertTick);
  const lastTick = useMarketStore((state) => state.ticks[symbol] ?? null);
  const [pnlSeries, setPnlSeries] = useState<EquityPoint[]>(() => generatePnl({ count: 60 }));

  useEffect(() => {
    if (!enabled) return;

    const rand = mulberry32(DEMO_SEED);
    let price = 2_400;
    const timer = setInterval(() => {
      price *= 1 + (rand() - 0.5) * 0.0006;
      const tick: MarketTick = {
        symbol,
        bid: price - 0.2,
        ask: price + 0.2,
        last: price,
        timestamp: new Date().toISOString(),
      };
      upsertTick(tick);
      setPnlSeries((prev) => {
        const last = prev[prev.length - 1]?.value ?? 0;
        const next = [
          ...prev.slice(-59),
          { time: Math.floor(Date.now() / 1000), value: last + (rand() - 0.48) * 40 },
        ];
        return next;
      });
    }, intervalMs);

    return () => clearInterval(timer);
  }, [enabled, symbol, intervalMs, upsertTick]);

  return { lastTick, pnlSeries };
}
