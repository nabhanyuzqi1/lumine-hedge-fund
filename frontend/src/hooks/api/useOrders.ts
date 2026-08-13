// Copyright (c) 2026 Lumine. All rights reserved.
/**
 * Order lifecycle React hooks using TanStack Query.
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';

import * as ordersClient from '../../lib/api/clients/ordersClient';
import type { Order } from '../../lib/api/types';

export const QUERY_KEYS = {
  orders: {
    all: ['orders'] as const,
    lists: () => [...QUERY_KEYS.orders.all, 'list'] as const,
    detail: (orderId: string) => [...QUERY_KEYS.orders.all, orderId] as const,
  },
};

/**
 * Place a new order.
 *
 * With optimistic update for instant UI feedback.
 * Invalidates position list and portfolio summary on success.
 */
export function usePlaceOrder(_portfolioId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ordersClient.placeOrder,
    onMutate: async (request) => {
      // Cancel current queries for faster UI response
      await queryClient.cancelQueries({
        queryKey: [QUERY_KEYS.orders.detail(request.portfolio_id)],
      });

      const previousOrders = queryClient.getQueryData<Order[]>(
        [QUERY_KEYS.orders.lists(), request.portfolio_id]
      );

      // Optimistically add new order in pending state
      const optimisticOrder: Order = {
        order_id: `pending_${Date.now()}`,
        portfolio_id: request.portfolio_id,
        symbol: request.symbol ?? 'XAUUSD',
        side: request.side,
        order_type: request.order_type,
        volume: request.volume,
        price: null,
        status: 'pending',
        filled_volume: 0,
        rejected_reason: null,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      };

      if (previousOrders) {
        queryClient.setQueryData(
          [QUERY_KEYS.orders.lists(), request.portfolio_id],
          [optimisticOrder, ...previousOrders]
        );
      }

      return { previousOrders, optimisticOrder };
    },
    onSuccess: (createdOrder, variables, context) => {
      // Replace optimistic order with real order
      queryClient.setQueryData<Order[]>(
        [QUERY_KEYS.orders.lists(), variables.portfolio_id],
        (old) => {
          if (!old) return [createdOrder];
          return old.map((o) =>
            o.order_id === context?.optimisticOrder?.order_id ? createdOrder : o
          );
        }
      );

      // Refresh positions for immediate P&L update
      queryClient.invalidateQueries({
        predicate: (query) =>
          query.queryKey.some((key) => key === 'positions'),
      });
    },
    onError: (_err, _variables, context) => {
      // Rollback optimistic update
      if (context?.previousOrders) {
        queryClient.setQueryData(
          [QUERY_KEYS.orders.lists(), _variables.portfolio_id],
          context.previousOrders
        );
      }
    },
  });
}

/**
 * Get single order by ID.
 */
export function useOrder(orderId: string, enabled: boolean = true) {
  return useQuery({
    queryKey: QUERY_KEYS.orders.detail(orderId),
    queryFn: () => ordersClient.getOrder(orderId),
    enabled: enabled && !!orderId,
    staleTime: 5_000, // Poll for updates
    retry: (failureCount, error) => {
      // Retry on network errors or server errors
      if (((error as { statusCode?: number }).statusCode ?? 0) >= 500) return false;
      return failureCount < 3;
    },
  });
}

/**
 * List orders with optional filtering.
 */
export function useOrders(filter?: ordersClient.OrderFilter) {
  return useQuery({
    queryKey: [QUERY_KEYS.orders.lists(), filter?.portfolioId || 'all'],
    queryFn: () => ordersClient.listOrders(filter),
    initialData: { items: [], total: 0 },
    refetchInterval: 10_000, // Poll for pending order updates
    refetchIntervalInBackground: true,
  });
}

/**
 * Cancel an existing order.
 */
export function useCancelOrder() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ orderId, reason }: { orderId: string; reason?: string }) =>
      ordersClient.cancelOrder(orderId, { reason }),
    onSuccess: async (_, { orderId: _orderId }) => {
      await queryClient.invalidateQueries({
        predicate: (query) =>
          query.queryKey.some((key) =>
            typeof key === 'string' && key.includes('orders')
          ),
      });
    },
  });
}

/**
 * Modify order parameters (price/volume).
 */
export function useModifyOrder() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ orderId, updates }: { orderId: string; updates: { price?: number; volume?: number } }) =>
      ordersClient.modifyOrder(orderId, updates),
    onSuccess: async (_updatedOrder) => {
      await queryClient.invalidateQueries({
        predicate: (query) =>
          query.queryKey.some((key) =>
            typeof key === 'string' && key.includes('orders')
          ),
      });
    },
  });
}

/**
 * Bulk cancel all orders for a symbol/portfolio.
 */
export function useCancelAllOrders() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (params: { portfolioId: string; symbol?: string }) =>
      ordersClient.cancelAllOrders(params.portfolioId, params.symbol),
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        predicate: (query) =>
          query.queryKey.some((key) =>
            typeof key === 'string' && key.includes('orders')
          ),
      });
    },
  });
}

/**
 * Fetch order execution history.
 */
export function useOrderHistory(orderId: string) {
  return useQuery({
    queryKey: [QUERY_KEYS.orders.detail(orderId), 'history'],
    queryFn: () => ordersClient.getOrderHistory(orderId),
    enabled: !!orderId,
    refetchOnWindowFocus: true,
  });
}

/**
 * Poll multiple order statuses efficiently.
 */
export function useBulkOrderStatuses(orderIds: string[]) {
  return useQuery({
    queryKey: ['orders', 'bulk-status', ...orderIds],
    queryFn: () => ordersClient.bulkGetOrderStatuses(orderIds),
    enabled: orderIds.length > 0,
    refetchInterval: 5_000, // Frequent polling for active orders
    refetchIntervalInBackground: true,
  });
}
