// Copyright (c) 2026 Lumine. All rights reserved.
/**
 * Order lifecycle API client per Phase 9 API contract.
 *
 * Handles:
 * - Order creation with validation
 * - Status tracking through execution states
 * - Order cancellation/modification
 * - Transaction history retrieval
 */

import { api } from '../core';
import type { Order, CreateOrderRequest } from '../types';

export interface OrderFilter {
  /** Filter by portfolio ID */
  portfolioId?: string;
  /** Filter by symbol (e.g., XAUUSD, EURUSD) */
  symbol?: string;
  /** Filter by status */
  status?: 'pending' | 'filled' | 'partially_filled' | 'rejected' | 'cancelled';
  /** Filter by order type */
  orderType?: 'market' | 'limit' | 'stop';
  /** Time range start */
  from?: string;
  /** Time range end */
  to?: string;
  /** Pagination limit */
  limit?: number;
  /** Pagination offset */
  offset?: number;
}

export interface CancelOrderRequest {
  reason?: string; // For audit trail
}

/**
 * Place a new order.
 *
 * Per D8-3 trading architecture: submits order to execution controller
 * which runs pre-trade risk checks before forwarding to broker.
 *
 * @param request - Order creation payload
 * @returns Created Order object with assigned ID
 */
export async function placeOrder(request: CreateOrderRequest): Promise<Order> {
  const result = await api.post<{ data: Order }>('/api/orders', request);
  if (result.error) throw result.error;
  return result.data?.data!;
}

/**
 * Get order by UUID.
 *
 * Returns full order details including current execution state
 * and filled portion for partial fills.
 *
 * @param orderId - Order UUID
 * @returns Order with full lifecycle data
 */
export async function getOrder(orderId: string): Promise<Order> {
  const result = await api.get<{ data: Order }>(`/api/orders/${orderId}`);
  if (result.error) throw result.error;
  return result.data?.data!;
}

/**
 * List orders with optional filtering.
 *
 * Supports time-range queries and pagination for performance.
 * Defaults to showing recent pending/filled orders only.
 *
 * @param filter - Optional filter parameters
 * @returns Paginated order list
 */
export async function listOrders(filter?: OrderFilter): Promise<{
  items: Order[];
  total: number;
}> {
  const params = new URLSearchParams();
  if (filter?.portfolioId) params.append('portfolio_id', filter.portfolioId);
  if (filter?.symbol) params.append('symbol', filter.symbol);
  if (filter?.status) params.append('status', filter.status);
  if (filter?.orderType) params.append('order_type', filter.orderType);
  if (filter?.from) params.append('from', filter.from);
  if (filter?.to) params.append('to', filter.to);
  if (filter?.limit) params.append('limit', String(filter.limit));
  if (filter?.offset) params.append('offset', String(filter.offset));

  const path = `/api/orders?${params.toString()}`;
  const result = await api.get<{ data: { items: Order[]; total: number } }>(path);
  if (result.error) throw result.error;
  return result.data?.data!;
}

/**
 * Cancel an existing order.
 *
 * Only applicable for pending orders not yet sent to broker.
 * Partially filled orders cannot be cancelled (use modify instead).
 *
 * @param orderId - Order UUID
 * @param request - Cancellation metadata
 */
export async function cancelOrder(orderId: string, _request?: CancelOrderRequest): Promise<void> {
  // Backend serves DELETE /orders/{order_id} (routers/orders.py); the
  // PATCH /orders/{id}/cancel contract was aligned to it (2026-08-14).
  const result = await api.delete(`/api/orders/${orderId}`);
  if (result.error) throw result.error;
}

/**
 * Modify order parameters.
 *
 * Allows price/volume adjustments for limit orders before fill.
 * Stops are converted to stop-limit when modified.
 *
 * @param orderId - Order UUID
 * @param updates - Fields to update (price or volume only)
 */
export async function modifyOrder(
  orderId: string,
  updates: { price?: number; volume?: number }
): Promise<Order> {
  const result = await api.patch<{ data: Order }>(`/api/orders/${orderId}`, updates);
  if (result.error) throw result.error;
  return result.data?.data!;
}

/**
 * Cancel all orders for a symbol/portfolio.
 *
 * Bulk cancellation endpoint for emergency stops or repositioning.
 * Returns count of successfully cancelled orders.
 *
 * @param portfolioId - Target portfolio
 * @param symbol - Symbol to cancel (optional, cancels all if omitted)
 */
export async function cancelAllOrders(portfolioId: string, symbol?: string): Promise<{
  cancelled: number;
  failed: number;
}> {
  const params = symbol ? `?symbol=${encodeURIComponent(symbol)}` : '';
  const result = await api.delete<{ data: { cancelled: number; failed: number } }>(
    `/api/portfolio/${portfolioId}/orders${params}`
  );
  if (result.error) throw result.error;
  return result.data?.data!;
}

/**
 * Get order execution history.
 *
 * Returns complete transaction log for an order including:
 * - Fill events with prices and volumes
 * - Rejection reasons
 * - Modification timestamps
 */
export async function getOrderHistory(orderId: string): Promise<Array<{
  event: string;
  timestamp: string;
  price?: number;
  volume?: number;
  message?: string;
}>> {
  const result = await api.get<{ data: Array<{
    event: string;
    timestamp: string;
    price?: number;
    volume?: number;
    message?: string;
  }> }>(`/api/orders/${orderId}/history`);
  if (result.error) throw result.error;
  return result.data?.data ?? [];
}

/**
 * Bulk get order statuses.
 *
 * Optimized for polling multiple orders simultaneously.
 * Returns minimal status summary without full order details.
 *
 * @param orderIds - List of order UUIDs
 * @returns Map of orderId → status summary
 */
export async function bulkGetOrderStatuses(orderIds: string[]): Promise<Map<string, {
  status: Order['status'];
  filled_volume: number;
  last_update: string;
}>> {
  const searchParams = new URLSearchParams(orderIds.map((id) => ['ids', id]));
  const result = await api.get<{ data: Record<string, {
    status: Order['status'];
    filled_volume: number;
    last_update: string;
  }> }>(`/api/orders/bulk/status?${searchParams.toString()}`);
  if (result.error) throw result.error;
  return new Map(Object.entries(result.data?.data ?? {}));
}
