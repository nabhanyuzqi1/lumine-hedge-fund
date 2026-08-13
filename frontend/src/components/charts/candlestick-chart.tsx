import { useEffect, useRef, useState } from "react";

import {
  CandlestickSeries,
  HistogramSeries,
  type IChartApi,
  type ISeriesApi,
  createChart,
} from "lightweight-charts";

import { ChartCard } from "@/components/charts/chart-card";
import type { ChartBar } from "@/data/fixtures";
import { useChartResize } from "@/hooks/useChartResize";
import { buildLwcOptions, getChartColors } from "@/lib/chart-theme";
import {
  barsToCandles,
  candleFromBar,
  updateBarWithTick,
  volumeFromBar,
} from "@/lib/chart-transform";
import { cn } from "@/lib/utils";

export const TIMEFRAMES = ["5m", "15m", "1H", "4H"] as const;
export type Timeframe = (typeof TIMEFRAMES)[number];

/** Batch live ticks into one series update — exit criterion: <150ms switch, no dropped frames. */
export const TICK_DEBOUNCE_MS = 100;

export interface CandlestickChartProps {
  bars: ChartBar[];
  /** Live tick used to mutate the in-progress bar (debounced). */
  lastTick?: { last: number } | null;
  timeframe: Timeframe;
  onTimeframeChange?: (timeframe: Timeframe) => void;
  height?: number;
}

/**
 * XAUUSD candlestick pane with volume overlay (lightweight-charts v5):
 * static series data on `bars` change, debounced incremental `series.update()`
 * on live ticks, timeframe selector in the card toolbar.
 */
export function CandlestickChart({
  bars,
  lastTick,
  timeframe,
  onTimeframeChange,
  height = 360,
}: CandlestickChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const seriesRef = useRef<{
    candles: ISeriesApi<"Candlestick"> | null;
    volumes: ISeriesApi<"Histogram"> | null;
  }>({ candles: null, volumes: null });
  const lastBarRef = useRef<ChartBar | null>(null);
  const [chart, setChart] = useState<IChartApi | null>(null);

  // Chart instance + series creation — runs once per mount.
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const colors = getChartColors();
    const chartInstance = createChart(container, buildLwcOptions());
    const candles = chartInstance.addSeries(CandlestickSeries, {
      upColor: colors.up,
      downColor: colors.down,
      borderUpColor: colors.up,
      borderDownColor: colors.down,
      wickUpColor: colors.up,
      wickDownColor: colors.down,
    });
    const volumes = chartInstance.addSeries(HistogramSeries, {
      priceFormat: { type: "volume" },
      priceScaleId: "",
    });
    chartInstance.priceScale("").applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } });

    seriesRef.current = { candles, volumes };
    setChart(chartInstance);

    return () => {
      chartInstance.remove();
      seriesRef.current = { candles: null, volumes: null };
      lastBarRef.current = null;
    };
  }, []);

  useChartResize(chart, containerRef);

  // Full re-render when the bar set changes (timeframe switch, refetch).
  useEffect(() => {
    const { candles, volumes } = seriesRef.current;
    if (!candles || !volumes || bars.length === 0) return;
    const payload = barsToCandles(bars);
    candles.setData(payload.candles);
    volumes.setData(payload.volumes);
    lastBarRef.current = bars[bars.length - 1] ?? null;
  }, [bars]);

  // Debounced live tick → mutate the in-progress bar in place.
  useEffect(() => {
    if (!lastTick) return;
    const timer = setTimeout(() => {
      const bar = lastBarRef.current;
      const { candles, volumes } = seriesRef.current;
      if (!bar || !candles || !volumes) return;
      const updated = updateBarWithTick(bar, lastTick.last);
      lastBarRef.current = updated;
      candles.update(candleFromBar(updated));
      volumes.update(volumeFromBar(updated));
    }, TICK_DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [lastTick]);

  return (
    <ChartCard
      title="XAUUSD — Price Action"
      description={`${timeframe} candlesticks · volume overlay`}
      toolbar={
        <div
          role="group"
          aria-label="Timeframe"
          className="flex items-center rounded-md border border-border-subtle bg-bg-overlay p-0.5"
        >
          {TIMEFRAMES.map((tf) => (
            <button
              key={tf}
              type="button"
              onClick={() => onTimeframeChange?.(tf)}
              aria-pressed={tf === timeframe}
              className={cn(
                "rounded px-2 py-1 font-mono text-[11px] transition-colors",
                tf === timeframe
                  ? "bg-accent text-white"
                  : "text-text-muted hover:text-text-primary"
              )}
            >
              {tf}
            </button>
          ))}
        </div>
      }
      height={height}
    >
      <div ref={containerRef} className="h-full w-full" />
    </ChartCard>
  );
}
