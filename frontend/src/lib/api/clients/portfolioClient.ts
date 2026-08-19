// Copyright (c) 2026 Lumine. All rights reserved.
/**
 * Portfolio API client per Phase 9 API contract.
 *
 * Handles:
 * - Portfolio summaries with NAV calculation
 * - Position list and detail retrieval
 * - Risk exposure breakdown
 * - Transaction history
 */

import { api, http } from '../core';
import type { PortfolioSummary, Position, ExposureSummary } from '../types';

export interface PortfolioFilter {
  /** Filter by portfolio ID(s) */
  ids?: string[];
  /** Filter by status: active/inactive/all */
  status?: 'active' | 'inactive' | 'all';
  /** Sort field (default: name) */
  sort?: 'name' | 'nav' | 'created_at';
  /** Sort direction (asc/desc) */
  order?: 'asc' | 'desc';
  /** Pagination limit */
  limit?: number;
  /** Pagination offset */
  offset?: number;
}

export interface UpdatePortfolioRequest {
  name?: string;
  description?: string;
  currency?: string;
  base_currency?: string;
}

/**
 * Fetch portfolio summary with NAV and cash positions.
 *
 * Per D5-1 physical ERD: portfolios table with snapshot joins.
 * Returns current state including unrealized P&L calculations.
 *
 * @param portfolioId - Portfolio UUID
 * @returns PortfolioSummary with real-time values
 */
export async function getPortfolioSummary(_portfolioId: string): Promise<PortfolioSummary> {
  // Backend serves the single default portfolio at /portfolio/summary
  // (routers/portfolio.py). The id parameter is reserved for the
  // multi-portfolio phase; it is dropped from the path (2026-08-14).
  const result = await api.get<{ data: PortfolioSummary }>(`/api/portfolio/summary`);
  if (result.error) throw result.error;
  return result.data!.data;
}

/**
 * List all portfolios with optional filtering.
 *
 * Supports pagination and sorting per D9-3 REST conventions.
 *
 * @param filter - Optional filter parameters
 * @returns Paginated portfolio list
 */
export async function listPortfolios(filter?: PortfolioFilter): Promise<{
  items: Array<{ id: string; name: string; nav: number; created_at: string }>;
  total: number;
}> {
  const params = new URLSearchParams();
  if (filter?.ids) params.append('ids', filter.ids.join(','));
  if (filter?.status) params.append('status', filter.status);
  if (filter?.sort) params.append('sort', filter.sort);
  if (filter?.order) params.append('order', filter.order);
  if (filter?.limit) params.append('limit', String(filter.limit));
  if (filter?.offset) params.append('offset', String(filter.offset));

  const path = `/api/portfolios?${params.toString()}`;
  const result = await api.get<{ data: { items: any[]; total: number } }>(path);
  if (result.error) throw result.error;
  return result.data!.data;
}

/**
 * Get open positions for a portfolio.
 *
 * Returns live position data with current prices and P&L calculations.
 * Positions include unrealized profit/loss based on last known market price.
 *
 * @param portfolioId - Portfolio UUID
 * @returns List of open positions
 */
export async function getPositionList(_portfolioId: string): Promise<Position[]> {
  // Single-default-portfolio backend: /portfolio/positions (2026-08-14).
  // Backend return PaginatedList envelope {data: {items: [...]}} — handle
  // kedua shape (array lama vs {items}) agar RiskGauges tidak crash.
  const result = await api.get<{ data: Position[] | { items: Position[] } }>(
    `/api/portfolio/positions`
  );
  if (result.error) throw result.error;
  const data = result.data?.data;
  if (Array.isArray(data)) return data;
  return data?.items ?? [];
}

/**
 * Get single position detail by UUID.
 *
 * Includes entry metrics and current pricing for analysis.
 *
 * @param portfolioId - Parent portfolio UUID
 * @param positionId - Position UUID
 * @returns Single position object
 */
