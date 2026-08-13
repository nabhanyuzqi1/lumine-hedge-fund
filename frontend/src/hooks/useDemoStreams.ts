import { useEffect, useState } from "react";

import { type EquityPoint, generatePnl, mulberry32 } from "@/data/fixtures";
import { type MarketTick, useMarketStore } from "@/stores";
import { useActivityStore } from "@/stores/activityStore";

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
  symbol = "XAUUSD",
  intervalMs = 1_000
): DemoStreams {
  const upsertTick = useMarketStore((state) => state.upsertTick);
  const lastTick = useMarketStore((state) => state.ticks[symbol] ?? null);
  const [pnlSeries, setPnlSeries] = useState<EquityPoint[]>(() => generatePnl({ count: 60 }));
  const appendLog = useActivityStore.getState().appendLog;

  useEffect(() => {
    if (!enabled) return;

    appendLog({ stream: "market", message: `Demo stream started for ${symbol}`, level: "info" });

    const rand = mulberry32(DEMO_SEED);
    let price = 2_400;
    let tickCount = 0;
    let timer: ReturnType<typeof setInterval> | undefined;

    // Defer the first tick until the main thread is idle so demo ticks do not
    // compete with initial render / LCP (keeps Lighthouse TBT low; fixtures
    // already render instantly, so users see no gap).
    const schedule = () => {
      timer = setInterval(() => {
        price *= 1 + (rand() - 0.5) * 0.0006;
        const tick: MarketTick = {
          symbol,
          bid: price - 0.2,
          ask: price + 0.2,
          last: price,
          timestamp: new Date().toISOString(),
        };
        upsertTick(tick);
        tickCount += 1;
        if (tickCount % 5 === 0) {
          appendLog({
            stream: "market",
            message: `${symbol} tick ${tick.last.toFixed(2)}`,
            level: "info",
          });
        }
        setPnlSeries((prev) => {
          const last = prev[prev.length - 1]?.value ?? 0;
          const next = [
            ...prev.slice(-59),
            { time: Math.floor(Date.now() / 1000), value: last + (rand() - 0.48) * 40 },
          ];
          return next;
        });
      }, intervalMs);
    };

    const requestIdle =
      typeof window.requestIdleCallback === "function"
        ? window.requestIdleCallback(schedule, { timeout: 2_000 })
        : (setTimeout(schedule, 1_000) as unknown as number);

    return () => {
      if (timer) clearInterval(timer);
      if (typeof window.cancelIdleCallback === "function") {
        window.cancelIdleCallback(requestIdle);
      } else {
        clearTimeout(requestIdle);
      }
    };
  }, [enabled, symbol, intervalMs, upsertTick, appendLog]);

  return { lastTick, pnlSeries };
}
