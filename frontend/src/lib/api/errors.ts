// Copyright (c) 2026 Lumine. All rights reserved.
/**
 * Unified frontend error types mapping to backend LumineError.
 *
 * Provides consistent error handling across all API clients and hooks.
 */

import type { PortfolioSummary, Position, ExposureSummary, Order } from './types';

export class ApiError extends Error {
  constructor(
    message: string,
    public statusCode: number,
    public code: string,
    public details?: Record<string, unknown>
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

export class ValidationError extends ApiError {
  constructor(
    message: string,
    public fieldErrors: Record<string, string[]>,
    public statusCode: number = 422
  ) {
    super(message, statusCode, 'VALIDATION_ERROR', { fieldErrors });
    this.name = 'ValidationError';
  }
}

export class AuthenticationError extends ApiError {
  constructor(message: string, public code: string = 'AUTH_FAILED') {
    super(message, 401, code);
    this.name = 'AuthenticationError';
  }
}

export class AuthorizationError extends ApiError {
  constructor(message: string = 'Access denied', public code: string = 'FORBIDDEN') {
    super(message, 403, code);
    this.name = 'AuthorizationError';
  }
}

export class NotFoundError extends ApiError {
  constructor(resource: string, public resourceId?: string) {
    const message = `${resource}${resourceId ? ` "${resourceId}"` : ' not found'}`;
    super(message, 404, 'NOT_FOUND');
    this.name = 'NotFoundError';
  }
}

export class TimeoutError extends ApiError {
  constructor(message = 'Request timed out', public code: string = 'TIMEOUT') {
    super(message, 408, code);
    this.name = 'TimeoutError';
  }
}

export class RateLimitError extends ApiError {
  constructor(
    message = 'Rate limit exceeded',
    public retryAfter?: number
  ) {
    super(message, 429, 'RATE_LIMITED', retryAfter ? { retryAfter } : undefined);
    this.name = 'RateLimitError';
  }
}

export class NetworkError extends ApiError {
  constructor(message: string, public cause?: unknown) {
    super(message, 0, 'NETWORK_ERROR', { cause: message });
    this.name = 'NetworkError';
  }
}

export class UnexpectedResponseError extends ApiError {
  constructor(message: string, public rawResponse?: unknown) {
    super(message, 500, 'UNEXPECTED_RESPONSE');
    this.name = 'UnexpectedResponseError';
  }
}

/**
 * Map backend LumineError response to frontend error types.
 *
 * Handles FastAPI exception responses per Phase 9 API contract:
 * - 400 Bad Request → ApiError
 * - 401 Unauthorized → AuthenticationError
 * - 403 Forbidden → AuthorizationError
 * - 404 Not Found → NotFoundError
 * - 422 Validation → ValidationError
 * - 5xx Server errors → ApiError
 *
 * @param response - Fetch Response object
 * @returns Promise that rejects with appropriate frontend error type
 */
export async function mapResponseToError(response: Response): Promise<never> {
  const contentType = response.headers.get('Content-Type') || '';

  let errorData: unknown;
  if (contentType.includes('application/json')) {
    errorData = await response.json();
  } else {
    errorData = { detail: await response.text() };
  }

  const status = response.status;
  const detail = typeof errorData === 'object' && errorData !== null
    ? ('detail' in errorData ? String(errorData.detail) : null)
    : null;

  switch (status) {
    case 401:
      throw new AuthenticationError(
        detail ?? 'Authentication required',
        'AUTH_REQUIRED'
      );

    case 403:
      throw new AuthorizationError(
        detail ?? 'Insufficient permissions',
        'ACCESS_DENIED'
      );

    case 404:
      throw new NotFoundError(detail ?? 'Resource', 'RESOURCE_NOT_FOUND');

    case 422:
      // Handle validation errors with field-level details
      const fieldErrors: Record<string, string[]> = {};
      const errorList = (errorData as { errors?: unknown } | null)?.errors;
      if (Array.isArray(errorList)) {
        for (const err of errorList as Record<string, unknown>[]) {
          const loc = err['loc'] as string[] | undefined;
          const msg = err['msg'] as string | undefined;
          if (loc && msg) {
            const field = loc[loc.length - 1];
            fieldErrors[field] = fieldErrors[field] ?? [];
            fieldErrors[field].push(msg);
          }
        }
      }
      throw new ValidationError(
        detail ?? 'Validation failed',
        fieldErrors,
        422
      );

    case 408:
      throw new TimeoutError(
        detail ?? 'Request timeout',
        'REQUEST_TIMEOUT'
      );

    case 429:
      const retryAfter = response.headers.get('Retry-After');
      throw new RateLimitError(
        detail ?? 'Rate limit exceeded',
        retryAfter ? parseInt(retryAfter, 10) : undefined
      );

    default:
      throw new ApiError(
        detail ?? `HTTP ${status}`,
        status,
        `HTTP_${status.toString()}`,
        errorData as Record<string, unknown>
      );
  }
}

/**
 * Extract success response data with optional deserialization.
 *
 * Type-safe wrapper that handles both JSON parsing and manual deserialization
 * for complex nested objects like PortfolioSummary, Position, etc.
 *
 * @param response - Fetch Response object
 * @param transform - Optional custom parser for response body
 * @throws ApiError if response indicates failure
 * @returns Parsed response data or transformed result
 */
export async function extractResponse<T>(
  response: Response,
  transform?: (data: unknown) => T
): Promise<T> {
  if (!response.ok) {
    await mapResponseToError(response);
    // Should never reach here, but TypeScript needs exhaustiveness check
    throw new ApiError('Unknown error', response.status, 'UNKNOWN_ERROR');
  }

  const contentType = response.headers.get('Content-Type') || '';

  if (transform) {
    return transform(await response.json());
  } else if (contentType.includes('application/json')) {
    return await response.json();
  } else {
    throw new UnexpectedResponseError('Expected JSON response', response);
  }
}

/**
 * Parse envelope response structure.
 *
 * Per Phase 9 API contract, all responses use CommonEnvelope format:
 * { data: T, metadata?: EnvMetadata }
 *
 * @param envelope - Parsed envelope object
 * @param transformer - Optional field transformer for nested data
 * @returns Transformed data payload
 */
export function parseEnvelope<T>(
  envelope: { data: T; metadata?: Record<string, unknown> },
  transformer?: (data: T) => T
): T {
  if (!envelope.data) {
    throw new ApiError('Missing data in envelope', 500, 'MISSING_DATA');
  }

  return transformer ? transformer(envelope.data) : envelope.data;
}

// Re-export common error types for convenience
export type { PortfolioSummary, Position, ExposureSummary, Order };
