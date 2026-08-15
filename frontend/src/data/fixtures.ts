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
  direction?: "bullish" | "bearish" | "neutral";
  rationale?: string;
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
  { symbol: "XAUUSD", assetClass: "Metals", weight: 0.38 },
  { symbol: "XAGUSD", assetClass: "Metals", weight: 0.08 },
  { symbol: "EURUSD", assetClass: "FX", weight: 0.16 },
  { symbol: "GBPUSD", assetClass: "FX", weight: 0.09 },
  { symbol: "USOIL", assetClass: "Energy", weight: 0.12 },
  { symbol: "BTCUSD", assetClass: "Crypto", weight: 0.17 },
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

export const DEFAULT_ANALYSTS = ["technical", "macro", "news", "smc"] as const;

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

/* ── F-Sprint 5 surface fixtures ─────────────────────────────────────── */

export interface MarketQuote {
  symbol: string;
  bid: number;
  ask: number;
  last: number;
  /** Epoch seconds (UTC). */
  timestamp: number;
}

export function generateQuote(symbol = "XAUUSD", seed = 31): MarketQuote {
  const rand = mulberry32(seed);
  const last = 2_400 + (rand() - 0.5) * 40;
  const spread = 0.18 + rand() * 0.12;
  return {
    symbol,
    bid: last - spread / 2,
    ask: last + spread / 2,
    last,
    timestamp: 1_720_000_000,
  };
}

export const ORDER_STATUSES = [
  "RECEIVED",
  "VALIDATED",
  "RISK_CHECK",
  "ACTIVE",
  "FILLED",
  "CANCELLED",
  "REJECTED",
] as const;
export type OrderStatus = (typeof ORDER_STATUSES)[number];

export const TERMINAL_ORDER_STATUSES: readonly OrderStatus[] = ["FILLED", "CANCELLED", "REJECTED"];

export interface OrderLifecycleEvent {
  status: OrderStatus;
  /** ISO timestamp. */
  timestamp: string;
  note?: string;
}

export interface OrderFixture {
  id: string;
  portfolio_id: string;
  symbol: string;
  side: "BUY" | "SELL";
  quantity: number;
  type: "MARKET" | "LIMIT" | "STOP";
  status: OrderStatus;
  entry_price: number;
  current_price: number;
  pnl: number;
  created_at: string;
  lifecycle: OrderLifecycleEvent[];
}

const ORDER_STATUS_SEQUENCE: OrderStatus[] = ["RECEIVED", "VALIDATED", "RISK_CHECK", "ACTIVE"];

export function generateOrder(id: string, seed = 47): OrderFixture {
  const rand = mulberry32(seed);
  const side: "BUY" | "SELL" = rand() > 0.5 ? "BUY" : "SELL";
  const quantity = Math.round((0.05 + rand() * 1.4) * 100) / 100;
  const entry = 2_400 + (rand() - 0.5) * 60;
  const current = entry * (1 + (rand() - 0.5) * 0.02);
  const base = 1_720_000_000 + Math.floor(rand() * 400_000);

  // Terminal status drawn from the full set; RECEIVED..ACTIVE progress seeded.
  const roll = rand();
  const status: OrderStatus =
    roll < 0.4 ? "FILLED" : roll < 0.55 ? "CANCELLED" : roll < 0.65 ? "REJECTED" : "ACTIVE";

  const progressed: OrderStatus[] = ORDER_STATUS_SEQUENCE.filter((s) =>
    status === "ACTIVE" ? s !== "ACTIVE" : true
  );

  const lifecycle: OrderLifecycleEvent[] = progressed.map((status_, i) => ({
    status: status_,
    timestamp: new Date((base + i * 3_000) * 1000).toISOString(),
    note: status_ === "RISK_CHECK" ? "Exposure within risk budget" : undefined,
  }));
  if (status !== "ACTIVE") {
    lifecycle.push({
      status,
      timestamp: new Date((base + progressed.length * 3_000) * 1000).toISOString(),
      note: status === "REJECTED" ? "Risk veto — drawdown guard" : undefined,
    });
  }

  return {
    id,
    portfolio_id: "portfolio-demo",
    symbol: "XAUUSD",
    side,
    quantity,
    type: rand() > 0.5 ? "MARKET" : "LIMIT",
    status,
    entry_price: entry,
    current_price: current,
    pnl: side === "BUY" ? (current - entry) * quantity : (entry - current) * quantity,
    created_at: new Date(base * 1000).toISOString(),
    lifecycle,
  };
}

