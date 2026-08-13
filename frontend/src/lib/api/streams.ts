// Copyright (c) 2026 Lumine. All rights reserved.
/**
 * Server-sent events (SSE) client per D9-6 (Event Streaming).
 *
 * Implements Phase 9 streaming contracts:
 * - Portfolio updates (NAV, positions change)
 * - Order lifecycle events (pending → filled/rejected)
 * - Market data streams (tick-by-tick price updates)
 * - Workflow progress (agent task execution)
 */

import { cancelAllRequests } from './core';
import type { SSEEvent } from './types';

export class SseError extends Error {
  constructor(
    message: string,
    public code: string = 'SSE_ERROR',
    public event?: unknown
  ) {
    super(message);
    this.name = 'SseError';
  }
}

export class SseConnectionError extends SseError {
  constructor(message = 'Connection failed') {
    super(message, 'CONNECTION_FAILED');
  }
}

export class SseTimeoutError extends SseError {
  constructor(message = 'Connection timeout') {
    super(message, 'CONNECTION_TIMEOUT');
  }
}

export class SseReconnectExhaustedError extends SseError {
  constructor(attempts: number, lastError: unknown) {
    super(`Max reconnect attempts (${attempts}) reached`, 'RECONNECT_EXHAUSTED', lastError);
  }
}

interface SseOptions {
  /** Event types to subscribe to (default: all) */
  events?: string[];
  /** Request headers (e.g., auth tokens) */
  headers?: Record<string, string>;
  /** Connection timeout in ms (default: 15s) */
  connectTimeout?: number;
  /** Reconnection delay in ms (default: 1s) */
  reconnectDelay?: number;
  /** Maximum reconnect attempts (-1 = infinite, default: 3) */
  maxReconnectAttempts?: number;
}

interface SseCallbacks<T> {
  onMessage?: (event: T) => void;
  onError?: (error: SseError) => void;
  onClose?: () => void;
  onOpen?: () => void;
  onReconnect?: (attempt: number) => void;
}

/**
 * SSE connection wrapper with reconnection logic.
 *
 * Per Phase 10 requirements:
 * - Smooth 60 FPS interaction with live updates
 * - Fast initial load (<1s connection establishment)
 * - Graceful degradation on network issues
 *
 * @param url - Full URL including protocol and port
 * @param callbacks - Optional event handlers
 * @param options - Connection configuration
 */
export function useSse<T>(
  url: string,
  callbacks?: SseCallbacks<T>,
  options: SseOptions = {}
): {
  isConnected: boolean;
  isConnecting: boolean;
  reconnectCount: number;
  connect: () => void;
  disconnect: () => void;
} {
  const {
    events,
    connectTimeout = 15_000,
    maxReconnectAttempts = 3,
  } = options;

  let source: EventSource | null = null;
  let reconnectAttempt = 0;
  let connectTimer: ReturnType<typeof setTimeout> | null = null;
  let isManualClose = false;

  const { onMessage, onError, onClose, onOpen, onReconnect } = callbacks ?? {};

  const scheduleConnect = () => {
    if (isManualClose) return;

    if (reconnectAttempt >= maxReconnectAttempts && maxReconnectAttempts > 0) {
      handleError(new SseReconnectExhaustedError(reconnectAttempt, null));
      return;
    }

    onReconnect?.(reconnectAttempt + 1);
    connect();
  };

  const startConnectTimer = () => {
    connectTimer = setTimeout(() => {
      handleError(new SseTimeoutError('Connection did not establish in time'));
    }, connectTimeout);
  };

  const clearConnectTimer = () => {
    if (connectTimer) {
      clearTimeout(connectTimer);
      connectTimer = null;
    }
  };

  const handleEvent = (event: MessageEvent) => {
    clearConnectTimer();

    try {
      const parsed: SSEEvent<T> = JSON.parse(event.data);

      if (events && !events.includes(parsed.event)) {
        return; // Skip unrelated events
      }

      onMessage?.(parsed.data);
    } catch (parseError) {
      handleError(new SseError('Failed to parse SSE message', 'PARSE_ERROR', event));
    }
  };

  const handleOpen = () => {
    clearConnectTimer();
    reconnectAttempt = 0;
    isManualClose = false;
    onOpen?.();
  };

  const handleError = (error: SseError) => {
    clearConnectTimer();
    onError?.(error);

    if (source?.readyState === EventSource.CONNECTING) {
      source.close();
      source = null;
    }

    if (!isManualClose && reconnectAttempt < (maxReconnectAttempts || Infinity)) {
      reconnectAttempt++;
      scheduleConnect();
    }
  };

  const connect = () => {
    if (source?.readyState === EventSource.OPEN) {
      return; // Already connected
    }

    isManualClose = false;
    source = new EventSource(url);

    source.onopen = handleOpen;
    source.onmessage = handleEvent;
    source.onerror = () => handleError(new SseConnectionError('Connection error'));

    startConnectTimer();
  };

  const disconnect = () => {
    isManualClose = true;
    clearConnectTimer();

    if (source) {
      source.close();
      source = null;
    }

    reconnectAttempt = 0;
    onClose?.();
  };

  return {
    // Getters evaluate `source` at property-access time (after this function
    // returns), so the closure keeps the declared `EventSource | null` type
    // instead of the narrowed `never` TypeScript infers at this return point.
    get isConnected() {
      return source?.readyState === EventSource.OPEN;
    },
    get isConnecting() {
      return source?.readyState === EventSource.CONNECTING;
    },
    reconnectCount: reconnectAttempt,
    connect,
    disconnect,
  };
}

