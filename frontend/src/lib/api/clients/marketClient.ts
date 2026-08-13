// Copyright (c) 2026 Lumine. All rights reserved.
/**
 * Market data API client per Phase 9 API contract.
 *
 * Handles:
 * - Real-time price quotes (bid/ask/mid)
 * - Historical OHLCV data with multiple timeframes
 * - Symbol configuration and metadata
 * - Volatility and correlation metrics
 */

import { api } from '../core';
import type { MarketData } from '../types';

export interface Timeframe {
  m1: '1m';
  m5: '5m';
  m15: '15m';
  m30: '30m';
  h1: '1h';
  h4: '4h';
  d1: '1d';
  w1: '1w';
}

export interface OHLCVPoint {
  timestamp: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface SymbolConfig {
  symbol: string;
  description: string;
  base_asset: string;
  quote_currency: string;
  tick_size: number;
  lot_size: number;
  min_lot_size: number;
  max_lot_size: number;
  is_active: boolean;
}

/**
 * Get real-time quote for a symbol.
 *
 * Returns current bid, ask, mid prices plus last trade info.
 * Price precision follows instrument specification (e.g., 5 decimal places for Forex).
 *
 * @param symbol - Trading symbol (e.g., XAUUSD, EURUSD)
 * @returns Current market quote
 */
export async function getQuote(symbol: string): Promise<MarketData> {
  const result = await api.get<{ data: MarketData }>(`/api/market/quote/${encodeURIComponent(symbol)}`);
  if (result.error) throw result.error;
  return result.data?.data!;
}

/**
 * Batch fetch quotes for multiple symbols.
 *
 * Optimized endpoint reducing round-trips for multi-symbol dashboards.
 * Returns map of symbol → quote for efficient lookup.
 *
 * @param symbols - List of trading symbols
 * @returns Map of symbol → market quote
 */
export async function getQuotes(symbols: string[]): Promise<Map<string, MarketData>> {
  const searchParams = new URLSearchParams(symbols.map((s) => ['symbols', s]));
  const result = await api.get<{ data: Record<string, MarketData> }>(
    `/api/market/quotes?${searchParams.toString()}`
  );
  if (result.error) throw result.error;
  return new Map(Object.entries(result.data?.data ?? {}));
}

/**
 * Fetch historical OHLCV data.
 *
 * Supports multiple timeframes (1m to 1w).
 * Data includes full candlestick bars with volume for technical analysis.
 *
 * @param symbol - Trading symbol
 * @param timeframe - Candle resolution
 * @param limit - Number of candles (max: 10000)
 * @param since - Optional start timestamp
 * @returns Array of OHLCV bars
 */
export async function getOHLCV({
  symbol,
  timeframe,
  limit = 100,
  since,
}: {
  symbol: string;
  timeframe: keyof Timeframe | string;
  limit?: number;
  since?: string;
}): Promise<OHLCVPoint[]> {
  const params = new URLSearchParams([
    ['timeframe', timeframe],
    ['limit', String(limit)],
  ]);
  if (since) params.append('since', since);

  const result = await api.get<{ data: OHLCVPoint[] }>(
    `/api/market/ohlcv/${encodeURIComponent(symbol)}?${params.toString()}`
  );
  if (result.error) throw result.error;
  return result.data?.data ?? [];
}

/**
 * Get symbol configuration and trading parameters.
 *
 * Provides broker specifications: tick size, lot size constraints,
 * minimum order volume, etc. Required for building valid orders.
 *
 * @param symbol - Trading symbol
 * @returns Instrument specification
 */
export async function getSymbolConfig(symbol: string): Promise<SymbolConfig> {
  const result = await api.get<{ data: SymbolConfig }>(
    `/api/market/symbol/${encodeURIComponent(symbol)}`
  );
  if (result.error) throw result.error;
  return result.data?.data!;
}

/**
 * List all available symbols.
 *
 * Returns active trading instruments with metadata.
 * Can be filtered by asset class or exchange.
 *
 * @param filters - Optional filters
 * @returns Active symbol list
 */
export async function listSymbols(filters?: {
  asset_class?: string;
  exchange?: string;
  include_inactive?: boolean;
}): Promise<SymbolConfig[]> {
  const params = new URLSearchParams();
  if (filters?.asset_class) params.append('asset_class', filters.asset_class);
  if (filters?.exchange) params.append('exchange', filters.exchange);
  if (filters?.include_inactive) params.append('include_inactive', 'true');

  const result = await api.get<{ data: SymbolConfig[] }>(`/api/market/symbols?${params.toString()}`);
  if (result.error) throw result.error;
  return result.data?.data ?? [];
}

/**
 * Calculate volatility metrics.
 *
 * Computes rolling volatility over specified window.
 * Used for position sizing and stop-loss placement.
 *
 * @param symbol - Trading symbol
 * @param window - Rolling window in days
 * @returns Volatility percentage
 */
export async function getVolatility({
  symbol,
  windowDays = 14,
}: {
  symbol: string;
  windowDays?: number;
}): Promise<number> {
  const params = new URLSearchParams([['window', String(windowDays)]]);
  const result = await api.get<{ data: { volatility: number } }>(
    `/api/market/volatility/${encodeURIComponent(symbol)}?${params.toString()}`
  );
  if (result.error) throw result.error;
  return result.data!.data.volatility;
}

/**
 * Get correlation matrix between symbols.
 *
 * Calculates Pearson correlation coefficient over time window.
 * Useful for portfolio diversification analysis.
 *
 * @param symbols - Symbols to correlate
 * @param windowDays - Correlation window in days
 * @returns Correlation matrix (lower triangular)
 */
export async function getCorrelation({
  symbols,
  windowDays = 30,
}: {
  symbols: string[];
  windowDays?: number;
}): Promise<Record<string, Record<string, number>>> {
  const searchParams = new URLSearchParams(
    [...symbols, `window=${windowDays}`].map((s) => ['q', s])
  );
  const result = await api.get<{ data: Record<string, Record<string, number>> }>(
    `/api/market/correlation?${searchParams.toString()}`
  );
  if (result.error) throw result.error;
  return result.data?.data ?? {};
}

/**
 * Fetch current spread metrics.
 *
 * Returns average spread width and percent spread relative to price.
 * High spreads indicate illiquid conditions or wider broker markup.
 *
 * @param symbol - Trading symbol
 * @param period - Spread calculation period (seconds)
 * @returns Spread metrics
 */
export async function getSpreadMetrics(symbol: string, period: number = 60): Promise<{
  avg_spread: number;
  avg_pct_spread: number;
  min_spread: number;
  max_spread: number;
}> {
  const result = await api.get<{ data: any }>(
    `/api/market/spread/${encodeURIComponent(symbol)}?period=${period}`
  );
  if (result.error) throw result.error;
  return result.data?.data!;
}

/**
 * Get session timezone data.
 *
 * Returns current trading session status (Asian/European/American)
 * and remaining time until session change.
 */
export async function getSessionData(symbol: string): Promise<{
  current_session: string;
  next_session: string;
  time_until_next: number; // seconds
  is_trading_open: boolean;
}> {
  const result = await api.get<{ data: any }>(
    `/api/market/session/${encodeURIComponent(symbol)}`
  );
  if (result.error) throw result.error;
  return result.data?.data!;
}
