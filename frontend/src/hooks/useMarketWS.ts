// Copyright (c) 2026 Lumine. All rights reserved.
/**
 * useMarketWS — WebSocket market stream (17 Aug 2026).
 *
 * Menggantikan SSE untuk market-data tick: WebSocket lebih ringan dan
 * realtime (frame per tick, tanpa overhead HTTP per event). Auto-reconnect
 * dengan exponential backoff; kalau WS gagal (Caddy/CF tidak support WS),
 * fallback otomatis ke SSE `/api/v1/streams/market-data` (tidak berubah).
 *
 * Frame: JSON `{event, channel, data}` — `event: "tick_update"` membawa
 * `data.tick {symbol, bid, ask, last, timestamp}`; `market_closed` untuk
 * status libur; `heartbeat` untuk keepalive.
 */

import * as React from "react";

export interface WSTick {
  symbol: string;
  bid: number;
  ask: number;
  last: number;
  timestamp: string;
}

interface UseMarketWSOptions {
  symbol: string;
  enabled?: boolean;
  onTick: (tick: WSTick) => void;
  onClosed?: (reason: string) => void;
  onStatusChange?: (status: "open" | "closed" | "connecting" | "error") => void;
}

const INITIAL_BACKOFF_MS = 1_000;
const MAX_BACKOFF_MS = 30_000;
const HEARTBEAT_TIMEOUT_MS = 90_000;

function wsUrl(symbol: string): string {
  const proto = window.location.protocol === "https:" ? "wss" : "ws";
  return `${proto}://${window.location.host}/api/v1/ws/market?symbol=${encodeURIComponent(symbol)}`;
}

export function useMarketWS(options: UseMarketWSOptions) {
  const { symbol, enabled = true, onTick, onClosed, onStatusChange } = options;
  const [status, setStatus] = React.useState<"idle" | "open" | "closed" | "connecting" | "error">("idle");
  const wsRef = React.useRef<WebSocket | null>(null);
  const backoffRef = React.useRef(INITIAL_BACKOFF_MS);
  const reconnectTimerRef = React.useRef<ReturnType<typeof setTimeout> | null>(null);
  const heartbeatTimerRef = React.useRef<ReturnType<typeof setTimeout> | null>(null);
  const closedRef = React.useRef(false);
  const callbacksRef = React.useRef({ onTick, onClosed, onStatusChange });
  callbacksRef.current = { onTick, onClosed, onStatusChange };

  const clearTimers = React.useCallback(() => {
    if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current);
    if (heartbeatTimerRef.current) clearTimeout(heartbeatTimerRef.current);
    reconnectTimerRef.current = null;
    heartbeatTimerRef.current = null;
  }, []);

  const updateStatus = React.useCallback((s: "open" | "closed" | "connecting" | "error") => {
    setStatus(s);
    callbacksRef.current.onStatusChange?.(s);
  }, []);

  React.useEffect(() => {
    if (!enabled) return;
    let cancelled = false;
    closedRef.current = false;
    backoffRef.current = INITIAL_BACKOFF_MS;

    const connect = () => {
      if (cancelled || closedRef.current) return;
      updateStatus("connecting");
      clearTimers();

      let ws: WebSocket;
      try {
        ws = new WebSocket(wsUrl(symbol));
      } catch {
        // WS tidak tersedia → biarkan caller fallback ke SSE (onStatusChange
        // "error" memberi sinyal; caller memutuskan).
        updateStatus("error");
        return;
      }
      wsRef.current = ws;

      ws.onopen = () => {
        if (cancelled) return;
        backoffRef.current = INITIAL_BACKOFF_MS;
        updateStatus("open");
        // Heartbeat watchdog: WS hidup tapi tidak ada frame → reconnect.
        heartbeatTimerRef.current = setTimeout(() => {
          if (!cancelled) {
            ws.close();
          }
        }, HEARTBEAT_TIMEOUT_MS);
      };

      ws.onmessage = (ev) => {
        // Frame apa pun = connection hidup → reset heartbeat.
        if (heartbeatTimerRef.current) clearTimeout(heartbeatTimerRef.current);
        heartbeatTimerRef.current = setTimeout(() => {
          if (!cancelled) ws.close();
        }, HEARTBEAT_TIMEOUT_MS);
        try {
          const frame = JSON.parse(String(ev.data)) as {
            event?: string;
            data?: { tick?: WSTick; reason?: string; symbol?: string; [k: string]: unknown };
          };
          const payload = frame.data ?? {};
          if (frame.event === "tick_update" && payload.tick) {
            // Hanya tick untuk symbol aktif (server sudah filter, double-check).
            if (!payload.symbol || String(payload.symbol).toUpperCase() === symbol.toUpperCase()) {
              callbacksRef.current.onTick(payload.tick as WSTick);
            }
          } else if (frame.event === "market_closed" && payload.reason) {
            callbacksRef.current.onClosed?.(String(payload.reason));
          }
        } catch {
          // frame non-JSON (heartbeat/comment) — abaikan.
        }
      };

      ws.onclose = () => {
        if (cancelled) return;
        updateStatus("closed");
        clearTimers();
        // Reconnect dengan backoff (jangan infinite-spam saat network down).
        reconnectTimerRef.current = setTimeout(connect, backoffRef.current);
        backoffRef.current = Math.min(backoffRef.current * 2, MAX_BACKOFF_MS);
      };

      ws.onerror = () => {
        // onclose selalu menyusul — reconnect di sana.
      };
    };

    connect();

    return () => {
      cancelled = true;
      closedRef.current = true;
      clearTimers();
      wsRef.current?.close();
      wsRef.current = null;
    };
  }, [symbol, enabled, updateStatus, clearTimers]);

  return { status, connected: status === "open" };
}

/** Reuse dalam satu module — export type untuk caller. */
export type MarketWSStatus = ReturnType<typeof useMarketWS>["status"];