export interface PositionFixture {
  id: string;
  portfolio_id: string;
  symbol: string;
  side: "LONG" | "SHORT";
  quantity: number;
  avg_entry_price: number;
  current_price: number;
  unrealized_pnl: number;
  updated_at: string;
}

export function generatePositions(seed = 43): PositionFixture[] {
  const rand = mulberry32(seed);
  const symbols = ["XAUUSD", "XAGUSD", "EURUSD", "BTCUSD", "USOIL"];
  const base = 1_720_000_000;
  return symbols.map((symbol, i) => {
    const side: "LONG" | "SHORT" = rand() > 0.35 ? "LONG" : "SHORT";
    const avg = 2_400 + (rand() - 0.5) * 500;
    const qty = Math.round((0.1 + rand() * 1.8) * 100) / 100;
    const current = avg * (1 + (rand() - 0.5) * 0.03);
    const pnl = (side === "LONG" ? current - avg : avg - current) * qty;
    return {
      id: `pos-${String(i + 1).padStart(3, "0")}`,
      portfolio_id: "portfolio-demo",
      symbol,
      side,
      quantity: qty,
      avg_entry_price: avg,
      current_price: current,
      unrealized_pnl: Math.round(pnl * 100) / 100,
      updated_at: new Date((base - i * 7_200) * 1000).toISOString(),
    };
  });
}

export const demoOrders = generateOrders();
export const demoPositions = generatePositions();

export function generateOrders(seed = 53): OrderFixture[] {
  const rand = mulberry32(seed);
  return Array.from({ length: 8 }, (_, i) =>
    generateOrder(`ord-${String(i + 1).padStart(3, "0")}`, seed + i)
  ).sort(() => rand() - 0.5);
}

export const RUN_STAGES = [
  "init",
  "data_gathering",
  "analyst_outputs",
  "debate",
  "ic_decision",
  "cio_proposal",
  "risk_assessment",
  "sizing",
  "order_draft",
  "execution",
  "journal",
] as const;
export type RunStage = (typeof RUN_STAGES)[number];

export const RUN_TERMINAL_STATES = ["completed", "failed", "cancelled", "killed"] as const;
export type RunTerminalState = (typeof RUN_TERMINAL_STATES)[number];

export type RunStatus = RunStage | RunTerminalState;

export interface RunStageEvent {
  stage: RunStage;
  /** ISO timestamp. */
  timestamp: string;
}

export interface WorkflowRun {
  id: string;
  workflow_id: string;
  workflow_name: string;
  status: RunStatus;
  started_at: string;
  completed_at?: string;
  model: string;
  cost_usd: number;
  error?: string;
  stages: RunStageEvent[];
}

const RUN_WORKFLOWS = [
  { id: "wf-xauusd-daily", name: "XAUUSD Daily Direction" },
  { id: "wf-xauusd-news", name: "News Event Sweep" },
  { id: "wf-portfolio-rebalance", name: "Portfolio Rebalance" },
];

