/**
 * Lumine API client — thin fetch wrapper for Phase 9 REST contracts.
 *
 * Reads `VITE_API_BASE_URL` from the environment (defaults to the local
 * backend). Returns the `data` field of the common envelope and maps
 * errors to typed `ApiError` instances.
 *
 * HMAC-SHA256 signing is Phase 14 scope; headers can be injected through
 * `options.headers` without changing call sites.
 */

const DEFAULT_BASE_URL = "http://localhost:8000/api/v1";

export interface ApiEnvelope<T> {
  meta: {
    api_version: string;
    timestamp: string;
    request_id: string;
    status: "ok" | "error";
    idempotent_replay?: boolean;
  };
  data: T | null;
  error: ApiErrorPayload | null;
}

export interface ApiErrorPayload {
  code: string;
  message: string;
  details: Record<string, unknown>;
  trace_id: string;
}

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
    public readonly code: string,
    public readonly traceId: string,
    public readonly details: Record<string, unknown> = {}
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export interface RequestOptions {
  headers?: Record<string, string>;
  signal?: AbortSignal;
}

function getBaseUrl(): string {
  const env = import.meta.env?.VITE_API_BASE_URL;
  return typeof env === "string" && env.length > 0 ? env : DEFAULT_BASE_URL;
}

function buildUrl(path: string, params?: Record<string, string | string[]>): string {
  const base = getBaseUrl().replace(/\/$/, "");
  const normalized = path.startsWith("/") ? path : `/${path}`;
  const url = new URL(`${base}${normalized}`);

  if (params) {
    for (const [key, value] of Object.entries(params)) {
      if (Array.isArray(value)) {
        url.searchParams.set(key, value.join(","));
      } else {
        url.searchParams.set(key, value);
      }
    }
  }

  return url.toString();
}

async function parseEnvelope<T>(response: Response): Promise<ApiEnvelope<T>> {
  const text = await response.text();
  try {
    return JSON.parse(text) as ApiEnvelope<T>;
  } catch {
    throw new ApiError(
      "Invalid JSON response from server",
      response.status,
      "INVALID_RESPONSE",
      ""
    );
  }
}

function throwOnError<T>(envelope: ApiEnvelope<T>, status: number, allowNull?: false): T;
function throwOnError<T>(envelope: ApiEnvelope<T>, status: number, allowNull: true): T | null;
function throwOnError<T>(envelope: ApiEnvelope<T>, status: number, allowNull = false): T | null {
  if (envelope.meta.status === "error" || envelope.error) {
    const err = envelope.error ?? {
      code: "UNKNOWN_ERROR",
      message: "Unknown server error",
      details: {},
      trace_id: "",
    };
    throw new ApiError(err.message, status, err.code, err.trace_id, err.details);
  }

  if (envelope.data === null && !allowNull) {
    throw new ApiError("Response data is null", status, "EMPTY_RESPONSE", "");
  }

  return envelope.data as T;
}

export async function get<T>(
  path: string,
  params?: Record<string, string | string[]>,
  options: RequestOptions = {}
): Promise<T> {
  const response = await fetch(buildUrl(path, params), {
    method: "GET",
    headers: {
      Accept: "application/json",
      ...options.headers,
    },
    signal: options.signal,
  });

  const envelope = await parseEnvelope<T>(response);
  return throwOnError(envelope, response.status);
}

export async function post<T>(
  path: string,
  body: unknown,
  options: RequestOptions = {}
): Promise<T> {
  const response = await fetch(buildUrl(path), {
    method: "POST",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
      ...options.headers,
    },
    body: JSON.stringify(body),
    signal: options.signal,
  });

  const envelope = await parseEnvelope<T>(response);
  return throwOnError(envelope, response.status);
}

export async function del(path: string, options: RequestOptions = {}): Promise<void> {
  const response = await fetch(buildUrl(path), {
    method: "DELETE",
    headers: {
      Accept: "application/json",
      ...options.headers,
    },
    signal: options.signal,
  });

  const envelope = await parseEnvelope<unknown>(response);
  throwOnError(envelope, response.status, true);
}
