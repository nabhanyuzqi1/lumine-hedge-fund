import { useEffect, useRef, useState } from "react";
import {
  ColorType,
  type IChartApi,
  type ISeriesApi,
  CandlestickSeries,
  createChart,
  type CandlestickData,
  type Time,
} from "lightweight-charts";
import { ChartCard } from "@/components/charts/chart-card";
import type { ChartBar } from "@/data/fixtures";
import { useChartResize } from "@/hooks/useChartResize";
import { cn } from "@/lib/utils";

// ── Types ────────────────────────────────────────────────────────────────────

export type Timeframe = "1m" | "5m" | "15m" | "1H" | "4H" | "1D";

export interface PriceLine {
  price: number;
  color: string;
  title: string;
  lineStyle?: number;
  axisLabelVisible?: boolean;
}

export interface CandlestickChartProps {
  bars: ChartBar[];
  lastTick?: { last?: number; bid?: number; timestamp?: string } | null;
  timeframe: Timeframe;
  onTimeframeChange?: (tf: Timeframe) => void;
  height?: number;
  waitingLabel?: string;
  heikinAshi?: boolean;
  onHeikinAshiChange?: (v: boolean) => void;
  priceLines?: PriceLine[];
  replayIndex?: number | null;
  replayWindow?: number;
  /** Pair symbol untuk title chart. */
  symbol?: string;
}

const TIMEFRAMES: Timeframe[] = ["1m", "5m", "15m", "1H", "4H", "1D"];
const TIMEFRAME_SECONDS: Record<Timeframe, number> = {
  "1m": 60,
  "5m": 300,
  "15m": 900,
  "1H": 3600,
  "4H": 14400,
  "1D": 86400,
};
export const TICK_DEBOUNCE_MS = 150;

// ── Helpers (inline, no chart-transform dependency) ───────────────────────────

/** Convert ChartBar[] → CandlestickData[], filter invalid, sort by time, dedupe. */
function toCandles(bars: ChartBar[]): CandlestickData[] {
  const seen = new Set<number>();
  const out: CandlestickData[] = [];
  for (const b of bars) {
    // Guard: NaN/null crash lightweight-charts v5 "Value is null"
    if (
      !Number.isFinite(b.time) || b.time <= 0 ||
      !Number.isFinite(b.open) || !Number.isFinite(b.high) ||
      !Number.isFinite(b.low) || !Number.isFinite(b.close)
    ) continue;
    if (seen.has(b.time)) continue; // dedupe
    seen.add(b.time);
    out.push({
      time: b.time as Time,
      open: b.open,
      high: b.high,
      low: b.low,
      close: b.close,
    });
  }
  out.sort((a, b) => Number(a.time) - Number(b.time));
  return out;
}

/** Mutate a bar with a new tick price (live update). */
function applyTick(bar: CandlestickData, price: number): CandlestickData {
  return {
    ...bar,
    close: price,
    high: Math.max(bar.high, price),
    low: Math.min(bar.low, price),
  };
}

/** Heikin-Ashi: transform OHLC array. */
function heikinAshiCandles(candles: CandlestickData[]): CandlestickData[] {
  if (candles.length === 0) return [];
  const out: CandlestickData[] = [];
  let prevHa: CandlestickData | null = null;
  for (const c of candles) {
    const haClose: number = (c.open + c.high + c.low + c.close) / 4;
    const haOpen: number = prevHa ? (prevHa.open + prevHa.close) / 2 : (c.open + c.close) / 2;
    const haHigh: number = Math.max(c.high, haOpen, haClose);
    const haLow: number = Math.min(c.low, haOpen, haClose);
    const ha: CandlestickData = { time: c.time, open: haOpen, high: haHigh, low: haLow, close: haClose };
    out.push(ha);
    prevHa = ha;
  }
  return out;
}