export function generateRun(runId: string, seed = 61): WorkflowRun {
  const rand = mulberry32(seed);
  const workflow = RUN_WORKFLOWS[Math.floor(rand() * RUN_WORKFLOWS.length)]!;
  const start = 1_720_000_000 + Math.floor(rand() * 500_000);
  const roll = rand();
  const terminal: RunTerminalState | null =
    roll < 0.55 ? "completed" : roll < 0.75 ? "failed" : roll < 0.9 ? "cancelled" : "killed";
  const stopIndex = terminal
    ? RUN_STAGES.length - 2 + Math.floor(rand() * 3)
    : RUN_STAGES.length - 1;
  const stages: RunStageEvent[] = RUN_STAGES.slice(0, stopIndex + 1).map((stage, i) => ({
    stage,
    timestamp: new Date((start + i * 45_000) * 1000).toISOString(),
  }));
  const stageCount = stages.length;

  return {
    id: runId,
    workflow_id: workflow.id,
    workflow_name: workflow.name,
    status: terminal ?? "journal",
    started_at: new Date(start * 1000).toISOString(),
    completed_at: terminal
      ? new Date((start + stageCount * 45_000) * 1000).toISOString()
      : undefined,
    model: "gpt-5.6-family/9router",
    cost_usd: Math.round((0.4 + rand() * 3.2) * 100) / 100,
    error: terminal === "failed" ? "RiskValidator veto: max drawdown guard tripped" : undefined,
    stages,
  };
}

export interface LineageNode {
  id: string;
  type: "decision" | "input" | "output" | "override";
  label: string;
  detail?: string;
  overridden?: boolean;
  children?: LineageNode[];
}

export interface LineageFixture {
  lineage_id: string;
  run_id: string;
  workflow_id: string;
  model: string;
  cost_usd: number;
  created_at: string;
  root: LineageNode;
}

export function generateLineage(lineageId: string, seed = 73): LineageFixture {
  const rand = mulberry32(seed);
  const created = 1_720_000_000 + Math.floor(rand() * 500_000);

  const tree: LineageNode = {
    id: "decision",
    type: "decision",
    label: `IC proposal — ${lineageId}`,
    detail: "Long XAUUSD 0.40 lots, stop 2,388",
    children: [
      {
        id: "technical",
        type: "input",
        label: "technical / trend",
        detail: "Bullish: 20>50 EMA, price above VWAP. Confidence 0.72",
        children: [
          {
            id: "input-1",
            type: "input",
            label: "ohlcv: XAUUSD 4H (120 bars)",
            detail: "window 2026-08-05→2026-08-11",
          },
          {
            id: "input-2",
            type: "input",
            label: "indicators: EMA20/50, VWAP",
            detail: "computed by feature-engineering",
          },
        ],
      },
      {
        id: "macro",
        type: "input",
        label: "macro / rates",
        detail: "Real yields -12bp this week; USD index soft. Confidence 0.58",
      },
      {
        id: "smc",
        type: "input",
        label: "smc / structure",
        detail: "Liquidity sweep + FVG retest. Confidence 0.64",
        children: [
          {
            id: "input-3",
            type: "input",
            label: "orderflow: 1m tape",
            detail: "12,400 contracts traded",
          },
        ],
      },
      {
        id: "news",
        type: "input",
        label: "news / macro calendar",
        detail: "FOMC minutes due — elevated variance. Confidence 0.41",
        overridden: true,
      },
      {
        id: "risk",
        type: "output",
        label: "risk_assessment / veto",
        detail: "PASS — exposure 8.2% < 15% cap; drawdown 4.1% < 6% guard",
      },
      {
        id: "sizer",
        type: "output",
        label: "portfolio_sizer / size",
        detail: "0.40 lots ≈ $960 risk budget (0.40% of equity)",
        overridden: true,
      },
    ],
  };

  return {
    lineage_id: lineageId,
    run_id: `run-${Math.floor(rand() * 900_000) + 100_000}`,
    workflow_id: "wf-xauusd-daily",
    model: "gpt-5.6-family/9router",
    cost_usd: Math.round((0.4 + rand() * 3.2) * 100) / 100,
    created_at: new Date(created * 1000).toISOString(),
    root: tree,
  };
}

export type JournalKind = "decision" | "trade" | "risk" | "note";

export interface JournalEntry {
  id: string;
  timestamp: string;
  symbol?: string;
  portfolio_id: string;
  kind: JournalKind;
  actor: string;
  summary: string;
  linked_lineage_id?: string;
}

export interface JournalPage {
  entries: JournalEntry[];
  /** Opaque cursor — next page offset; null when exhausted. */
  cursor: string | null;
  has_more: boolean;
}

