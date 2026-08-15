import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, del, get, post } from "./client";

const mockFetch = vi.fn();

describe("api client", () => {
  beforeEach(() => {
    globalThis.fetch = mockFetch;
    vi.stubEnv("VITE_API_BASE_URL", "http://localhost:8000/api/v1");
  });

  afterEach(() => {
    vi.unstubAllEnvs();
    vi.resetAllMocks();
  });

  it("returns data field from ok envelope", async () => {
    mockFetch.mockResolvedValueOnce({
      status: 200,
      text: async () =>
        JSON.stringify({
          meta: {
            api_version: "v1",
            timestamp: "2026-08-01T00:00:00Z",
            request_id: "r1",
            status: "ok",
          },
          data: { bid: 2400.5 },
          error: null,
        }),
    });

    const data = await get<{ bid: number }>("market/quotes/XAUUSD");

    expect(data.bid).toBe(2400.5);
    expect(mockFetch).toHaveBeenCalledWith(
      "http://localhost:8000/api/v1/market/quotes/XAUUSD",
      expect.objectContaining({ method: "GET" })
    );
  });

  it("serializes array query params as comma-separated", async () => {
    mockFetch.mockResolvedValueOnce({
      status: 200,
      text: async () =>
        JSON.stringify({
          meta: {
            api_version: "v1",
            timestamp: "2026-08-01T00:00:00Z",
            request_id: "r2",
            status: "ok",
          },
          data: [],
          error: null,
        }),
    });

    await get("orders", { status: ["PENDING", "ACTIVE"] });

    const [url] = mockFetch.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("status=PENDING%2CACTIVE");
  });

  it("throws ApiError on error envelope", async () => {
    mockFetch.mockResolvedValueOnce({
      status: 429,
      text: async () =>
        JSON.stringify({
          meta: {
            api_version: "v1",
            timestamp: "2026-08-01T00:00:00Z",
            request_id: "r3",
            status: "error",
          },
          data: null,
          error: {
            code: "RATE_LIMITED",
            message: "Too many requests",
            details: { retry_after: 10 },
            trace_id: "t1",
          },
        }),
    });

    const promise = get("orders");
    await expect(promise).rejects.toThrow(ApiError);
    await expect(promise).rejects.toMatchObject({
      status: 429,
      code: "RATE_LIMITED",
      traceId: "t1",
    });
  });

  it("posts JSON body", async () => {
    mockFetch.mockResolvedValueOnce({
      status: 200,
      text: async () =>
        JSON.stringify({
          meta: {
            api_version: "v1",
            timestamp: "2026-08-01T00:00:00Z",
            request_id: "r4",
            status: "ok",
          },
          data: { id: "o1" },
          error: null,
        }),
    });

    const data = await post("orders", { symbol: "XAUUSD", side: "BUY" });
    expect(data).toEqual({ id: "o1" });

    const [, init] = mockFetch.mock.calls[0] as [string, RequestInit];
    expect(init.method).toBe("POST");
    expect(init.body).toBe(JSON.stringify({ symbol: "XAUUSD", side: "BUY" }));
  });

  it("deletes resource", async () => {
    mockFetch.mockResolvedValueOnce({
      status: 200,
      text: async () =>
        JSON.stringify({
          meta: {
            api_version: "v1",
            timestamp: "2026-08-01T00:00:00Z",
            request_id: "r5",
            status: "ok",
          },
          data: null,
          error: null,
        }),
    });

    await del("orders/o1");
    const [url, init] = mockFetch.mock.calls[0] as [string, RequestInit];
    expect(init.method).toBe("DELETE");
    expect(url).toBe("http://localhost:8000/api/v1/orders/o1");
  });
});
