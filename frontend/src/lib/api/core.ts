// Copyright (c) 2026 Lumine. All rights reserved.
/**
 * Core HTTP client for Lumine API communication.
 *
 * Provides type-safe fetch wrapper with consistent error handling,
 * timeout management, and common header configuration per Phase 9 API contract.
 */

import { ApiError, mapResponseToError, TimeoutError, NetworkError } from './errors';
import { buildAuthHeaders, getHmacCredentials } from './auth';
import type { EnvEnvelope } from './types';

export interface RequestOptions extends RequestInit {
  /** Request timeout in milliseconds (default: 30s) */
  timeout?: number;
  /** Skip response validation (for edge cases) */
  skipValidate?: boolean;
}

interface ResponseResult<T> {
  ok: boolean;
  status: number;
  headers: Headers;
  data?: T;
  error?: Error;
}

const DEFAULT_TIMEOUT = 30_000; // 30 seconds per D9-6 latency targets

/**
 * Abort controller pool for cleanup on component unmount.
 */
const controllers = new Set<AbortController>();

/**
 * Cancel all pending requests with provided reason.
 */
export function cancelAllRequests(reason: string): void {
  for (const controller of controllers) {
    controller.abort(reason);
  }
  controllers.clear();
}

/**
 * Normalize a request path onto the versioned API prefix.
 *
 * Phase 9 rest-api.md: every domain router is mounted under /api/v1.
 * Clients may pass either bare `/api/...` routes (legacy) or already
 * versioned `/api/v1/...` routes (SSE layer); both resolve here so a
 * single place owns the prefix contract.
 */
export function normalizeApiPath(path: string): string {
  if (path.startsWith('/api/v1/')) return path;
  if (path.startsWith('/api/')) return `/api/v1/${path.slice('/api/'.length)}`;
  return path;
}

/**
 * Build URL from base path and relative route.
 *
 * Handles trailing slashes automatically for clean concatenation.
 */
