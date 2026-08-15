/**
 * Multi-agent intelligence system data for landing page.
 * SIMULATED DATA — not connected to live backend.
 */

export interface Agent {
  id: string;
  name: string;
  role: string;
  description: string;
  color: string;
  capabilities: string[];
}

export interface AgentAnalysis {
  agent: string;
  bias: "BULLISH" | "BEARISH" | "NEUTRAL";
  confidence: number;
  reasoning: string;
}

export const AGENTS: Agent[] = [
  {
    id: "technical",
    name: "Technical Intelligence",
    role: "Price Action & Momentum Analysis",
    description:
      "Analyzes trend, momentum, volatility, price structure, and technical indicators across multiple timeframes.",
    color: "#4d8dff", // accent
    capabilities: [
      "Multi-timeframe trend analysis",
      "Momentum & volatility measurement",
      "Support/resistance identification",
      "Technical indicator synthesis",
      "Price pattern recognition",
    ],
  },
  {
    id: "macro",
    name: "Macro Intelligence",
    role: "Economic Regime & Policy Analysis",
    description:
      "Evaluates interest rates, inflation, monetary policy, and macroeconomic conditions that drive market regimes.",
    color: "#34d399", // up
    capabilities: [
      "Interest rate regime analysis",
      "Inflation trend monitoring",
      "Central bank policy assessment",
      "Economic cycle positioning",
      "Cross-asset correlation analysis",
    ],
  },
  {
    id: "news",
    name: "News Intelligence",
    role: "Event & Sentiment Analysis",
    description:
      "Processes market-moving events, sentiment shifts, scheduled economic releases, and geopolitical risk.",
    color: "#ffb020", // warn
    capabilities: [
      "Real-time event detection",
      "Sentiment analysis",
      "Economic calendar integration",
      "Geopolitical risk assessment",
      "Market reaction forecasting",
    ],
  },
  {
    id: "structure",
    name: "Market Structure Intelligence",
    role: "Liquidity & Order Flow Analysis",
    description:
      "Analyzes liquidity zones, market structure, institutional levels, order flow concepts, and structural breaks.",
    color: "#22d3ee", // cyan
    capabilities: [
      "Liquidity zone mapping",
      "Order flow analysis",
      "Institutional level detection",
      "Market structure break identification",
      "Supply/demand zone analysis",
    ],
  },
];

export const SAMPLE_MASTER_DECISION = {
  asset: "XAUUSD",
  timestamp: "2026-08-15T14:32:08Z",
  bias: "BULLISH" as const,
  confidence: 78.4,
  analyses: [
    {
      agent: "Technical Intelligence",
      bias: "BULLISH" as const,
      confidence: 82.0,
      reasoning:
        "Strong uptrend on H4/D1. Momentum indicators showing sustained buying pressure. Price trading above key moving averages.",
    },
    {
      agent: "Macro Intelligence",
      bias: "BULLISH" as const,
      confidence: 75.0,
      reasoning:
        "Fed rate cut expectations increasing. Real yields declining. USD weakness supporting gold rally.",
    },
    {
      agent: "News Intelligence",
      bias: "NEUTRAL" as const,
      confidence: 65.0,
      reasoning:
        "No major scheduled events. Sentiment neutral with slight risk-on bias. Geopolitical tensions stable.",
    },
    {
      agent: "Market Structure Intelligence",
      bias: "BULLISH" as const,
      confidence: 80.0,
      reasoning:
        "Price holding above key liquidity zone at 3340. Structure intact. Institutional buying zones respected.",
    },
  ] as AgentAnalysis[],
  consensus: "HIGH" as const,
  masterThesis:
    "Four agents show strong bullish alignment with high confidence. Technical and structure analysis particularly strong. Macro conditions supportive. News environment neutral but not conflicting. Favorable risk/reward setup.",
};
