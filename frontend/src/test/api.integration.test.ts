// Copyright (c) 2026 Lumine. All rights reserved.
/**
 * Integration tests for frontend-backend API communication.
 *
 * Verifies:
 * - End-to-end request/response cycles
 * - Error handling and validation
 * - SSE streaming functionality
 * - Optimistic updates in React hooks
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import type { MockedFunction } from 'vitest';

import { api, cancelAllRequests } from '../lib/api/core';
import { mapResponseToError, extractResponse, ValidationError } from '../lib/api/errors';
import { useSse } from '../lib/api/streams';
import * as portfolioClient from '../lib/api/clients/portfolioClient';
import * as ordersClient from '../lib/api/clients/ordersClient';
import * as adminClient from '../lib/api/clients/adminClient';
import { QUERY_KEYS } from '../hooks/api/usePortfolio';
import { QUERY_KEYS as OrdersQueryKeys } from '../hooks/api/useOrders';
import type { PortfolioSummary } from '../lib/api/types';

// Mock fetch globally
global.fetch = vi.fn();

describe('API Integration', () => {
  const mockEnv = { VITE_API_URL: 'http://localhost:8000' };

  beforeEach(() => {
    // PITFALL: vi.stubGlobal('import.meta') tidak bekerja — import.meta
    // adalah object spesial. Gunakan vi.stubEnv (Vitest native env stub).
    vi.stubEnv('VITE_API_URL', mockEnv.VITE_API_URL);
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
    cancelAllRequests('test cleanup');
  });

  describe('HTTP Client', () => {
    it('successfully fetches data envelope', async () => {
      const mockData = { data: { test: 'value' } };
      const response = new Response(JSON.stringify(mockData), { status: 200, headers: { 'Content-Type': 'application/json' } });
      (global.fetch as MockedFunction<typeof global.fetch>).mockResolvedValueOnce(response);

      const result = await api.get<{ data: unknown }>('/api/test');
      expect(result.ok).toBe(true);
      expect(result.data?.data).toEqual(mockData.data);
    });

    it('throws ApiError on 404', async () => {
      const response = new Response(JSON.stringify({ detail: 'Not found' }), { status: 404 });
      (global.fetch as MockedFunction<typeof global.fetch>).mockResolvedValueOnce(response);

      const result = await api.get('/api/not-found');
      expect(result.ok).toBe(false);
      expect(result.error?.name).toBe('NotFoundError');
      expect((result.error as { statusCode?: number }).statusCode).toBe(404);
    });

    it('throws ApiError on 500', async () => {
      const response = new Response(JSON.stringify({ detail: 'Internal server error' }), { status: 500 });
      (global.fetch as MockedFunction<typeof global.fetch>).mockResolvedValueOnce(response);

      const result = await api.get('/api/error');
      expect(result.ok).toBe(false);
      expect(result.error?.name).toBe('ApiError');
      expect((result.error as { statusCode?: number }).statusCode).toBe(500);
    });

    it('handles timeout gracefully', async () => {
      // Never resolve on its own; reject when the client's abort signal fires.
      (global.fetch as MockedFunction<typeof global.fetch>).mockImplementationOnce((_input, init) =>
        new Promise((_resolve, reject) => {
          init?.signal?.addEventListener('abort', () => {
            const abortError = new Error('Aborted');
            abortError.name = 'AbortError';
            reject(abortError);
          });
        })
      );

      const result = await api.get('/api/slow', { timeout: 10 });
      expect(result.ok).toBe(false);
      expect(result.error?.name).toBe('TimeoutError');
    });
  });

  describe('Error Mapping', () => {
    it('maps 422 to ValidationError with field errors', async () => {
      const mockJson = {
        detail: 'Validation failed',
        errors: [
          { loc: ['body', 'volume'], msg: 'Must be positive' },
          { loc: ['body', 'price'], msg: 'Required for limit orders' },
        ],
      };
      const response = new Response(JSON.stringify(mockJson), {
        status: 422,
        headers: { 'Content-Type': 'application/json' },
      });

      try {
        await mapResponseToError(response);
        expect.fail('Expected error');
      } catch (error: any) {
        expect(error instanceof ValidationError).toBe(true);
        expect(error.fieldErrors.volume).toContain('Must be positive');
        expect(error.fieldErrors.price).toContain('Required for limit orders');
      }
    });

    it('maps 401 to AuthenticationError', async () => {
      const response = new Response(JSON.stringify({ detail: 'Unauthorized' }), { status: 401 });
      try {
        await mapResponseToError(response);
      } catch (error: any) {
        expect(error.name).toBe('AuthenticationError');
      }
    });

    it('extracts response data from successful responses', async () => {
      const mockData = { portfolio_id: 'abc-123', nav: 100000 };
      const response = new Response(JSON.stringify({ data: mockData }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      });
      const extracted = await extractResponse<{ data: PortfolioSummary }>(response);
      expect(extracted).toEqual({ data: mockData });
    });
  });

  describe('Domain Clients', () => {
    it('portfolioClient.getPortfolioSummary builds correct URL', async () => {
      const mockSummary: PortfolioSummary = {
        portfolio_id: 'p1',
        nav: 100000,
        cash: 50000,
        margin_used: 10000,
        open_pnl: 2500,
        closed_pnl: 5000,
        timestamp: new Date().toISOString(),
      };

      const response = new Response(JSON.stringify({ data: mockSummary }), { status: 200, headers: { 'Content-Type': 'application/json' } });
      (global.fetch as MockedFunction<typeof global.fetch>).mockResolvedValueOnce(response);

      const result = await portfolioClient.getPortfolioSummary('p1');
      expect(result.portfolio_id).toBe('p1');
      expect(result.nav).toBe(100000);
    });

    it('portfolioClient.listPortfolios includes query params', async () => {
      const mockList = { items: [], total: 0 };
      const response = new Response(JSON.stringify({ data: mockList }), { status: 200, headers: { 'Content-Type': 'application/json' } });
      (global.fetch as MockedFunction<typeof global.fetch>).mockResolvedValueOnce(response);

      await portfolioClient.listPortfolios({ status: 'active', limit: 10, offset: 0 });

      const call = (global.fetch as MockedFunction<typeof global.fetch>).mock.calls[0];
      const url = call[0] as string;
      expect(url).toContain('status=active');
      expect(url).toContain('limit=10');
    });
  });

  describe('SSE Streaming', () => {
    // Captures every `new EventSource(url)` instance so tests can drive the
    // onopen/onmessage/onerror handlers the client wires up.
    let sources: Array<{
      url: string;
      readyState: number;
      onopen: ((ev: Event) => void) | null;
      onmessage: ((ev: MessageEvent) => void) | null;
      onerror: ((ev: Event) => void) | null;
      close: () => void;
    }> = [];

    beforeEach(() => {
      sources = [];
      vi.stubGlobal('EventSource', class MockEventSource {
        static CONNECTING = 0;
        static OPEN = 1;
        static CLOSED = 2;
        readyState = MockEventSource.CONNECTING;
        onopen: ((ev: Event) => void) | null = null;
        onmessage: ((ev: MessageEvent) => void) | null = null;
        onerror: ((ev: Event) => void) | null = null;
        close = vi.fn();
        constructor(public url: string) {
          sources.push(this);
        }
      });
    });

    afterEach(() => {
      vi.unstubAllGlobals();
    });

    it('connects and receives messages', () => {
      const mockData = { event: 'portfolio_update', data: { portfolio_id: 'p1', nav: 100000 } };
      const messageCallback = vi.fn();
      const openCallback = vi.fn();

      const listener = useSse('http://localhost:8000/api/streams/portfolio/p1', {
        onMessage: messageCallback,
        onOpen: openCallback,
      });

      // No connection until explicitly requested.
      expect(listener.isConnected).toBe(false);

      listener.connect();
      expect(sources).toHaveLength(1);

      // Simulate the server accepting the connection.
      sources[0]!.readyState = EventSource.OPEN;
      sources[0]!.onopen?.(new Event('open'));
      expect(openCallback).toHaveBeenCalled();
      expect(listener.isConnected).toBe(true);

      // Simulate an incoming SSE message.
      sources[0]!.onmessage?.(new MessageEvent('message', { data: JSON.stringify(mockData) }));
      expect(messageCallback).toHaveBeenCalledWith(mockData.data);

      // Stop the pending connect-timeout timer.
      listener.disconnect();
    });

    it('reconnects after transient failures', () => {
      const reconnectHandler = vi.fn();

      const listener = useSse('http://localhost:8000/api/streams/portfolio/p1', {
        onReconnect: reconnectHandler,
      });

      expect(reconnectHandler).not.toHaveBeenCalled();

      listener.connect();
      expect(sources).toHaveLength(1);

      // Transient failure while CONNECTING: client tears down and retries.
      sources[0]!.onerror?.(new Event('error'));
      expect(reconnectHandler).toHaveBeenCalledTimes(1);
      expect(sources).toHaveLength(2);

      listener.disconnect();
    });

    it('manually disconnects successfully', () => {
      const disconnectHandler = vi.fn();
      const listener = useSse('http://localhost:8000/api/streams/portfolio/p1', { onClose: disconnectHandler });

      listener.connect();
      expect(sources).toHaveLength(1);

      listener.disconnect();

      expect(disconnectHandler).toHaveBeenCalled();
      expect(sources[0]!.close).toHaveBeenCalled();
    });
  });

  describe('React Query Hooks', () => {
    it('usePortfolioSummary generates correct query key', () => {
      const portfolioId = 'p123-abc';
      const expectedKey = [...QUERY_KEYS.portfolios.details(portfolioId)];

      expect(expectedKey[0]).toBe('portfolios');
      expect(expectedKey[2]).toBe(portfolioId);
    });

    it('useOrder query includes orderId in key', () => {
      const orderId = 'order-xyz';
      const expectedKey = OrdersQueryKeys.orders.detail(orderId);

      expect(expectedKey[0]).toBe('orders');
      expect(expectedKey[1]).toBe(orderId);
    });
  });

  describe('Edge Cases', () => {
    it('handles missing data field in envelope', async () => {
      const response = new Response(JSON.stringify({ metadata: {} }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      });
      (global.fetch as MockedFunction<typeof global.fetch>).mockResolvedValueOnce(response);

      const result = await api.get<any>('/api/test');
      expect(result.ok).toBe(false);
      expect((result.error as { code?: string }).code).toBe('MISSING_DATA');
    });

    it('handles invalid JSON content type', async () => {
      const response = new Response('<html></html>', {
        status: 200,
        headers: { 'Content-Type': 'text/html' },
      });
      (global.fetch as MockedFunction<typeof global.fetch>).mockResolvedValueOnce(response);

      const result = await api.get('/api/test');
      expect(result.ok).toBe(false);
      expect((result.error as { code?: string }).code).toBe('INVALID_CONTENT_TYPE');
    });
  });

  describe('API version prefix (Phase 9 /api/v1)', () => {
    it('rewrites bare /api/* paths onto /api/v1/*', async () => {
      const response = new Response(JSON.stringify({ data: { ok: true } }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      });
      (global.fetch as MockedFunction<typeof global.fetch>).mockResolvedValueOnce(response);

      await api.get('/api/orders/abc-123');

      const url = (global.fetch as MockedFunction<typeof global.fetch>).mock.calls[0][0] as string;
      expect(url).toContain('http://localhost:8000/api/v1/orders/abc-123');
    });

    it('leaves already-versioned /api/v1/* paths untouched', async () => {
      const response = new Response(JSON.stringify({ data: { ok: true } }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      });
      (global.fetch as MockedFunction<typeof global.fetch>).mockResolvedValueOnce(response);

      await api.get('/api/v1/market/quote/XAUUSD');

      const url = (global.fetch as MockedFunction<typeof global.fetch>).mock.calls[0][0] as string;
      expect(url).toContain('http://localhost:8000/api/v1/market/quote/XAUUSD');
      expect(url).not.toContain('/api/v1/api/v1');
    });
  });

  describe('Admin Client', () => {
    it('setKillSwitch posts {armed, reason, tier} to /api/v1/admin/kill-switch', async () => {
      const mockStatus = {
        data: { armed: true, reason: 'news shock', tier: 'book', updated_at: null },
      };
      const response = new Response(JSON.stringify(mockStatus), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      });
      (global.fetch as MockedFunction<typeof global.fetch>).mockResolvedValueOnce(response);

      const status = await adminClient.setKillSwitch({
        armed: true,
        reason: 'news shock',
        tier: 'book',
      });

      expect(status.armed).toBe(true);
      expect(status.tier).toBe('book');

      const [url, init] = (global.fetch as MockedFunction<typeof global.fetch>).mock.calls[0] as [
        string,
        RequestInit
      ];
      expect(url).toContain('/api/v1/admin/kill-switch');
      expect(init.method).toBe('POST');
      expect(JSON.parse(String(init.body))).toEqual({
        armed: true,
        reason: 'news shock',
        tier: 'book',
      });
    });

    it('createApiKey returns the one-time secret', async () => {
      const mockCreated = {
        data: { key_id: 'key-abc', secret: 'sk-live-secret', scopes: ['market.read'], created_at: '2026-08-14T00:00:00Z' },
      };
      const response = new Response(JSON.stringify(mockCreated), {
        status: 201,
        headers: { 'Content-Type': 'application/json' },
      });
      (global.fetch as MockedFunction<typeof global.fetch>).mockResolvedValueOnce(response);

      const created = await adminClient.createApiKey({
        key_id: 'key-abc',
        scopes: ['market.read'],
      });

      expect(created.secret).toBe('sk-live-secret');
      const url = (global.fetch as MockedFunction<typeof global.fetch>).mock.calls[0][0] as string;
      expect(url).toContain('/api/v1/admin/keys');
    });
  });

  describe('Order Cancel Alignment', () => {
    it('cancelOrder issues DELETE /api/v1/orders/{id}', async () => {
      const response = new Response(JSON.stringify({ data: { order_id: 'o1' } }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      });
      (global.fetch as MockedFunction<typeof global.fetch>).mockResolvedValueOnce(response);

      await ordersClient.cancelOrder('o1');

      const [url, init] = (global.fetch as MockedFunction<typeof global.fetch>).mock.calls[0] as [
        string,
        RequestInit
      ];
      expect(url).toContain('/api/v1/orders/o1');
      expect(init.method).toBe('DELETE');
    });
  });
});
