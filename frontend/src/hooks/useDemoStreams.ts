import { useEffect, useState } from "react";

import { type EquityPoint, generatePnl, mulberry32 } from "@/data/fixtures";
import { type CandlestickBar, type MarketTick, useMarketStore } from "@/stores";
import { useActivityStore } from "@/stores/activityStore";

const DEMO_SEED = 999;

export interface DemoStreams {
  lastTick: { last: number } | null;
  bars: CandlestickBar[];
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
  const [bars, setBars] = useState<CandlestickBar[]>([]);
  const [pnlSeries, setPnlSeries] = useState<EquityPoint[]>(() => generatePnl({ count: 60 }));
  const appendLog = useActivityStore.getState().appendLog;

  useEffect(() => {
    if (!enabled) return;

    appendLog({ stream: "market", message: `Demo stream started for ${symbol}`, level: "info" });

    const rand = mulberry32(DEMO_SEED);
    let price = 2400;
    let tickCount = 0;
    let timer: ReturnType<typeof setInterval> | undefined;
    let openPrice = price;
    let barStartTime = Date.now();

    // Fixed-window limits to prevent unbounded growth — old data evicted as new arrives
    const MAX_BARS = 100;
    const MAX_PNL_POINTS = 60;

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

        // Cap ticks per symbol to avoid memory bloat
        upsertTick(tick);
        tickCount += 1;

        // Build candlestick bars every 5 ticks (~5 seconds at default interval)
        if (tickCount % 5 === 0) {
          const closeTime = Date.now();
          setBars((prev) => [
            ...prev.slice(-MAX_BARS + 1),
            {
              time: Math.floor(barStartTime / 1000),
              open: openPrice,
              high: Math.max(openPrice, price) + 0.5,
              low: Math.min(openPrice, price) - 0.5,
              close: price,
              volume: 1000 + Math.floor(rand() * 9000),
            },
          ]);
          openPrice = price;
          barStartTime = closeTime;
        }
        if (tickCount % 5 === 0) {
          appendLog({
            stream: "market",
            message: `${symbol} tick ${tick.last.toFixed(2)}`,
            level: "info",
          });
        }
        setPnlSeries((prev) => {
          const last = prev[prev.length - 1]?.value ?? 0;
          return [...prev.slice(-MAX_PNL_POINTS + 1), { time: Math.floor(Date.now() / 1000), value: last + (rand() - 0.48) * 40 }];
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

  return { lastTick, bars, pnlSeries };
}
