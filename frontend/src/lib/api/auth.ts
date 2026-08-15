// Copyright (c) 2026 Lumine. All rights reserved.
/**
 * HMAC-SHA256 authentication per docs/09-api/auth.md (D9-4).
 *
 * Backend contract (backend/src/lumine/api/middleware/auth.py):
 * - Headers: X-Lumine-API-Key, X-Lumine-Timestamp (unix seconds), X-Lumine-Signature
 * - Payload:  `{METHOD}\n{path_with_query}\n{timestamp}\n{sha256(body_hex)}`
 * - Replay cache keyed on (api_key, timestamp, body_hash) → the client paces
 *   timestamps so two requests never share (timestamp, body_hash).
 */

export class AuthenticationError extends Error {
  constructor(message: string, public code: string = 'AUTH_FAILED') {
    super(message);
    this.name = 'AuthenticationError';
  }
}

export interface SignatureComponents {
  timestamp: string;
  signature: string;
}

/**
 * Compute hex SHA-256 digest of a UTF-8 string (Web Crypto).
 */
export async function sha256Hex(message: string): Promise<string> {
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(message));
  return Array.from(new Uint8Array(digest))
    .map((b) => b.toString(16).padStart(2, '0'))
    .join('');
}

/**
 * Compute hex HMAC-SHA256 of a message (Web Crypto).
 */
async function computeSignature(message: string, secret: string): Promise<string> {
  const cryptoKey = await crypto.subtle.importKey(
    'raw',
    new TextEncoder().encode(secret),
    { name: 'HMAC', hash: 'SHA-256' },
    false,
    ['sign']
  );
  const signature = await crypto.subtle.sign('HMAC', cryptoKey, new TextEncoder().encode(message));
  return Array.from(new Uint8Array(signature))
    .map((b) => b.toString(16).padStart(2, '0'))
    .join('');
}

/**
 * Paced unix-seconds timestamp. The backend replay cache keys on
 * (api_key, timestamp, body_hash), so every request in this session gets a
 * strictly increasing timestamp — same-second bursts sign ts, ts+1, ts+2…
 * (still inside the ±300 s window) instead of colliding as replays.
 */
let _lastTimestamp = 0;

export function nextTimestamp(nowSeconds: number = Math.floor(Date.now() / 1000)): string {
  const ts = Math.max(nowSeconds, _lastTimestamp + 1);
  _lastTimestamp = ts;
  return String(ts);
}

/**
 * Sign a request per docs/09-api/auth.md.
 *
 * @param method - HTTP method (GET, POST, PATCH, DELETE, …)
 * @param path - Path with query string exactly as sent to the server
 *               (e.g. `/api/v1/orders?limit=10`)
 * @param body - Serialized request body (empty string when no body)
 * @param apiSecret - HMAC secret for the API key
 * @returns Signature components for the X-Lumine-* headers
 */
export async function signRequest(
  method: string,
  path: string,
  body: string,
  apiSecret: string
): Promise<SignatureComponents> {
  const timestamp = nextTimestamp();
  const payload = `${method}\n${path}\n${timestamp}\n${await sha256Hex(body)}`;
  const signature = await computeSignature(payload, apiSecret);
  return { timestamp, signature };
}

/**
 * Build the X-Lumine-* headers required by the backend auth middleware.
 */
export async function buildAuthHeaders(
  method: string,
  path: string,
  body: string,
  apiKey: string,
  apiSecret: string
): Promise<Record<string, string>> {
  const { timestamp, signature } = await signRequest(method, path, body, apiSecret);
  return {
    'X-Lumine-API-Key': apiKey,
    'X-Lumine-Timestamp': timestamp,
    'X-Lumine-Signature': signature,
  };
}

/**
 * HMAC credentials from the environment, when configured.
 *
 * VITE_LUMINE_API_KEY + VITE_LUMINE_API_SECRET must BOTH be set for the
 * client to sign requests; otherwise requests go out unsigned (dev mode).
 */
export function getHmacCredentials(): { apiKey: string; apiSecret: string } | null {
  const apiKey = import.meta.env?.VITE_LUMINE_API_KEY;
  const apiSecret = import.meta.env?.VITE_LUMINE_API_SECRET;
  if (typeof apiKey === 'string' && apiKey.length > 0 && typeof apiSecret === 'string' && apiSecret.length > 0) {
    return { apiKey, apiSecret };
  }
  return null;
}

/**
 * Validate response timestamp against replay attack window.
 *
 * @param timestampISO - ISO-8601 timestamp from request
 * @param maxAgeSeconds - Maximum age in seconds (default: 300)
 * @returns true if timestamp is valid, false otherwise
 */
export function isTimestampValid(timestampISO: string, maxAgeSeconds: number = 300): boolean {
  const now = Date.now();
  const requestTime = new Date(timestampISO).getTime();
  const diffSeconds = Math.abs(now - requestTime) / 1000;
  return diffSeconds <= maxAgeSeconds;
}

/**
 * Verify server response timestamp for replay protection.
 *
 * @param responseHeaders - Raw response headers
 * @param maxAgeSeconds - Allowed timestamp age
 * @throws AuthenticationError if validation fails
 */
export function validateResponseTimestamp(responseHeaders: Headers, maxAgeSeconds: number = 300): void {
  const timestamp = responseHeaders.get('X-Lumine-Timestamp');
  if (!timestamp) {
    throw new AuthenticationError('Missing timestamp header', 'MISSING_TIMESTAMP');
  }
  if (!isTimestampValid(timestamp, maxAgeSeconds)) {
    throw new AuthenticationError('Response timestamp expired', 'TIMESTAMP_EXPIRED');
  }
}

/** Test hook: reset the timestamp pacing. */
export function resetTimestampPacing(): void {
  _lastTimestamp = 0;
}
