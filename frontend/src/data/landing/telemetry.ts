/**
 * System telemetry data for landing page hero section.
 * SIMULATED DATA — not connected to live backend.
 */

export interface SystemStatus {
  status: "ONLINE" | "OFFLINE" | "DEGRADED";
  mode: "RESEARCH" | "PAPER" | "LIVE";
  uptime: string;
  lastUpdate: string;
}

export interface MarketStatus {
  symbol: string;
  status: "OPEN" | "CLOSED";
  session: string;
}

export const SYSTEM_STATUS: SystemStatus = {
  status: "ONLINE",
  mode: "RESEARCH",
  uptime: "99.7%",
  lastUpdate: new Date().toISOString(),
};

export const MARKETS: MarketStatus[] = [
  { symbol: "XAUUSD", status: "OPEN", session: "LONDON" },
  { symbol: "EURUSD", status: "OPEN", session: "LONDON" },
  { symbol: "GBPUSD", status: "OPEN", session: "LONDON" },
  { symbol: "USDJPY", status: "OPEN", session: "TOKYO" },
  { symbol: "SPX500", status: "CLOSED", session: "PRE-MARKET" },
];

export const ENGINE_STATS = {
  agents: 4,
  strategies: 8,
  instruments: 8,
  avgLatency: "< 120ms",
};
