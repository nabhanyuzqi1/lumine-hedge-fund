// Copyright (c) 2026 Lumine. All rights reserved.
/**
 * HMAC signing tests — payload scheme must match the backend contract
 * (backend/tests/contract/test_api_contract.py `_sign` and
 * middleware/auth.py `_build_signature_payload`).
 */

import { beforeEach, describe, expect, it, vi } from 'vitest';

import {
  buildAuthHeaders,
  nextTimestamp,
  resetTimestampPacing,
  sha256Hex,
  signRequest,
} from '../lib/api/auth';

const SECRET = 'bootstrap-secret-for-tests';

async function hmacSha256Hex(message: string, secret: string): Promise<string> {
  const cryptoKey = await crypto.subtle.importKey(
    'raw',
    new TextEncoder().encode(secret),
    { name: 'HMAC', hash: 'SHA-256' },
    false,
    ['sign']
  );
  const sig = await crypto.subtle.sign('HMAC', cryptoKey, new TextEncoder().encode(message));
  return Array.from(new Uint8Array(sig))
    .map((b) => b.toString(16).padStart(2, '0'))
    .join('');
}

describe('HMAC request signing (docs/09-api/auth.md)', () => {
  beforeEach(() => {
    resetTimestampPacing();
  });

  it('produces the exact payload the backend verifies', async () => {
    const body = '';
    const { timestamp, signature } = await signRequest(
      'GET',
      '/api/v1/portfolio/summary',
      body,
      SECRET
    );

    const bodyHash = await sha256Hex(body);
    const expected = await hmacSha256Hex(
      `GET\n/api/v1/portfolio/summary\n${timestamp}\n${bodyHash}`,
      SECRET
    );
    expect(signature).toBe(expected);
    expect(timestamp).toMatch(/^\d{10}$/); // unix seconds
  });

  it('signs the body hash for write requests', async () => {
    const body = JSON.stringify({ symbol: 'XAUUSD', side: 'buy', volume: 1 });
    const { timestamp, signature } = await signRequest('POST', '/api/v1/orders', body, SECRET);

    const bodyHash = await sha256Hex(body);
    const expected = await hmacSha256Hex(`POST\n/api/v1/orders\n${timestamp}\n${bodyHash}`, SECRET);
    expect(signature).toBe(expected);
  });

  it('includes the query string in the signed path', async () => {
    const { timestamp, signature } = await signRequest(
      'GET',
      '/api/v1/orders?limit=10&offset=0',
      '',
      SECRET
    );
    const bodyHash = await sha256Hex('');
    const expected = await hmacSha256Hex(
      `GET\n/api/v1/orders?limit=10&offset=0\n${timestamp}\n${bodyHash}`,
      SECRET
    );
    expect(signature).toBe(expected);
  });

  it('paces timestamps so same-second requests do not collide as replays', async () => {
    const t1 = nextTimestamp(1_700_000_000);
    const t2 = nextTimestamp(1_700_000_000);
    const t3 = nextTimestamp(1_700_000_005);

    expect(t1).toBe('1700000000');
    expect(t2).toBe('1700000001'); // bumped to avoid (ts, body_hash) replay collision
    expect(t3).toBe('1700000005'); // real time moved forward; pacing follows max
  });

  it('buildAuthHeaders returns the three X-Lumine headers', async () => {
    const headers = await buildAuthHeaders('DELETE', '/api/v1/orders/o1', '', 'bootstrap', SECRET);

    expect(headers['X-Lumine-API-Key']).toBe('bootstrap');
    expect(headers['X-Lumine-Timestamp']).toMatch(/^\d{10}$/);
    expect(headers['X-Lumine-Signature']).toMatch(/^[0-9a-f]{64}$/);
  });

  it('does not sign when credentials are absent from the environment', async () => {
    vi.stubGlobal('import.meta', { env: { VITE_API_URL: 'http://localhost:8000' } });
    try {
      const { getHmacCredentials } = await import('../lib/api/auth');
      expect(getHmacCredentials()).toBeNull();
    } finally {
      vi.unstubAllGlobals();
    }
  });
});
