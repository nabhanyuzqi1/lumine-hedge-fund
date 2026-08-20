// Copyright (c) 2026 Lumine. All rights reserved.
/**
 * Domain-specific type definitions for portfolio management APIs.
 *
 * Maps to backend schemas from `backend/src/lumine/api/schemas/api.py`.
 */

/**
 * High-level portfolio snapshot with NAV calculation.
 */
export interface PortfolioSummary {
  /** Unique portfolio identifier */
  portfolio_id: string;
  /** Net asset value in base currency */
  nav: number;
  /** Available cash balance */
  cash: number;
  /** Total margin utilization */
  margin_used: number;
  /** Unrealized P&L from open positions */
  open_pnl: number;
  /** Realized P&L from closed trades */
  closed_pnl: number;
  /** Snapshot timestamp */
  timestamp: string;
}

/**
 * Open position detail with live pricing.
 */
export interface Position {
  /** Unique position UUID */
  position_id: string;
  /** Associated portfolio ID */
  portfolio_id: string;
  /** Trading symbol (e.g., XAUUSD, EURUSD) */
  symbol: string;
  /** Direction: long = buy, short = sell */
  direction: 'long' | 'short';
  /** Trade volume/contract size */
  volume: number;
  /** Entry price at position open */
  entry_price: number;
  /** Current market price (null if unavailable) */
  current_price: number | null;
  /** Stop loss level (optional) */
  stop_loss: number | null;
  /** Take profit level (optional) */
  take_profit: number | null;
  /** Unrealized profit/loss */
  unrealized_pnl: number;
  /** When position was opened */
  opened_at: string;
}

/**
 * Risk exposure breakdown per symbol/bucket.
 */
export interface ExposureSummary {
  /** Symbol or risk bucket name */
  symbol: string;
  /** Notional exposure value */
  notional: number;
  /** Percentage of total NAV */
  pct_of_nav: number;
  /** Related correlated bucket (if hedged) */
  correlated_bucket: string | null;
}

/**
 * Order lifecycle record with status tracking.
 */
export interface Order {
  /** Unique order UUID */
  order_id: string;
  /** Associated portfolio ID */
  portfolio_id: string;
  /** Trading symbol */
  symbol: string;
  /** Side: buy = long, sell = short */
  side: 'buy' | 'sell';
  /** Order type classification */
  order_type: 'market' | 'limit' | 'stop';
  /** Requested volume */
  volume: number;
  /** Limit price (only for limit orders) */
  price: number | null;
  /** Current execution state */
  status: 'pending' | 'filled' | 'partially_filled' | 'rejected' | 'cancelled';
  /** Filled portion of volume */
  filled_volume: number;
  /** Reason for rejection (if rejected) */
  rejected_reason: string | null;
  /** 19 Aug 2026 A5: alasan keputusan LLM (JSON string) — buy/sell/TP/entry */
  ai_reason?: string | null;
  /** Creation timestamp */
  created_at: string;
  /** Last update timestamp */
  updated_at: string;
}

/**
 * Request payload for creating new orders.
 */
export interface CreateOrderRequest {
  /** Portfolio to execute against */
  portfolio_id: string;
  /** Trading symbol (default: XAUUSD) */
  symbol?: string;
  /** Order direction */
  side: 'buy' | 'sell';
  /** Order type */
  order_type: 'market' | 'limit' | 'stop';
  /** Execution volume */
  volume: number;
  /** Limit price (required for limit orders) */
  price?: number;
  /** Stop trigger price (required for stop orders) */
  stop_price?: number;
  /** Stop loss level (optional override) */
  stop_loss?: number;
  /** Take profit level (optional override) */
  take_profit?: number;
}

/**
 * Server-sent event envelope structure.
 */
export interface SSEEvent<T> {
  /** Event type classification */
  event: string;
  /** Data payload matching event schema */
  data: T;
  /** Optional sequence ID for ordering */
  id?: string;
}

/**
 * Common API response envelope per Phase 9 contract.
 */
export interface EnvEnvelope<T> {
  /** Primary data payload */
  data: T;
  /** Optional metadata (trace_id, latency, etc.) */
  metadata?: Record<string, unknown>;
}

/**
 * Market data snapshot for a trading symbol.
 */
export interface MarketData {
  /** Symbol identifier */
  symbol: string;
  /** Current bid price */
  bid: number;
  /** Current ask price */
  ask: number;
  /** Mid-price average */
  mid: number;
  /** Last traded price */
  last: number;
  /** Volume in base currency */
  volume_24h: number;
  /** Price change over 24h */
  change_24h: number;
  /** Change percentage */
  change_pct_24h: number;
  /** Latest timestamp */
  timestamp: string;
}

/**
 * API key management view (backend schemas/api.py AdminKey).
 */
export interface AdminKey {
  key_id: string;
  name: string;
  scopes: string[];
  revoked: boolean;
  created_at: string;
}

/**
 * API key creation response — the secret is shown exactly once.
 */
export interface CreatedAdminKey {
  key_id: string;
  secret: string;
  scopes: string[];
  created_at: string;
}

export type KillSwitchTier = 'global' | 'book' | 'strategy';

/**
 * Current kill-switch state (backend schemas/api.py KillSwitchStatus).
 */
export interface KillSwitchStatus {
  armed: boolean;
  reason: string | null;
  tier: KillSwitchTier | null;
  updated_at: string | null;
}

/**
 * Workflow execution state record.
 */
export interface WorkflowState {
  /** Unique workflow UUID */
  workflow_id: string;
  /** Workflow type/classification */
  type: string;
  /** Current execution state */
  state: 'pending' | 'running' | 'completed' | 'failed' | 'cancelled';
  /** Progress percentage (0-100) */
  progress: number;
  /** Error message if failed */
  error: string | null;
  /** Start timestamp */
  started_at: string | null;
  /** Completion timestamp */
  completed_at: string | null;
  /** Step-by-step audit log */
  steps: Array<{
    step: number;
    action: string;
    status: 'pending' | 'success' | 'error';
    timestamp: string;
    message?: string;
  }>;
}