/**
 * Convenience wrapper that immediately connects and returns unsubscribe handler.
 *
 * @param url - SSE endpoint URL
 * @param callback - Single event handler
 * @param options - Connection options
 * @returns Unsubscribe function
 */
export function subscribeToSse<T>(
  url: string,
  callback: (data: T) => void,
  options?: SseOptions
): () => void {
  const { connect, disconnect } = useSse<T>(url, { onMessage: callback }, options);
  connect();

  return disconnect;
}

/**
 * Create typed SSE client for a specific domain.
 *
 * Example usage:
 * ```ts
 * const portfolioStream = sseClient<PortfolioSummary>(`/api/portfolio/summary?portfolios=${id}`);
 * portfolioStream.events.on('portfolio_update', (data) => setState(data));
 * ```
 */
export function sseClient<T>(url: string, options: SseOptions = {}) {
  let instance: ReturnType<typeof useSse<T>> | null = null;
  let subscribers = new Map<string, Set<(data: T) => void>>();

  const setupListener = () => {
    if (instance) return instance;

    instance = useSse<T>(url, {
      onMessage: (data) => {
        subscribers.forEach((subs) => {
          subs.forEach(cb => cb(data));
        });
      },
      onError: (error) => {
        console.error('[SSE]', error);
        subscribers.forEach((subs) => {
          subs.forEach(cb => cb(null as any)); // Trigger error handling
        });
      },
      onClose: () => {
        console.warn('[SSE] Connection closed');
      },
      onOpen: () => {
        console.log('[SSE] Connected');
      },
    }, options);

    return instance;
  };

  const subscribe = (eventType: string, callback: (data: T) => void) => {
    const listener = setupListener();
    if (!subscribers.has(eventType)) {
      subscribers.set(eventType, new Set());
    }
    subscribers.get(eventType)?.add(callback);

    // Auto-connect on first subscription
    if (listener.isConnected) return;
    listener.connect();

    // Return unsubscribe handler
    return () => {
      subscribers.get(eventType)?.delete(callback);
      if (subscribers.get(eventType)?.size === 0) {
        subscribers.delete(eventType);
      }
    };
  };

  const unsubscribeAll = () => {
    cancelAllRequests('SSE client destroyed');
    instance?.disconnect();
    subscribers.clear();
  };

  return {
    subscribe,
    unsubscribe: unsubscribeAll,
    get connection() {
      const listener = setupListener();
      return {
        isConnected: listener.isConnected,
        isConnecting: listener.isConnecting,
        reconnectCount: listener.reconnectCount,
      };
    },
  };
}
