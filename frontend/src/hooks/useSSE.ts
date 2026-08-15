import { useCallback, useEffect, useRef, useState } from "react";

/**
 * Minimal SSE envelope returned by the Phase 9 stream endpoints.
 * The generic `T` is the payload inside `data.data`.
 */
export interface SSEEnvelope<T> {
  meta: {
    api_version: string;
    timestamp: string;
    request_id: string;
    status: "ok" | "error";
  };
  data: T | null;
  error: {
    code: string;
    message: string;
    details: Record<string, unknown>;
    trace_id: string;
  } | null;
}

export type SSELifecycleType =
  | "stream_open"
  | "stream_resumed"
  | "stream_closed"
  | "stream_dropped"
  | "gap_detected";

export interface SSELifecycleEvent {
  type: SSELifecycleType;
  data: Record<string, unknown>;
}

export type SSEStatus = "idle" | "connecting" | "open" | "stale" | "error" | "closed";

export interface UseSSEOptions<T> {
  /** Full SSE endpoint URL (including query params). */
  url: string;
  /** Disable the stream. */
  enabled?: boolean;
  /** Headers sent with the fetch request (e.g. auth). */
  headers?: Record<string, string>;
  /** Callback for every parsed event. */
  onEvent?: (event: SSEEnvelope<T>) => void;
  /** Callback for lifecycle events. */
  onLifecycle?: (event: SSELifecycleEvent) => void;
  /** Called when the stream reaches a terminal error. */
  onError?: (error: Error) => void;
}

export interface UseSSEReturn {
  status: SSEStatus;
  lastEventId: string | null;
  stale: boolean;
  error: Error | null;
}

const INITIAL_BACKOFF_MS = 1_000;
const MAX_BACKOFF_MS = 30_000;
const BACKOFF_RESET_MS = 30_000;
// Heartbeat server (streams.py) = 30s; stale = 2× heartbeat = 60s.
// PITFALL: stale timer (10s) < heartbeat (30s) → status flicker
// stale→open terus → "Realtime feed degraded" palsu di GapBanner.
const HEARTBEAT_INTERVAL_MS = 30_000;
const STALE_AFTER_MS = 60_000;

function getRetryAfterMs(response: Response, defaultMs: number): number {
  const header = response.headers.get("Retry-After");
  if (!header) return defaultMs;
  const parsed = Number(header);
  if (Number.isNaN(parsed) || parsed <= 0) return defaultMs;
  return parsed * 1_000;
}

/**
 * Subscribe to a Phase 9 SSE stream using a fetch/ReadableStream polyfill.
 *
 * This gives us control over custom headers (auth) and full reconnect
 * semantics required by `sse-api.md`:
 * - Backoff: 1s → 2s → 4s → 8s → max 30s
 * - Reset backoff after connection stays open 30+ seconds
 * - Send Last-Event-ID on reconnect
 * - Stop reconnect on 404 / 401 / 403
 * - Honor Retry-After on 429
 * - Reconnect on 5xx / network error
 */
