/**
 * Trade audit log sample data for landing page.
 * SIMULATED DATA — demonstrates auditability and decision traceability.
 */

export interface TradeAudit {
  tradeId: string;
  timestamp: string;
  asset: string;
  side: "LONG" | "SHORT";
  regime: string;
  technical: "BULLISH" | "BEARISH" | "NEUTRAL";
  macro: "BULLISH" | "BEARISH" | "NEUTRAL";
  news: "BULLISH" | "BEARISH" | "NEUTRAL";
  structure: "BULLISH" | "BEARISH" | "NEUTRAL";
  masterThesis: "LONG" | "SHORT" | "NEUTRAL";
  confidence: number;
  riskPercent: number;
  entry: number;
  stop: number;
  target: number;
  status: "SIMULATED" | "PAPER" | "LIVE";
}

export const SAMPLE_TRADE_AUDIT: TradeAudit = {
  tradeId: "LUM-2026-001842",
  timestamp: "2026-08-14T14:32:08Z",
  asset: "XAUUSD",
  side: "LONG",
  regime: "TRENDING",
  technical: "BULLISH",
  macro: "BULLISH",
  news: "NEUTRAL",
  structure: "BULLISH",
  masterThesis: "LONG",
  confidence: 78.4,
  riskPercent: 0.5,
  entry: 3350.2,
  stop: 3340.2,
  target: 3370.2,
  status: "SIMULATED",
};

export const SAMPLE_TRADES: TradeAudit[] = [
  SAMPLE_TRADE_AUDIT,
  {
    tradeId: "LUM-2026-001841",
    timestamp: "2026-08-14T09:15:22Z",
    asset: "EURUSD",
    side: "SHORT",
    regime: "RANGING",
    technical: "BEARISH",
    macro: "NEUTRAL",
    news: "BEARISH",
    structure: "BEARISH",
    masterThesis: "SHORT",
    confidence: 72.1,
    riskPercent: 0.5,
    entry: 1.092,
    stop: 1.0935,
    target: 1.0895,
    status: "SIMULATED",
  },
  {
    tradeId: "LUM-2026-001840",
    timestamp: "2026-08-13T16:45:03Z",
    asset: "XAUUSD",
    side: "LONG",
    regime: "TRENDING",
    technical: "BULLISH",
    macro: "BULLISH",
    news: "NEUTRAL",
    structure: "BULLISH",
    masterThesis: "LONG",
    confidence: 81.2,
    riskPercent: 0.5,
    entry: 3342.5,
    stop: 3332.5,
    target: 3362.5,
    status: "SIMULATED",
  },
];
