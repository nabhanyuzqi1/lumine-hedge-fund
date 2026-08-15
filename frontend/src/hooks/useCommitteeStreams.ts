import { useEffect, useState } from "react";

import { buildAuthHeaders, getHmacCredentials } from "@/lib/api/auth";
import { useSSE, type SSEEnvelope } from "@/hooks/useSSE";
import { useCommitteeStore, type CommitteeActivity } from "@/stores/committeeStore";
import { useStreamStore } from "@/stores/streamStore";

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

// Ref stabil — useSSE effect deps membandingkan `headers` (reference).
// PITFALL: `?? {}` membuat objek BARU tiap render → connect loop →
// "Maximum update depth exceeded" (React batal render, UI blank).
const EMPTY_HEADERS: Record<string, string> = {};

function toActivity(
  channel: string,
  data: CommitteeStreamEvent | null,
  eventTs: string
): CommitteeActivity | null {
  const spec = CHANNEL_MAP.get(channel);
  if (!spec || !data) return null;
  const decision =
    data.decision ?? data.action ?? data.recommendation ?? undefined;
  return {
    id: `${channel}-${data.run_id ?? data.workflow_run_id ?? Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    type: spec.type,
    agent: typeof data.analyst_name === "string" ? data.analyst_name : spec.agent,
    workflow_run_id:
      typeof data.workflow_run_id === "string" ? data.workflow_run_id : undefined,
    decision: typeof decision === "string" ? decision : undefined,
    confidence:
      typeof data.confidence === "number" ? data.confidence : undefined,
    timestamp: typeof data.timestamp === "string" ? data.timestamp : eventTs,
  };
}

export function useCommitteeStreams(enabled = true) {
  // HMAC headers PER-CHANNEL (fix B6): signature path harus match path
  // request — sebelumnya satu signature (analyst-outputs) dipakai untuk
  // semua channel → 401 INVALID_SIGNATURE di cio/risk/ic.
  const [headersByChannel, setHeadersByChannel] = useState<
    Record<string, Record<string, string>>
  >({});
  const appendActivity = useCommitteeStore((s) => s.appendActivity);
  const setStreamState = useStreamStore((s) => s.setStreamState);

  useEffect(() => {
    let active = true;
    const creds = getHmacCredentials();
    if (!creds) {
      setHeadersByChannel({});
      return;
    }
    const build = async () => {
      const result: Record<string, Record<string, string>> = {};
      for (const spec of STREAMS) {
        const path = `/api/v1/streams/${spec.channel}`;
        result[spec.channel] = await buildAuthHeaders(
          "GET",
          path,
          "",
          creds.apiKey,
          creds.apiSecret
        );
      }
      if (active) setHeadersByChannel(result);
    };
    void build();
    return () => {
      active = false;
    };
  }, []);

  const apiOrigin = (import.meta.env.VITE_API_BASE_URL ?? "").replace(/\/api\/v1\/?$/, "");

  for (const spec of STREAMS) {
    const channelHeaders = headersByChannel[spec.channel] ?? EMPTY_HEADERS;
    // eslint-disable-next-line react-hooks/rules-of-hooks
    const sse = useSSE<CommitteeStreamEvent>({
      url: `${apiOrigin}/api/v1/streams/${spec.channel}`,
      enabled: enabled && (Object.keys(channelHeaders).length > 0 || !getHmacCredentials()),
      headers: channelHeaders,
      onEvent: (envelope: SSEEnvelope<CommitteeStreamEvent>) => {
        const activity = toActivity(spec.channel, envelope.data, envelope.meta.timestamp);
        if (activity) appendActivity(activity);
      },
    });
    // B3: register status ke streamStore agar header health count akurat
    // (sebelumnya committee streams tidak terhitung → "1/6" padahal 5
    // stream jalan).
    // eslint-disable-next-line react-hooks/rules-of-hooks
    useEffect(() => {
      setStreamState(spec.channel, {
        status: sse.status,
        stale: sse.stale,
        error: sse.error ? sse.error.message : null,
      });
    }, [sse.status, sse.stale, sse.error, spec.channel, setStreamState]);
  }
}