export function useSSE<T>(options: UseSSEOptions<T>): UseSSEReturn {
  const { url, enabled = true, headers, onEvent, onLifecycle, onError } = options;

  const [status, setStatus] = useState<SSEStatus>("idle");
  const [lastEventId, setLastEventId] = useState<string | null>(null);
  const [stale, setStale] = useState(false);
  const [error, setError] = useState<Error | null>(null);

  const lastEventIdRef = useRef<string | null>(null);
  useEffect(() => {
    lastEventIdRef.current = lastEventId;
  }, [lastEventId]);

  const abortRef = useRef<AbortController | null>(null);
  const backoffRef = useRef(INITIAL_BACKOFF_MS);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const openedAtRef = useRef<number | null>(null);
  const staleTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const callbacksRef = useRef({ onEvent, onLifecycle, onError });

  callbacksRef.current = { onEvent, onLifecycle, onError };

  const clearReconnectTimer = useCallback(() => {
    if (reconnectTimerRef.current) {
      clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }
  }, []);

  const clearStaleTimer = useCallback(() => {
    if (staleTimerRef.current) {
      clearTimeout(staleTimerRef.current);
      staleTimerRef.current = null;
    }
  }, []);

  const resetStaleTimer = useCallback(
    (heartbeatIntervalMs: number) => {
      clearStaleTimer();
      staleTimerRef.current = setTimeout(() => {
        setStale(true);
      }, heartbeatIntervalMs * 2);
    },
    [clearStaleTimer]
  );

  const connect = useCallback(async () => {
    if (!enabled) return;

    abortRef.current?.abort();
    abortRef.current = new AbortController();
    setStatus("connecting");
    setStale(false);

    const requestHeaders: Record<string, string> = {
      Accept: "text/event-stream",
      ...headers,
    };

    if (lastEventIdRef.current) {
      requestHeaders["Last-Event-ID"] = lastEventIdRef.current;
    }

    try {
      const response = await fetch(url, {
        method: "GET",
        headers: requestHeaders,
        signal: abortRef.current.signal,
      });

      if (response.status === 401 || response.status === 403 || response.status === 404) {
        setStatus("error");
        setError(new Error(`SSE terminal status ${response.status}`));
        callbacksRef.current.onError?.(new Error(`SSE terminal status ${response.status}`));
        return;
      }

      if (response.status === 429) {
        const delay = getRetryAfterMs(response, backoffRef.current);
        setStatus("stale");
        reconnectTimerRef.current = setTimeout(() => {
          backoffRef.current = Math.min(backoffRef.current * 2, MAX_BACKOFF_MS);
          void connect();
        }, delay);
        return;
      }

      if (response.status >= 500) {
        throw new Error(`Server error ${response.status}`);
      }

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }

      if (!response.body) {
        throw new Error("Response body is null");
      }

      // Reset backoff once the connection is healthy.
      backoffRef.current = INITIAL_BACKOFF_MS;
      openedAtRef.current = Date.now();
      setStatus("open");
      setError(null);

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let currentEvent = "";
      let currentId = "";
      let currentData = "";

      const heartbeatIntervalMs = HEARTBEAT_INTERVAL_MS; // match server 30s
      // stale timer = 2× heartbeat = 60s (STALE_AFTER_MS).
      // PITFALL lama: 10s stale vs 30s heartbeat → flicker "degraded".
      resetStaleTimer(heartbeatIntervalMs);

      while (enabled) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() ?? "";

        for (const rawLine of lines) {
          const line = rawLine.replace(/\r$/, "");

          if (line.startsWith(":")) {
            // Heartbeat comment — keeps connection alive.
            resetStaleTimer(heartbeatIntervalMs);
            continue;
          }

          if (line === "") {
            // Dispatch event.
            if (currentEvent === "" && currentData === "") continue;

            const eventType = currentEvent || "message";

            if (eventType === "stream_open" || eventType === "stream_resumed") {
              try {
                const payload = JSON.parse(currentData) as Record<string, unknown>;
                callbacksRef.current.onLifecycle?.({ type: eventType, data: payload });
              } catch {
                callbacksRef.current.onLifecycle?.({ type: eventType, data: { raw: currentData } });
              }
            } else if (eventType === "stream_closed") {
              try {
                const payload = JSON.parse(currentData) as Record<string, unknown>;
                callbacksRef.current.onLifecycle?.({ type: "stream_closed", data: payload });
              } catch {
                callbacksRef.current.onLifecycle?.({
                  type: "stream_closed",
                  data: { raw: currentData },
                });
              }
            } else if (eventType === "stream_dropped") {
              try {
                const payload = JSON.parse(currentData) as Record<string, unknown>;
                callbacksRef.current.onLifecycle?.({ type: "stream_dropped", data: payload });
              } catch {
                callbacksRef.current.onLifecycle?.({
                  type: "stream_dropped",
                  data: { raw: currentData },
                });
              }
              setStatus("error");
              setError(new Error("Stream dropped by server"));
            } else {
              try {
                const envelope = JSON.parse(currentData) as SSEEnvelope<T>;
                callbacksRef.current.onEvent?.(envelope);

                if (envelope.meta.status === "error" && envelope.error) {
                  const err = new Error(`${envelope.error.code}: ${envelope.error.message}`);
                  setError(err);
                  callbacksRef.current.onError?.(err);

                  if (
                    envelope.error.code === "MISSING_AUTH" ||
                    envelope.error.code === "INVALID_SIGNATURE" ||
                    envelope.error.code === "INSUFFICIENT_SCOPE" ||
                    envelope.error.code === "NOT_FOUND"
                  ) {
                    setStatus("error");
                    return;
                  }
                }
              } catch {
                // Ignore malformed events.
              }
            }

            if (currentId) {
              setLastEventId(currentId);
            }

            currentEvent = "";
            currentData = "";
            currentId = "";
            continue;
          }

          if (line.startsWith("id:")) {
            currentId = line.slice(3).trim();
          } else if (line.startsWith("event:")) {
            currentEvent = line.slice(6).trim();
          } else if (line.startsWith("data:")) {
            currentData =
              currentData === "" ? line.slice(5).trim() : `${currentData}\n${line.slice(5).trim()}`;
          }
        }
      }

      // Clean disconnect.
      reader.releaseLock();
      clearStaleTimer();

      if (openedAtRef.current && Date.now() - openedAtRef.current >= BACKOFF_RESET_MS) {
        backoffRef.current = INITIAL_BACKOFF_MS;
      }

      reconnectTimerRef.current = setTimeout(() => {
        backoffRef.current = Math.min(backoffRef.current * 2, MAX_BACKOFF_MS);
        void connect();
      }, backoffRef.current);
    } catch (err) {
      if (err instanceof Error && err.name === "AbortError") {
        setStatus("closed");
        return;
      }

      setStatus("error");
      setError(err instanceof Error ? err : new Error(String(err)));

      if (openedAtRef.current && Date.now() - openedAtRef.current >= BACKOFF_RESET_MS) {
        backoffRef.current = INITIAL_BACKOFF_MS;
      }

      reconnectTimerRef.current = setTimeout(() => {
        backoffRef.current = Math.min(backoffRef.current * 2, MAX_BACKOFF_MS);
        void connect();
      }, backoffRef.current);
    }
  }, [enabled, url, headers, resetStaleTimer, clearStaleTimer]);

  useEffect(() => {
    void connect();

    return () => {
      clearReconnectTimer();
      clearStaleTimer();
      abortRef.current?.abort();
      setStatus("closed");
    };
  }, [connect, clearReconnectTimer, clearStaleTimer]);

  return { status, lastEventId, stale, error };
}
