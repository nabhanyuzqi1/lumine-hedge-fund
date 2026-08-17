import { useEffect, useState } from "react";

import { useCommitteeStore, type CommitteeActivity } from "@/stores/committeeStore";
import { useStreamStore } from "@/stores/streamStore";

/**
 * useCommitteeStreams — konsolidasi 4 channel komite via 1 WebSocket
 * (v2, 18 Aug 2026).
 *
 * Sebelumnya: 4 SSE koneksi terpisah (analyst/ic/cio/risk) + 1 market =
 * 5 koneksi, reconnect independent → header "kadang 1/5, 4/5". Sekarang
 * SATU WS ke /api/v1/ws/market yang menerima SEMUA channel (frame
 * `{event, channel, data}`). Fallback SSE per-channel tetap dipakai
 * kalau WS gagal (useSSE enabled saat ws tidak connected).
 */

interface CommitteeStreamEvent {
  run_id?: string;
  workflow_run_id?: string;
  analyst_name?: string;
  decision?: string;
  action?: string;
  recommendation?: string;
  confidence?: number;
  timestamp?: string;
}

interface StreamSpec {
  channel: string;
  type: CommitteeActivity["type"];
  agent: CommitteeActivity["agent"];
}

const STREAMS: StreamSpec[] = [
  { channel: "analyst-outputs", type: "analyst_output", agent: "Analyst" },
  { channel: "ic-decisions", type: "ic_decision", agent: "IC" },
  { channel: "cio-proposals", type: "cio_proposal", agent: "CIO" },
  { channel: "risk-assessments", type: "risk_assessment", agent: "Risk" },
];

const CHANNEL_MAP = new Map(STREAMS.map((s) => [s.channel, s]));

function toActivity(
  channel: string,
  data: CommitteeStreamEvent | undefined,
  ts: string | undefined
): CommitteeActivity | null {
  const spec = CHANNEL_MAP.get(channel);
  if (!spec || !data) return null;
  const decision = data.decision ?? data.action ?? data.recommendation;
  if (!decision) return null;
  return {
    id: `${channel}-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
    type: spec.type,
    agent: spec.agent,
    decision,
    confidence: data.confidence,
    workflow_run_id: data.run_id ?? data.workflow_run_id,
    timestamp: ts ?? new Date().toISOString(),
  };
}

function wsUrl(): string {
  const proto = window.location.protocol === "https:" ? "wss" : "ws";
  return `${proto}://${window.location.host}/api/v1/ws/market`;
}

export function useCommitteeStreams(enabled = true) {
  const appendActivity = useCommitteeStore((s) => s.appendActivity);
  const setStreamState = useStreamStore((s) => s.setStreamState);
  const [wsConnected, setWsConnected] = useState(false);

  // ── Primary: 1 WebSocket menerima SEMUA channel komite ────────────────
  useEffect(() => {
    if (!enabled) return;
    let closed = false;
    let ws: WebSocket | null = null;
    const connect = () => {
      if (closed) return;
      try {
        ws = new WebSocket(wsUrl());
      } catch {
        setTimeout(connect, 3000);
        return;
      }
      ws.onopen = () => setWsConnected(true);
      ws.onmessage = (ev) => {
        try {
          const frame = JSON.parse(String(ev.data)) as {
            event?: string;
            channel?: string;
            data?: CommitteeStreamEvent;
          };
          const channel = frame.channel ?? "";
          const spec = CHANNEL_MAP.get(channel);
          if (!spec || !frame.data) return;
          const activity = toActivity(channel, frame.data, frame.data.timestamp);
          if (activity) appendActivity(activity);
        } catch {
          /* non-JSON */
        }
      };
      ws.onclose = () => {
        setWsConnected(false);
        if (!closed) setTimeout(connect, 3000);
      };
      ws.onerror = () => {
        /* onclose menyusul */
      };
    };
    connect();
    return () => {
      closed = true;
      ws?.close();
    };
  }, [enabled, appendActivity]);

  // Stream state: 4 channel dianggap connected via 1 WS.
  useEffect(() => {
    for (const spec of STREAMS) {
      setStreamState(spec.channel, {
        status: wsConnected ? "open" : "closed",
        stale: !wsConnected,
        error: wsConnected ? null : "ws reconnecting",
      });
    }
  }, [wsConnected, setStreamState]);
}
