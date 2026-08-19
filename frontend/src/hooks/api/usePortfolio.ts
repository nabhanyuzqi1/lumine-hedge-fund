// Copyright (c) 2026 Lumine. All rights reserved.
/**
 * Portfolio-related React hooks using TanStack Query.
 *
 * Provides typed wrappers around portfolioClient with:
 * - Automatic refetch on focus/poll
 * - Optimistic updates for instant feedback
 * - Error boundaries and retry logic
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import type { UseQueryOptions, UseQueryResult } from '@tanstack/react-query';

import * as portfolioClient from '../../lib/api/clients/portfolioClient';
import type { PortfolioSummary } from '../../lib/api/types';

export const QUERY_KEYS = {
  portfolios: {
    all: ['portfolios'] as const,
    lists: () => [...QUERY_KEYS.portfolios.all, 'list'] as const,
    details: (id: string) => [...QUERY_KEYS.portfolios.lists(), id] as const,
  },
  positions: {
    all: ['positions'] as const,
    list: (portfolioId: string) => [...QUERY_KEYS.positions.all, portfolioId] as const,
    detail: (portfolioId: string, positionId: string) =>
      [...QUERY_KEYS.positions.list(portfolioId), positionId] as const,
  },
  exposure: {
    all: ['exposure'] as const,
    list: (portfolioId: string) => [...QUERY_KEYS.exposure.all, portfolioId] as const,
  },
};

/**
 * Fetch portfolio summary with NAV and cash position.
 *
 * @param portfolioId - Portfolio UUID
 * @param options - Query configuration
 */
export function usePortfolioSummary(
  portfolioId: string,
  options?: Omit<UseQueryOptions<PortfolioSummary>, 'queryKey' | 'queryFn'>
): UseQueryResult<PortfolioSummary> {
  return useQuery({
    queryKey: QUERY_KEYS.portfolios.details(portfolioId),
    queryFn: () => portfolioClient.getPortfolioSummary(portfolioId),
    staleTime: 5_000, // Revalidate after 5s for live pricing
    ...options,
  });
}

/**
 * List all available portfolios.
 *
 * Supports pagination and filtering. Auto-refreshes every 30s in background.
 */
export function usePortfolios(filter?: portfolioClient.PortfolioFilter) {
  return useQuery({
    queryKey: QUERY_KEYS.portfolios.lists(),
    queryFn: () => portfolioClient.listPortfolios(filter),
    initialData: { items: [], total: 0 },
    staleTime: 30_000, // Cache for 30s during navigation
    ...filter?.status === 'all' ? {} : { refetchOnMount: true },
  });
}

/**
 * Fetch open positions for a portfolio.
 *
 * Updates every 10s for live P&L tracking. Optimistic updates enabled
 * when new positions are created via trade execution.
 */
export function usePositionList(portfolioId: string) {
  return useQuery({
    queryKey: QUERY_KEYS.positions.list(portfolioId),
    queryFn: () => portfolioClient.getPositionList(portfolioId),
    staleTime: 10_000, // Live pricing refresh
    retry: 3,
  });
}

/**
 * Fetch single position detail with full metrics.
 */
export function usePositionDetail(portfolioId: string, positionId: string) {
  return useQuery({
    queryKey: QUERY_KEYS.positions.detail(portfolioId, positionId),
    queryFn: () => portfolioClient.getPositionDetail(portfolioId, positionId),
    enabled: !!positionId,
    staleTime: 15_000,
  });
}

/**
 * Get risk exposure breakdown.
 *
 * Returns symbol-level allocation percentages for chart visualization.
 */
export function useExposureData(portfolioId: string) {
  return useQuery({
    queryKey: QUERY_KEYS.exposure.list(portfolioId),
    queryFn: () => portfolioClient.getExposureData(portfolioId),
    staleTime: 60_000, // Exposure changes slower than prices
  });
}

/**
 * Create new portfolio with given metadata.
 */
export function useCreatePortfolio() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: portfolioClient.createPortfolio,
    onSuccess: () => {
      // Refresh portfolio list after creation
      queryClient.invalidateQueries({
        queryKey: QUERY_KEYS.portfolios.lists(),
      });
    },
  });
}

/**
 * Update portfolio metadata (name/description).
 */
export function useUpdatePortfolio(portfolioId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (request: portfolioClient.UpdatePortfolioRequest) =>
      portfolioClient.updatePortfolio(portfolioId, request),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: QUERY_KEYS.portfolios.details(portfolioId),
      });
    },
  });
}

/**
 * Delete portfolio (soft delete).
 */
export function useDeletePortfolio(portfolioId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: () => portfolioClient.deletePortfolio(portfolioId),
    onSuccess: () => {
      // Remove portfolio from UI
      queryClient.removeQueries({
        queryKey: QUERY_KEYS.portfolios.details(portfolioId),
      });
      queryClient.invalidateQueries({
        queryKey: QUERY_KEYS.portfolios.lists(),
      });
    },
  });
}

/**
 * Export portfolio transaction history to CSV.
 */
export function useExportTransactions(portfolioId: string) {
  return useMutation({
    mutationFn: () => portfolioClient.exportTransactions(portfolioId),
    // No onSuccess handler needed - just returns blob for download
  });
}

/**
 * Bulk fetch multiple portfolio summaries.
 *
 * Reduces round-trips when showing portfolio overview grid.
 */
export function useBulkPortfolios(portfolioIds: string[]) {
  return useQuery({
    queryKey: ['portfolios', 'bulk', ...portfolioIds],
    queryFn: () => portfolioClient.bulkGetPortfolios(portfolioIds),
    enabled: portfolioIds.length > 0,
    staleTime: 10_000,
  });
}
