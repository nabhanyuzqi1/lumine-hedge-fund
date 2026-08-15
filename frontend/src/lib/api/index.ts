// Copyright (c) 2026 Lumine. All rights reserved.
/**
 * Centralized exports for all API layer modules.
 *
 * Provides unified import structure per Phase 10 design system.
 */

export { api, http, request, cancelAllRequests } from './core';
export type { RequestOptions } from './core';

export {
  ApiError,
  ValidationError,
  AuthenticationError,
  AuthorizationError,
  NotFoundError,
  TimeoutError,
  RateLimitError,
  NetworkError,
  UnexpectedResponseError,
  mapResponseToError,
  extractResponse,
  parseEnvelope,
} from './errors';

export {
  signRequest,
  buildAuthHeaders,
  isTimestampValid,
  validateResponseTimestamp,
} from './auth';
export type { SignatureComponents } from './auth';

export { useSse, subscribeToSse, sseClient, SseError, SseConnectionError, SseTimeoutError, SseReconnectExhaustedError } from './streams';

export type {
  PortfolioSummary,
  Position,
  ExposureSummary,
  Order,
  CreateOrderRequest,
  SSEEvent,
  EnvEnvelope,
  MarketData,
  WorkflowState,
} from './types';
export type { SymbolConfig, OHLCVPoint, Timeframe } from './clients/marketClient';

export * as portfolioClient from './clients/portfolioClient';
export * as ordersClient from './clients/ordersClient';
export * as marketClient from './clients/marketClient';
export * as adminClient from './clients/adminClient';