export async function getPositionDetail(
  _portfolioId: string,
  positionId: string
): Promise<Position> {
  // Single-default-portfolio backend: /portfolio/positions/{id} (2026-08-14).
  const result = await api.get<{ data: Position }>(
    `/api/portfolio/positions/${positionId}`
  );
  if (result.error) throw result.error;
  return result.data!.data;
}

/**
 * Get risk exposure breakdown.
 *
 * Per D7-4 agent architecture: exposure analysis across symbols, sectors, correlations.
 * Returns notional value and percentage allocation per bucket.
 *
 * @param portfolioId - Portfolio UUID
 * @returns Exposure summary per symbol/bucket
 */
export async function getExposureData(_portfolioId: string): Promise<ExposureSummary[]> {
  // Single-default-portfolio backend: /portfolio/exposure (2026-08-14).
  // Backend return PaginatedList envelope {data: {items: [...]}} — handle
  // kedua shape (array lama vs {items}).
  const result = await api.get<{ data: ExposureSummary[] | { items: ExposureSummary[] } }>(
    `/api/portfolio/exposure`
  );
  if (result.error) throw result.error;
  const data = result.data?.data;
  if (Array.isArray(data)) return data;
  return data?.items ?? [];
}

/**
 * Create new portfolio.
 *
 * Initializes empty portfolio with base currency configuration.
 * Sets up initial transaction log for audit trail.
 *
 * @param request - Portfolio creation payload
 * @returns Created portfolio ID
 */
export async function createPortfolio(request: {
  name: string;
  description?: string;
  currency?: string;
  base_currency?: string;
}): Promise<string> {
  const result = await api.post<{ data: { id: string } }>('/api/portfolios', request);
  if (result.error) throw result.error;
  return result.data!.data.id;
}

/**
 * Update portfolio metadata.
 *
 * Allows renaming or updating configuration after creation.
 * Does not affect existing positions or transaction history.
 *
 * @param portfolioId - Portfolio UUID
 * @param request - Update fields
 */
export async function updatePortfolio(
  portfolioId: string,
  request: UpdatePortfolioRequest
): Promise<void> {
  const result = await api.put(`/api/portfolio/${portfolioId}`, request);
  if (result.error) throw result.error;
}

/**
 * Delete portfolio (soft delete).
 *
 * Marks portfolio as inactive but preserves historical data for compliance.
 * Positions cannot be added to deleted portfolios.
 *
 * @param portfolioId - Portfolio UUID
 */
export async function deletePortfolio(portfolioId: string): Promise<void> {
  const result = await api.delete(`/api/portfolio/${portfolioId}`);
  if (result.error) throw result.error;
}

/**
 * Export portfolio transaction history.
 *
 * For compliance audits and backtesting analysis.
 * Returns CSV format with all trades and position changes.
 *
 * @param portfolioId - Portfolio UUID
 * @returns CSV download URL or blob
 */
export async function exportTransactions(portfolioId: string): Promise<Blob> {
  const result = await http<Blob>('GET', `/api/portfolio/${portfolioId}/transactions/export`, {
    skipValidate: true, // Binary response
  });
  if (result.error) throw result.error;
  return result.data!;
}

/**
 * Bulk get portfolio summaries.
 *
 * Optimized endpoint for fetching multiple portfolios at once.
 * Reduces round-trip latency in dashboard overview screens.
 *
 * @param portfolioIds - List of portfolio UUIDs
 * @returns Map of portfolio_id → summary
 */
export async function bulkGetPortfolios(portfolioIds: string[]): Promise<Map<string, PortfolioSummary>> {
  const searchParams = new URLSearchParams(portfolioIds.map((id) => ['ids', id]));
  const result = await api.get<{ data: Record<string, PortfolioSummary> }>(
    `/api/portfolios/bulk?${searchParams.toString()}`
  );
  if (result.error) throw result.error;
  return new Map(Object.entries(result.data?.data ?? {}));
}
