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
  heikinAshiToCandles,
  updateBarWithTick,
  volumeFromBar,
} from "@/lib/chart-transform";
import { cn } from "@/lib/utils";

export const TIMEFRAMES = ["1m", "5m", "15m", "1H", "4H", "1D"] as const;
export type Timeframe = (typeof TIMEFRAMES)[number];

/** Batch live ticks into one series update — exit criterion: <150ms switch, no dropped frames. */
export const TICK_DEBOUNCE_MS = 100;

export interface PriceLine {
  price: number;
  title: string;
  color?: string;
}

export interface CandlestickChartProps {
  bars: ChartBar[];
  /** Live tick used to mutate the in-progress bar (debounced). */
  lastTick?: { last?: number; bid?: number; timestamp?: string } | null;
  timeframe: Timeframe;
  onTimeframeChange?: (timeframe: Timeframe) => void;
  height?: number;
  /** Fallback label saat data live belum masuk/stale (market tutup dll). */
  waitingLabel?: string;
  /** T5b: Heikin-Ashi toggle (transform OHLC → HA). */
  heikinAshi?: boolean;
  onHeikinAshiChange?: (v: boolean) => void;
  /** T5b: price lines (TP/SL/Entry) via createPriceLine. */
  priceLines?: PriceLine[];
  /** T5c: replay mode — index bar aktif (null = normal). Saat aktif,
   *  chart menampilkan window [index-window, index] via visible range. */
  replayIndex?: number | null;
  replayWindow?: number;
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
  heikinAshi = false,
  onHeikinAshiChange,
  priceLines = [],
  replayIndex = null,
  replayWindow = 80,
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

  // T5c: replay — visible range mengekor index aktif. Replay aktif →
  // live tick dibekukan (guard di bawah).
  useEffect(() => {
    if (!chart || replayIndex == null) return;
    const total = bars.length;
    if (total === 0) return;
    const from = Math.max(0, replayIndex - replayWindow);
    chart.timeScale().setVisibleLogicalRange({
      from,
      to: Math.max(from + 1, replayIndex),
    });
  }, [chart, replayIndex, replayWindow, bars.length]);

  // T5b: price lines (TP/SL/Entry) — createPriceLine per level.
  // Recreate saat daftar level berubah (hapus semua → create ulang).
  // PITFALL (18 Aug 2026): parent pass array BARU tiap render (positions
  // refetch 1s) → recreate price line tiap detik → WebGL churn →
  // browser renderer crash STATUS_BREAKPOINT. Fix: bandingkan JSON isi.
  const priceLinesKey = JSON.stringify(priceLines);
  const prevKeyRef = useRef("");
  useEffect(() => {
    const { candles } = seriesRef.current;
    if (!candles) return;
    if (prevKeyRef.current === priceLinesKey) return;
    prevKeyRef.current = priceLinesKey;
    const created = priceLines.map((pl) => {
      if (!Number.isFinite(pl.price) || pl.price <= 0) return null;
      return candles.createPriceLine({
        price: pl.price,
        title: pl.title,
        color: pl.color ?? "#f59e0b",
        lineWidth: 1 as const,
        lineStyle: 2 as const,
        axisLabelVisible: true,
      });
    });
    return () => {
      for (const line of created) {
        if (line) candles.removePriceLine(line);
      }
    };
  }, [priceLinesKey, priceLines]);

  // Full re-render when the bar set changes (timeframe switch, refetch).
  useEffect(() => {
    const { candles, volumes } = seriesRef.current;
    if (!candles || !volumes || bars.length === 0) return;
    // T5b: Heikin-Ashi mode → transform OHLC ke HA sebelum render.
    const payload = heikinAshi
      ? { candles: heikinAshiToCandles(bars), volumes: barsToCandles(bars).volumes }
      : barsToCandles(bars);
    candles.setData(payload.candles);
    volumes.setData(payload.volumes);
    lastBarRef.current = bars[bars.length - 1] ?? null;
  }, [bars, heikinAshi]);

  // Debounced live tick → mutate the in-progress bar in place.
    useEffect(() => {
      if (!lastTick) return;
      // T5c: replay aktif → jangan mutasi bar live (frozen snapshot).
      if (replayIndex != null) return;
      const timer = setTimeout(() => {
        const bar = lastBarRef.current;
        const { candles, volumes } = seriesRef.current;
        if (!bar || !candles || !volumes) return;
        // Guard: lastTick.last null/NaN (SSE partial data) → fallback bid,
        // lalu skip kalau keduanya invalid (jangan crash "Value is null").
        const price = lastTick.last ?? (lastTick as { bid?: number }).bid;
        if (price == null || !Number.isFinite(price) || price <= 0) return;
        const updated = updateBarWithTick(bar, price);
        lastBarRef.current = updated;
        candles.update(candleFromBar(updated));
        volumes.update(volumeFromBar(updated));
      }, TICK_DEBOUNCE_MS);
      return () => clearTimeout(timer);
    }, [lastTick, replayIndex]);

    // Data freshness: TANPA tick live dalam 2× interval → stale. PITFALL
    // (17 Aug 2026): logika lama pakai umur bar terakhir vs interval —
    // untuk 1H/4H bar terakhir selalu "baru" saat market buka TAPI bar
    // terakhir itu wajar lebih tua dari 10 menit (bar 4H berganti tiap 4
    // jam) → overlay "market closed" tampil padahal market BUKA dan chart
    // malah tidak live. Sebaliknya dengan live tick: kalau EA kirim tick
    // <30s lalu, market jelas buka → jangan stale.
    // Freshness: tick live <30s → market BUKA, pasti tidak stale (18 Aug).
    // lastTick.last null → fallback bid (EA kirim bid/ask; last di-set
    // backend = bid). Umur bar terakhir TIDAK dipakai (bar 4H wajar tua).
    const tickPrice = lastTick?.last ?? lastTick?.bid;
    const tickFresh =
      lastTick != null &&
      tickPrice != null &&
      Number.isFinite(tickPrice) &&
      Date.now() - Date.parse(lastTick.timestamp ?? "") < 30_000;
    const isStale = bars.length > 0 && waitingLabel != null && !tickFresh;

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
          {onHeikinAshiChange && (
            <button
              type="button"
              onClick={() => onHeikinAshiChange(!heikinAshi)}
              aria-pressed={heikinAshi}
              className={cn(
                "ml-1 rounded px-2 py-1 font-mono text-[11px] transition-colors",
                heikinAshi
                  ? "bg-cyan-500/20 text-cyan-300"
                  : "text-text-muted hover:text-text-primary"
              )}
            >
              HA
            </button>
          )}
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