const JOURNAL_ACTORS = [
  "technical",
  "macro",
  "news",
  "smc",
  "ic",
  "cio",
  "risk-officer",
  "pm",
  "execution",
];
const JOURNAL_SUMMARIES: Array<[JournalKind, string]> = [
  ["decision", "Proposal drafted for XAUUSD long"],
  ["decision", "Debate round 2 — macro vs technical divergence"],
  ["trade", "Order FILLED 0.40 XAUUSD @ 2,401.5"],
  ["trade", "Position closed — take profit hit"],
  ["risk", "Drawdown guard check passed (4.1%)"],
  ["risk", "Exposure cap review — 8.2% of equity"],
  ["note", "Session notes: NFP week, widen stop"],
  ["note", "Model cost sweep: 9router routed to gpt-5.6"],
];

/** 137 deterministic entries split into pages of `pageSize` via cursor. */
const JOURNAL_TOTAL = 137;

export interface JournalOptions {
  seed?: number;
  pageSize?: number;
}

export function generateJournalEntries(
  cursor: string | null = null,
  options: JournalOptions = {}
): JournalPage {
  const { seed = 89, pageSize = 50 } = options;
  const rand = mulberry32(seed);
  const offset = cursor === null ? 0 : Math.max(0, Number.parseInt(cursor, 10) || 0);

  const entries: JournalEntry[] = [];
  const base = 1_720_000_000;
  for (let i = offset; i < Math.min(offset + pageSize, JOURNAL_TOTAL); i++) {
    const [kind, summary] = JOURNAL_SUMMARIES[Math.floor(rand() * JOURNAL_SUMMARIES.length)]!;
    entries.push({
      id: `entry-${String(i + 1).padStart(4, "0")}`,
      timestamp: new Date((base + i * 2_160) * 1000).toISOString(),
      symbol: rand() > 0.3 ? "XAUUSD" : "EURUSD",
      portfolio_id: "portfolio-demo",
      kind,
      actor: JOURNAL_ACTORS[Math.floor(rand() * JOURNAL_ACTORS.length)]!,
      summary,
      linked_lineage_id: kind === "trade" || kind === "decision" ? `lineage-${i + 1}` : undefined,
    });
  }

  const nextOffset = offset + pageSize;
  const has_more = nextOffset < JOURNAL_TOTAL;
  return { entries, cursor: has_more ? String(nextOffset) : null, has_more };
}

export interface ApiKeyFixture {
  key_id: string;
  prefix: string;
  scopes: string[];
  created_at: string;
  last_used_at: string | null;
  revoked: boolean;
}

const API_SCOPES = [
  "market.read",
  "portfolio.read",
  "portfolio.write",
  "orders.write",
  "journal.read",
  "admin.keys",
];

export function generateApiKeys(seed = 97): ApiKeyFixture[] {
  const rand = mulberry32(seed);
  const base = 1_720_000_000;
  const prefixes = ["sk-live", "sk-live", "sk-test", "sk-live", "sk-test", "sk-live"];
  return prefixes.map((prefix, i) => ({
    key_id: `key-${String(i + 1).padStart(3, "0")}`,
    prefix: `${prefix}-${Math.floor(rand() * 1_000_000).toString(36)}`,
    scopes: API_SCOPES.slice(0, 2 + Math.floor(rand() * 3)),
    created_at: new Date((base - i * 30_000_000) * 1000).toISOString(),
    last_used_at:
      rand() > 0.25 ? new Date((base - Math.floor(rand() * 2_000_000)) * 1000).toISOString() : null,
    revoked: i === 2 || i === 4,
  }));
}

/** One-time secret for a freshly created key — shown once, never retrievable. */
export function generateApiKeySecret(scopes: string[] = ["market.read", "portfolio.read"]): {
  key_id: string;
  prefix: string;
  secret: string;
  scopes: string[];
} {
  const rand = mulberry32(101);
  return {
    key_id: `key-${String(Math.floor(rand() * 900) + 100)}`,
    prefix: `sk-live-${Math.floor(rand() * 1_000_000).toString(36)}`,
    secret: `sk-live-${Array.from({ length: 4 }, () => Math.floor(rand() * 1_000_000).toString(36)).join("-")}`,
    scopes,
  };
}
