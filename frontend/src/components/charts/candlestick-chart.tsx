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
  /** Fallback label saat data live belum masuk/stale (market tutup dll). */
  waitingLabel?: string;
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
  waitingLabel,
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

  // Forward wheel events to the page scroller so the chart doesn't trap
  // mouse-wheel scroll. lightweight-charts registers a non-passive wheel
  // listener that swallows events — we capture them first (capture phase)
  // and mirror the deltaY to the nearest overflow-y-auto ancestor.
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    const onWheel = (e: WheelEvent) => {
      // Find the nearest scrollable ancestor outside the chart container
      let el: HTMLElement | null = container.parentElement;
      while (el) {
        const style = window.getComputedStyle(el);
        const overflow = style.overflowY;
        if ((overflow === "auto" || overflow === "scroll") && el.scrollHeight > el.clientHeight) {
          el.scrollBy({ top: e.deltaY, behavior: "auto" });
          break;
        }
        el = el.parentElement;
      }
    };
    container.addEventListener("wheel", onWheel, { passive: true, capture: true });
    return () => container.removeEventListener("wheel", onWheel, { capture: true });
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
        // Guard: lastTick.last null/NaN (SSE partial data) → skip, jangan
        // crash lightweight-charts "Value is null".
        const price = lastTick.last;
        if (price == null || !Number.isFinite(price) || price <= 0) return;
        const updated = updateBarWithTick(bar, price);
        lastBarRef.current = updated;
        candles.update(candleFromBar(updated));
        volumes.update(volumeFromBar(updated));
      }, TICK_DEBOUNCE_MS);
      return () => clearTimeout(timer);
    }, [lastTick]);

    // Data freshness: TANPA tick live dalam 2× interval → stale. PITFALL
    // (17 Aug 2026): logika lama pakai umur bar terakhir vs interval —
    // untuk 1H/4H bar terakhir selalu "baru" saat market buka TAPI bar
    // terakhir itu wajar lebih tua dari 10 menit (bar 4H berganti tiap 4
    // jam) → overlay "market closed" tampil padahal market BUKA dan chart
    // malah tidak live. Sebaliknya dengan live tick: kalau EA kirim tick
    // <30s lalu, market jelas buka → jangan stale.
    const isStale =
      bars.length > 0 &&
      waitingLabel != null &&
      // Live tick lebih baru dari 30 detik → market buka, pasti tidak stale.
      (lastTick == null ||
        lastTick.last == null ||
        !Number.isFinite(lastTick.last) ||
        Date.now() - (bars[bars.length - 1]!.time + (timeframe === "5m" ? 300 : timeframe === "15m" ? 900 : timeframe === "1H" ? 3600 : 14400)) * 1000 >
          (timeframe === "1H" || timeframe === "4H" ? 2 * 60 * 60_000 : 10 * 60_000));

  return (
    <ChartCard
      title="XAUUSD — Price Action"
      description={`${timeframe} candlesticks · volume overlay${isStale && bars.length > 0 ? ` · last bar: ${new Date((bars[bars.length - 1]!.time) * 1000).toLocaleDateString()}` : ""}`}
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
            <div
              ref={containerRef}
              className="h-full w-full"
              style={{ touchAction: "none" }}
            />
            {isStale && (
              <div className="pointer-events-none absolute inset-0 flex items-center justify-center">
                <div className="rounded-md border border-amber-500/30 bg-bg-base/80 px-4 py-2 font-mono text-[11px] uppercase tracking-[0.2em] text-amber-400 backdrop-blur">
                  {waitingLabel}
                </div>
              </div>
            )}
          </ChartCard>
  );
}
