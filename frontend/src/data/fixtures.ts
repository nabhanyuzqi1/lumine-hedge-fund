/**
 * Deterministic chart fixtures — seeded PRNG (mulberry32) generators for the
 * chart panes. Backend REST endpoints for candlesticks, equity, exposure and
 * signals exist in contract (docs/09-api) but are not implemented yet, so the
 * dashboard renders from these fixtures until the API hooks receive real
 * data. Same seed ⇒ same output — tests and screenshots are reproducible.
 */

export interface ChartBar {
  /** Epoch seconds (UTC). */
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface EquityPoint {
  /** Epoch seconds (UTC). */
  time: number;
  value: number;
}

export interface ExposureItem {
  symbol: string;
  assetClass: string;
  weight: number;
}

export interface SignalPoint {
  /** Epoch seconds (UTC). */
  time: number;
  analyst: string;
  confidence: number;
}

export type CorrelationMatrix = number[][];

/** mulberry32 — tiny seeded PRNG; deterministic across platforms. */
export function mulberry32(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

export interface BarsOptions {
  seed?: number;
  count?: number;
  /** Epoch seconds of the first bar. */
  startTime?: number;
  /** Bar interval in seconds (300 = 5m, default XAUUSD pane). */
  intervalSec?: number;
  basePrice?: number;
  /** Per-bar volatility — relative step of the random walk. */
  volatility?: number;
  baseVolume?: number;
}

export function generateBars(options: BarsOptions = {}): ChartBar[] {
  const {
    seed = 42,
    count = 180,
    startTime = 1_720_000_000,
    intervalSec = 300,
    basePrice = 2_400,
    volatility = 0.0012,
    baseVolume = 1_200,
  } = options;
  const rand = mulberry32(seed);
  const bars: ChartBar[] = [];
  let price = basePrice;

  for (let i = 0; i < count; i++) {
    const open = price;
    const close = open * (1 + (rand() - 0.5) * volatility);
    const high = Math.max(open, close) * (1 + rand() * volatility * 0.5);
    const low = Math.min(open, close) * (1 - rand() * volatility * 0.5);
    bars.push({
      time: startTime + i * intervalSec,
      open,
      high,
      low,
      close,
      volume: Math.round(baseVolume * (0.5 + rand())),
    });
    price = close;
  }

  return bars;
}

export interface EquityOptions {
  seed?: number;
  count?: number;
  startTime?: number;
  intervalSec?: number;
  startValue?: number;
  /** Per-step relative drift. */
  drift?: number;
  /** Per-step relative volatility. */
  volatility?: number;
}

export function generateEquity(options: EquityOptions = {}): EquityPoint[] {
  const {
    seed = 7,
    count = 180,
    startTime = 1_720_000_000,
    intervalSec = 86_400,
    startValue = 1_000_000,
    drift = 0.0006,
    volatility = 0.012,
  } = options;
  const rand = mulberry32(seed);
  const points: EquityPoint[] = [];
  let value = startValue;

  for (let i = 0; i < count; i++) {
    value *= 1 + drift + (rand() - 0.5) * volatility;
    points.push({ time: startTime + i * intervalSec, value });
  }

  return points;
}

export interface ExposureOptions {
  seed?: number;
}

const DEFAULT_EXPOSURE: ExposureItem[] = [
  { symbol: 'XAUUSD', assetClass: 'Metals', weight: 0.38 },
  { symbol: 'XAGUSD', assetClass: 'Metals', weight: 0.08 },
  { symbol: 'EURUSD', assetClass: 'FX', weight: 0.16 },
  { symbol: 'GBPUSD', assetClass: 'FX', weight: 0.09 },
  { symbol: 'USOIL', assetClass: 'Energy', weight: 0.12 },
  { symbol: 'BTCUSD', assetClass: 'Crypto', weight: 0.17 },
];

export function generateExposure(options: ExposureOptions = {}): ExposureItem[] {
  const { seed = 11 } = options;
  const rand = mulberry32(seed);
  // Jitter the fixed skeleton so the treemap is not pixel-identical across runs.
  const total = DEFAULT_EXPOSURE.reduce((sum, item) => sum + item.weight, 0);
  return DEFAULT_EXPOSURE.map((item) => {
    const jittered = clamp(item.weight * (0.92 + rand() * 0.16), 0.01, 0.6);
    return { ...item, weight: jittered };
  }).map((item) => ({ ...item, weight: item.weight / (total * 0.98) }));
}

export function generateCorrelationMatrix(symbols: string[], seed = 23): CorrelationMatrix {
  const rand = mulberry32(seed);
  const n = symbols.length;
  const matrix: CorrelationMatrix = Array.from({ length: n }, () => Array(n).fill(0));

  for (let i = 0; i < n; i++) {
    matrix[i]![i] = 1;
    for (let j = i + 1; j < n; j++) {
      const value = clamp((rand() - 0.3) * 1.4, -0.7, 0.95);
      matrix[i]![j] = value;
      matrix[j]![i] = value;
    }
  }

  return matrix;
}

export interface SignalsOptions {
  seed?: number;
  count?: number;
  startTime?: number;
  intervalSec?: number;
  analysts?: string[];
}

export const DEFAULT_ANALYSTS = ['technical', 'macro', 'news', 'smc'] as const;

export function generateSignals(options: SignalsOptions = {}): SignalPoint[] {
  const {
    seed = 3,
    count = 120,
    startTime = 1_720_000_000,
    intervalSec = 300,
    analysts = [...DEFAULT_ANALYSTS],
  } = options;
  const rand = mulberry32(seed);
  const points: SignalPoint[] = [];
  const levels = new Map<string, number>();

  for (const analyst of analysts) {
    levels.set(analyst, 0.4 + rand() * 0.3);
  }

  for (let i = 0; i < count; i++) {
    for (const analyst of analysts) {
      const level = (levels.get(analyst) ?? 0.5) + (rand() - 0.5) * 0.08;
      const clamped = clamp(level, 0.05, 0.95);
      levels.set(analyst, clamped);
      points.push({ time: startTime + i * intervalSec, analyst, confidence: clamped });
    }
  }

  return points;
}

export interface PnlOptions {
  seed?: number;
  count?: number;
  startTime?: number;
  intervalSec?: number;
  startValue?: number;
  volatility?: number;
}

export function generatePnl(options: PnlOptions = {}): EquityPoint[] {
  const {
    seed = 5,
    count = 60,
    startTime = 1_720_000_000,
    intervalSec = 1,
    startValue = 0,
    volatility = 900,
  } = options;
  const rand = mulberry32(seed);
  const points: EquityPoint[] = [];
  let value = startValue;

  for (let i = 0; i < count; i++) {
    value += (rand() - 0.48) * volatility;
    points.push({ time: startTime + i * intervalSec, value });
  }

  return points;
}
