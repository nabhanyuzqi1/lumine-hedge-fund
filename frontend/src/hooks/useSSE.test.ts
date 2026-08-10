import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { useSSE } from './useSSE';

class MockReadableStream {
  private chunks: Uint8Array[] = [];
  private locked = false;

  push(text: string) {
    this.chunks.push(new TextEncoder().encode(text));
  }

  close() {
    this.chunks.push(new Uint8Array(0));
  }

  getReader() {
    if (this.locked) throw new Error('Stream already locked');
    this.locked = true;

    return {
      read: async () => {
        const chunk = this.chunks.shift();
        if (!chunk) return { done: true, value: undefined };
        if (chunk.length === 0) return { done: true, value: undefined };
        return { done: false, value: chunk };
      },
      releaseLock: () => {
        this.locked = false;
      },
    };
  }
}

function createMockResponse(
  stream: MockReadableStream,
  overrides: Partial<Response> = {},
): Response {
  return {
    ok: true,
    status: 200,
    headers: new Headers(),
    body: stream as unknown as ReadableStream<Uint8Array>,
    ...overrides,
  } as Response;
}

describe('useSSE', () => {
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it('calls onEvent for parsed events', async () => {
    const stream = new MockReadableStream();
    const onEvent = vi.fn();

    vi.stubGlobal('fetch', vi.fn().mockResolvedValueOnce(createMockResponse(stream)));

    stream.push(
      'id: 1\nevent: market_data\ndata: {"meta":{"api_version":"v1","timestamp":"2026-08-01T00:00:00Z","request_id":"r1","status":"ok"},"data":{"price":2400},"error":null}\n\n',
    );

    renderHook(() => useSSE({ url: 'http://localhost/stream', onEvent }));

    await waitFor(() => expect(onEvent).toHaveBeenCalledTimes(1));
    expect(onEvent.mock.calls[0]![0].data).toEqual({ price: 2400 });
  });

  it('ignores heartbeat comments', async () => {
    const stream = new MockReadableStream();
    const onEvent = vi.fn();

    vi.stubGlobal('fetch', vi.fn().mockResolvedValueOnce(createMockResponse(stream)));

    stream.push(': heartbeat\n\n');
    stream.push(
      'id: 2\nevent: market_data\ndata: {"meta":{"api_version":"v1","timestamp":"2026-08-01T00:00:01Z","request_id":"r2","status":"ok"},"data":{"price":2401},"error":null}\n\n',
    );

    renderHook(() => useSSE({ url: 'http://localhost/stream', onEvent }));

    await waitFor(() => expect(onEvent).toHaveBeenCalledTimes(1));
    expect(onEvent.mock.calls[0]![0].data).toEqual({ price: 2401 });
  });

  it('sends Last-Event-ID on reconnect', async () => {
    const stream1 = new MockReadableStream();
    const stream2 = new MockReadableStream();
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(createMockResponse(stream1))
      .mockResolvedValueOnce(createMockResponse(stream2));
    vi.stubGlobal('fetch', fetchMock);

    stream1.push(
      'id: 10\nevent: market_data\ndata: {"meta":{"api_version":"v1","timestamp":"2026-08-01T00:00:00Z","request_id":"r1","status":"ok"},"data":{"price":2400},"error":null}\n\n',
    );
    stream1.close();

    stream2.push(
      'id: 11\nevent: market_data\ndata: {"meta":{"api_version":"v1","timestamp":"2026-08-01T00:00:01Z","request_id":"r2","status":"ok"},"data":{"price":2401},"error":null}\n\n',
    );

    const { unmount } = renderHook(() => useSSE({ url: 'http://localhost/stream' }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));

    vi.advanceTimersByTime(1_100);

    await waitFor(() => expect(fetchMock.mock.calls.length).toBeGreaterThanOrEqual(2));

    const [, init] = fetchMock.mock.calls[1] as [string, RequestInit];
    expect(init.headers).toMatchObject({ 'Last-Event-ID': '10' });

    unmount();
  });

  it('does not reconnect on 404', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: false,
      status: 404,
      headers: new Headers(),
      body: null,
    });
    vi.stubGlobal('fetch', fetchMock);

    const { result } = renderHook(() => useSSE({ url: 'http://localhost/stream' }));

    await waitFor(() => expect(result.current.status).toBe('error'));

    vi.advanceTimersByTime(5_000);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it('honors Retry-After on 429', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({
        ok: false,
        status: 429,
        headers: new Headers({ 'Retry-After': '2' }),
        body: null,
      })
      .mockResolvedValueOnce({
        ok: false,
        status: 404,
        headers: new Headers(),
        body: null,
      });
    vi.stubGlobal('fetch', fetchMock);

    renderHook(() => useSSE({ url: 'http://localhost/stream' }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));

    vi.advanceTimersByTime(2_100);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
  });

  it('backs off on network error', async () => {
    const fetchMock = vi.fn().mockRejectedValue(new Error('Network failure'));
    vi.stubGlobal('fetch', fetchMock);

    renderHook(() => useSSE({ url: 'http://localhost/stream' }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));

    vi.advanceTimersByTime(1_100);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
  });
});