// ── Component ─────────────────────────────────────────────────────────────────

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
  symbol = "XAUUSD",
}: CandlestickChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const [chartInstance, setChartInstance] = useState<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const lastBarCache = useRef<CandlestickData | null>(null);
  const priceLineRefs = useRef<ReturnType<ISeriesApi<"Candlestick">["createPriceLine"]>[]>([]);

  // ── Mount / unmount ────────────────────────────────────────────────────────
  useEffect(() => {
    if (!containerRef.current) return;
    const chart = createChart(containerRef.current, {
      width: containerRef.current.clientWidth,
      height,
      layout: {
        background: { type: ColorType.Solid, color: "transparent" },
        textColor: "var(--text-secondary, #a0a0a0)",
      },
      grid: {
        vertLines: { color: "var(--border-subtle, #2a2a2a)" },
        horzLines: { color: "var(--border-subtle, #2a2a2a)" },
      },
      crosshair: { mode: 0 },
      rightPriceScale: { borderColor: "var(--border-subtle, #2a2a2a)" },
      timeScale: {
        borderColor: "var(--border-subtle, #2a2a2a)",
        timeVisible: true,
        secondsVisible: false,
      },
      handleScroll: { vertTouchDrag: false },
      handleScale: { axisPressedMouseMove: false },
    });
    const series = chart.addSeries(CandlestickSeries, {
      upColor: "var(--up, #22c55e)",
      downColor: "var(--down, #ef4444)",
      borderUpColor: "var(--up, #22c55e)",
      borderDownColor: "var(--down, #ef4444)",
      wickUpColor: "var(--up, #22c55e)",
      wickDownColor: "var(--down, #ef4444)",
    });
    chartRef.current = chart;
    setChartInstance(chart);
    seriesRef.current = series;
    lastBarCache.current = null;

    return () => {
      chart.remove();
      chartRef.current = null;
      setChartInstance(null);
      seriesRef.current = null;
    };
  }, [height]);

  // ── Resize ─────────────────────────────────────────────────────────────────
  useChartResize(chartInstance, containerRef);

  // ── Bars → setData ─────────────────────────────────────────────────────────
  useEffect(() => {
    const series = seriesRef.current;
    if (!series) return;
    if (bars.length === 0) return;
    let candles = toCandles(bars);
    if (heikinAshi) candles = heikinAshiCandles(candles);
    if (candles.length === 0) return;
    series.setData(candles);
    lastBarCache.current = candles[candles.length - 1] ?? null;
  }, [bars, heikinAshi]);

  // ── Live tick → debounced bar update ───────────────────────────────────────
  useEffect(() => {
    if (!lastTick) return;
    if (replayIndex != null) return;
    const series = seriesRef.current;
    if (!series) return;
    const price = lastTick.last ?? lastTick.bid;
    if (price == null || !Number.isFinite(price) || price <= 0) return;

    const timer = setTimeout(() => {
      if (!lastBarCache.current) return;
      const updated = applyTick(lastBarCache.current, price);
      lastBarCache.current = updated;
      series.update(updated);
    }, TICK_DEBOUNCE_MS);

    return () => clearTimeout(timer);
  }, [lastTick, replayIndex]);

  // ── Price lines ────────────────────────────────────────────────────────────
  useEffect(() => {
    const series = seriesRef.current;
    if (!series) return;
    // Remove old price lines
    for (const pl of priceLineRefs.current) series.removePriceLine(pl);
    priceLineRefs.current = [];
    // Add new ones
    // Guard: createPriceLine mungkin undefined (mock/jsdom) — skip aman.
    priceLineRefs.current = priceLines
      .map((pl) => {
        try {
          return (series as unknown as {
            createPriceLine?: (opts: object) => object | null;
          }).createPriceLine?.({
            price: pl.price,
            color: pl.color,
            title: pl.title,
            lineStyle: pl.lineStyle ?? 2,
            axisLabelVisible: pl.axisLabelVisible ?? true,
          }) as ReturnType<ISeriesApi<"Candlestick">["createPriceLine"]> | null;
        } catch {
          return null;
        }
      })
      .filter((pl): pl is ReturnType<ISeriesApi<"Candlestick">["createPriceLine"]> => pl != null);
    return () => {
      for (const pl of priceLineRefs.current) series.removePriceLine(pl);
      priceLineRefs.current = [];
    };
  }, [priceLines]);

  // ── Replay index ───────────────────────────────────────────────────────────
  useEffect(() => {
    const chart = chartRef.current;
    if (!chart) return;
    if (replayIndex != null && bars.length > 0) {
      const candles = toCandles(bars);
      const target = candles[replayIndex] ?? null;
      if (target) {
        chart.timeScale().setVisibleRange({
          from: (Number(target.time) - 3600) as Time,
          to: target.time,
        });
      }
    }
  }, [replayIndex, bars]);

  // ── Stale detection ────────────────────────────────────────────────────────
  const tickPrice = lastTick?.last ?? lastTick?.bid;
  const tickFresh =
    lastTick != null &&
    tickPrice != null &&
    Number.isFinite(tickPrice) &&
    Date.now() - Date.parse(lastTick.timestamp ?? "") < 30_000;
  const isStale = bars.length > 0 && waitingLabel != null && !tickFresh;

  return (
    <ChartCard
      title={`${symbol} — Price Action`}
      description={`${timeframe} candlesticks · volume overlay${isStale ? ` · last bar: ${new Date((bars[bars.length - 1]!.time) * 1000).toLocaleDateString()}` : ""}`}
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
              aria-pressed={tf === timeframe}
              onClick={() => onTimeframeChange?.(tf)}
              className={cn(
                "rounded px-2 py-1 text-[11px] font-medium transition-colors",
                tf === timeframe
                  ? "bg-accent text-white shadow-sm"
                  : "text-text-secondary hover:text-text-primary"
              )}
            >
              {tf}
            </button>
          ))}
          <span className="mx-1 h-4 w-px bg-border-subtle" />
          <button
            type="button"
            aria-pressed={heikinAshi}
            onClick={() => onHeikinAshiChange?.(!heikinAshi)}
            className={cn(
              "rounded px-2 py-1 text-[11px] font-medium transition-colors",
              heikinAshi
                ? "bg-accent text-white shadow-sm"
                : "text-text-secondary hover:text-text-primary"
            )}
            title="Toggle Heikin-Ashi"
          >
            HA
          </button>
        </div>
      }
    >
      {isStale && (
        <div className="pointer-events-none absolute inset-0 z-10 flex items-center justify-center">
          <span className="rounded-md bg-bg-overlay/80 px-3 py-1.5 text-xs text-text-tertiary backdrop-blur-sm">
            {waitingLabel}
          </span>
        </div>
      )}
      <div
        ref={containerRef}
        className="relative"
        style={{ height }}
        data-testid="candlestick-chart"
      />
    </ChartCard>
  );
}

// ── Re-export ─────────────────────────────────────────────────────────────────
export { TIMEFRAMES, TIMEFRAME_SECONDS };