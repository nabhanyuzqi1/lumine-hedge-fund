import type { ChartBar, EquityPoint, ExposureItem, SignalPoint } from "@/data/fixtures";
/**
 * Pure chart data transforms — deterministic inputs to chart series data.
 *
 * Every function here is side-effect free so it can be unit-tested without a
 * DOM. Lightweight-charts series expect epoch seconds (`UTCTimestamp`);
 * ECharts works with epoch milliseconds, so the ECharts-oriented helpers
 * return `[ms, value]` pairs directly.
 */
import type {
  AreaData,
  CandlestickData,
  HistogramData,
  LineData,
  UTCTimestamp,
} from "lightweight-charts";
import { CHART_COLORS } from "./chart-theme";

export function toUTCTime(seconds: number): UTCTimestamp {
  return Math.floor(seconds) as UTCTimestamp;
}

export interface CandlePayload {
  candles: CandlestickData<UTCTimestamp>[];
  volumes: HistogramData<UTCTimestamp>[];
}

/** Single bar → candle point (incremental `series.update()`). */
export function candleFromBar(bar: ChartBar): CandlestickData<UTCTimestamp> {
  return {
    time: toUTCTime(bar.time),
    open: Number.isFinite(bar.open) ? bar.open : bar.close,
    high: Number.isFinite(bar.high) ? bar.high : bar.close,
    low: Number.isFinite(bar.low) ? bar.low : bar.close,
    close: Number.isFinite(bar.close) ? bar.close : bar.open,
  };
}

/** Single bar → volume point (incremental `series.update()`). */
export function volumeFromBar(
  bar: ChartBar,
  colors: { up: string; down: string } = CHART_COLORS
): HistogramData<UTCTimestamp> {
  return {
    time: toUTCTime(bar.time),
    value: Number.isFinite(bar.volume) ? Math.max(0, bar.volume) : 0,
    color: bar.close >= bar.open ? colors.up : colors.down,
  };
}

/** Split OHLCV bars into candle + volume series. Volume bars inherit up/down color. */
export function barsToCandles(
  bars: ChartBar[],
  colors: { up: string; down: string } = CHART_COLORS
): CandlePayload {
  const candles: CandlestickData<UTCTimestamp>[] = [];
  const volumes: HistogramData<UTCTimestamp>[] = [];

  for (const bar of bars) {
    // Guard: lightweight-charts v5 throws "Value is null" saat time/value
    // NaN/null lolos (seed bars realtime bisa berisi bar in-progress atau
    // data parsial dari EA). Skip bar invalid — jangan render.
    if (!bar || !Number.isFinite(bar.time) || bar.time <= 0) continue;
    if (!Number.isFinite(bar.open) || !Number.isFinite(bar.high) ||
        !Number.isFinite(bar.low) || !Number.isFinite(bar.close)) continue;
    const time = toUTCTime(bar.time);
    candles.push({ time, open: bar.open, high: bar.high, low: bar.low, close: bar.close });
    const volume = Number.isFinite(bar.volume) ? Math.max(0, bar.volume) : 0;
    volumes.push({
      time,
      value: volume,
      color: bar.close >= bar.open ? colors.up : colors.down,
    });
  }

  return { candles, volumes };
}

/**
 * Merge a live tick into the in-progress bar: raise high, lower low, move
 * close. Pure — the caller decides whether to start a new bar (timeframe
 * aggregation) or update the last one.
 */
export function updateBarWithTick(bar: ChartBar, price: number, time?: number): ChartBar {
  return {
    ...bar,
    time: time === undefined ? bar.time : Math.max(bar.time, time),
    high: Math.max(bar.high, price),
    low: Math.min(bar.low, price),
    close: price,
  };
}

/** Equity curve / P&L sparkline → area/line series points. */
function validPoint(p: EquityPoint): p is EquityPoint {
  return (
    p != null &&
    Number.isFinite(p.time) &&
    p.time > 0 &&
    Number.isFinite(p.value)
  );
}

export function equityToArea(points: EquityPoint[]): AreaData<UTCTimestamp>[] {
  return points.filter(validPoint).map((p) => ({ time: toUTCTime(p.time), value: p.value }));
}

export function pnlToLine(points: EquityPoint[]): LineData<UTCTimestamp>[] {
  return points.filter(validPoint).map((p) => ({ time: toUTCTime(p.time), value: p.value }));
}

/**
 * Cumulative drawdown (underwater curve) derived from an equity curve:
 * `value / runningPeak - 1`, always ≤ 0. Derived, not generated, so the
 * drawdown chart can never disagree with the equity chart.
 */
export function equityToDrawdown(points: EquityPoint[]): EquityPoint[] {
  let peak = Number.NEGATIVE_INFINITY;
  return points.filter(validPoint).map((p) => {
    peak = Math.max(peak, p.value);
    return { time: p.time, value: p.value / peak - 1 };
  });
}

export interface TreemapNode {
  name: string;
  value: number;
  children?: TreemapNode[];
}

/** Exposure items → ECharts treemap: one top-level node per asset class. */
export function exposureToTreemap(items: ExposureItem[]): TreemapNode[] {
  const byClass = new Map<string, ExposureItem[]>();
  for (const item of items) {
    const list = byClass.get(item.assetClass) ?? [];
    list.push(item);
    byClass.set(item.assetClass, list);
  }

  return [...byClass.entries()]
    .map(([assetClass, members]) => ({
      name: assetClass,
      value: members.reduce((sum, m) => sum + m.weight, 0),
      children: members.map((m) => ({ name: m.symbol, value: m.weight })),
    }))
    .sort((a, b) => b.value - a.value);
}

export interface HeatmapPayload {
  /** `[rowIndex, colIndex, value]` triplets for ECharts heatmap. */
  data: [number, number, number][];
  labels: string[];
}

export function correlationToHeatmap(symbols: string[], matrix: number[][]): HeatmapPayload {
  const data: [number, number, number][] = [];
  for (let i = 0; i < symbols.length; i++) {
    for (let j = 0; j < symbols.length; j++) {
      data.push([i, j, clamp(matrix[i]?.[j] ?? 0, -1, 1)]);
    }
  }
  return { data, labels: symbols };
}

export interface SignalLine {
  name: string;
  /** `[epochMs, confidence]` pairs for ECharts line series. */
  data: [number, number][];
}

/** Analyst confidence timeline grouped per analyst, x in epoch milliseconds. */
export function confidenceToEcharts(points: SignalPoint[]): { series: SignalLine[] } {
  const byAnalyst = new Map<string, [number, number][]>();
  for (const point of points) {
    const list = byAnalyst.get(point.analyst) ?? [];
    list.push([point.time * 1000, clamp(point.confidence, 0, 1)]);
    byAnalyst.set(point.analyst, list);
  }

  const series: SignalLine[] = [...byAnalyst.entries()].map(([name, data]) => ({
    name,
    data: data.sort((a, b) => a[0] - b[0]),
  }));

  return { series };
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}