export function buildUrl(baseUrl: string, path: string): string {
  const base = baseUrl.replace(/\/$/, '');
  const route = normalizeApiPath(path).replace(/^\//, '');
  return `${base}/${route}`;
}

/**
 * Create timeout signal for fetch operations.
 *
 * Per Phase 10 performance requirements, ensures smooth UI even during slow network.
 * Returns aborted signal with custom reason if timeout fires.
 */
export function createTimeoutSignal(timeoutMs: number): AbortSignal {
  const controller = new AbortController();
  const id = setTimeout(() => controller.abort(`Request timeout after ${timeoutMs}ms`), timeoutMs);

  // Cleanup timer when abort happens
  controller.signal.addEventListener('abort', () => clearTimeout(id));

  return controller.signal;
}

/**
 * Parse JSON safely with comprehensive error handling.
 *
 * Throws ApiError with detailed information on parse failure.
 */
async function safeJsonParse<T>(response: Response, url: string): Promise<T> {
  const contentType = response.headers.get('Content-Type') || '';

  if (!contentType.includes('application/json')) {
    const text = await response.text();
    throw new ApiError(
      `Expected JSON but received ${contentType}`,
      response.status,
      'INVALID_CONTENT_TYPE',
      { actual: contentType, preview: text.slice(0, 200) }
    );
  }

  try {
    return await response.json() as T;
  } catch (parseError) {
    throw new ApiError(
      'Failed to parse JSON response',
      response.status,
      'PARSE_ERROR',
      { url, error: String(parseError) }
    );
  }
}

/**
 * Extract and validate envelope structure from response.
 *
 * Per Phase 9 API contract, all responses use CommonEnvelope format:
 * { data: T, metadata?: EnvMetadata }
 *
 * Validates the required `data` field exists, then returns the full envelope.
 * Callers unwrap `.data` (API clients use `result.data!.data`).
 */
async function extractEnvelope<T>(response: Response, url: string): Promise<T> {
  const envelope = await safeJsonParse<EnvEnvelope<unknown>>(response, url);

  if (!envelope.data) {
    throw new ApiError(
      'Missing data field in response envelope',
      response.status,
      'MISSING_DATA',
      { url }
    );
  }

  return envelope as T;
}

/**
 * Perform HTTP request with automatic error handling.
 *
 * Handles:
 * - Network errors → NetworkError
 * - HTTP errors → mapped ApiError types
 * - Timeout errors → TimeoutError
 * - Invalid JSON → ApiError(PARSE_ERROR)
 *
 * Automatically validates response structure unless skipValidate=true.
 *
 * @param method - HTTP method (GET, POST, PUT, DELETE, etc.)
 * @param path - Relative URL path
 * @param options - Fetch options including headers and body
 * @returns Result object with ok/status/data/error
 */
export async function http<T>(
  method: string,
  path: string,
  options: RequestOptions = {}
): Promise<ResponseResult<T>> {
  const { timeout = DEFAULT_TIMEOUT, skipValidate = false, ...fetchOptions } = options;
  const baseUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000';
  const url = buildUrl(baseUrl, path);

  // Merge common headers with user-provided options
  const headers = new Headers(fetchOptions.headers ?? {});
  headers.set('Content-Type', 'application/json');
  headers.set('Accept', 'application/json');

  // HMAC-SHA256 signing per docs/09-api/auth.md when credentials are
  // configured (VITE_LUMINE_API_KEY + VITE_LUMINE_API_SECRET). The signed
  // path is exactly what the server receives (normalized /api/v1 path +
  // query string), so the payload matches authenticate_request.
  const credentials = getHmacCredentials();
  if (credentials) {
    const signTarget = url.replace(/^https?:\/\/[^/]+/, '');
    const authHeaders = await buildAuthHeaders(
      method,
      signTarget,
      String(fetchOptions.body ?? ''),
      credentials.apiKey,
      credentials.apiSecret
    );
    for (const [key, value] of Object.entries(authHeaders)) {
      headers.set(key, value);
    }
  }

  const finalOptions: RequestInit = {
    ...fetchOptions,
    method,
    headers,
    signal: createTimeoutSignal(timeout),
  };

  try {
    const response = await fetch(url, finalOptions);

    // Handle HTTP errors (non-2xx status codes)
    if (!response.ok) {
      await mapResponseToError(response);
      // Should never reach here, but TypeScript needs exhaustiveness
      return {
        ok: false,
        status: response.status,
        headers: response.headers,
        error: new ApiError('Unknown HTTP error', response.status, 'UNKNOWN'),
      };
    }

    // Parse envelope structure if not skipped
    let data: T;
    if (skipValidate) {
      data = await response.json() as T;
    } else {
      data = await extractEnvelope<T>(response, url);
    }

    return { ok: true, status: response.status, headers: response.headers, data };
  } catch (error) {
    // Classify error type
    const isAbort = error instanceof Error && error.name === 'AbortError';

    if (isAbort) {
      return {
        ok: false,
        status: 0,
        headers: new Headers(),
        error: new TimeoutError(String(error)),
      };
    }

    if (error instanceof ApiError) {
      return { ok: false, status: error.statusCode, headers: new Headers(), error };
    }

    return {
      ok: false,
      status: 0,
      headers: new Headers(),
      error: new NetworkError('Network request failed', error),
    };
  }
}

/**
 * Helper methods for REST-style API calls.
 */
export const api = {
  get: <T>(path: string, options?: RequestOptions): Promise<ResponseResult<T>> =>
    http<T>('GET', path, options),

  post: <T>(path: string, body?: unknown, options?: RequestOptions): Promise<ResponseResult<T>> =>
    http<T>('POST', path, { ...options, body: JSON.stringify(body) }),

  put: <T>(path: string, body?: unknown, options?: RequestOptions): Promise<ResponseResult<T>> =>
    http<T>('PUT', path, { ...options, body: JSON.stringify(body) }),

  patch: <T>(path: string, body?: unknown, options?: RequestOptions): Promise<ResponseResult<T>> =>
    http<T>('PATCH', path, { ...options, body: JSON.stringify(body) }),

  delete: <T>(path: string, options?: RequestOptions): Promise<ResponseResult<T>> =>
    http<T>('DELETE', path, options),
};

/**
 * Generic request handler with built-in error handling.
 *
 * Convenience wrapper that returns data directly or throws appropriate error.
 * Use this when you expect successful responses and want immediate error propagation.
 *
 * @throws ApiError and subclasses for all failure cases
 */
export async function request<T>(
  path: string,
  options?: RequestOptions
): Promise<T> {
  const result = await http<T>('GET', path, options);

  if (result.error) {
    throw result.error;
  }

  return result.data!;
}
