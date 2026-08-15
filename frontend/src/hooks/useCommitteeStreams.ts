import { useEffect, useState } from "react";

import { buildAuthHeaders, getHmacCredentials } from "@/lib/api/auth";
import { useSSE, type SSEEnvelope } from "@/hooks/useSSE";
import { useCommitteeStore, type CommitteeActivity } from "@/stores/committeeStore";

/**
 * Committee SSE streams — analyst-outputs, ic-decisions, cio-proposals,
 * risk-assessments. Connect ke 4 channel dan append ke committeeStore
 * sehingga CommitteeFeed terisi LIVE.
 *
 * Sebelumnya committee feed kosong selamanya: frontend tidak pernah
 * connect ke stream ini (dan backend stream tidak relay event — fixed).
 */

interface CommitteeStreamEvent {
  symbol?: string;
  decision?: string;
  action?: string;
  recommendation?: string;
  confidence?: number;
  analyst_name?: string;
  agent?: string;
  run_id?: string;
  workflow_run_id?: string;
  timestamp?: string;
  [key: string]: unknown;
}

const STREAMS: {
  channel: string;
  type: CommitteeActivity["type"];
  agent: string;
}[] = [
  { channel: "analyst-outputs", type: "analyst_output", agent: "Analyst" },
  { channel: "ic-decisions", type: "ic_decision", agent: "IC" },
  { channel: "cio-proposals", type: "cio_proposal", agent: "CIO" },
  { channel: "risk-assessments", type: "risk_assessment", agent: "Risk" },
];

const CHANNEL_MAP = new Map(STREAMS.map((s) => [s.channel, s]));

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
  const [headers, setHeaders] = useState<Record<string, string>>({});
  const appendActivity = useCommitteeStore((s) => s.appendActivity);

  // HMAC headers untuk stream endpoint (sama pattern market-data).
  useEffect(() => {
    let active = true;
    const creds = getHmacCredentials();
    if (!creds) {
      setHeaders({});
      return;
    }
    // Path base untuk signature — query beda per channel, tapi signature
    // dibangun per-request di useSSE via buildAuthHeaders di caller.
    // Di sini kita pakai satu path generik; tiap stream pakai channel-nya.
    const path = `/api/v1/streams/analyst-outputs`;
    buildAuthHeaders("GET", path, "", creds.apiKey, creds.apiSecret).then((h) => {
      if (active) setHeaders(h);
    });
    return () => {
      active = false;
    };
  }, []);

  const apiOrigin = (import.meta.env.VITE_API_BASE_URL ?? "").replace(/\/api\/v1\/?$/, "");

  for (const spec of STREAMS) {
    // eslint-disable-next-line react-hooks/rules-of-hooks
    useSSE<CommitteeStreamEvent>({
      url: `${apiOrigin}/api/v1/streams/${spec.channel}`,
      enabled: enabled && (Object.keys(headers).length > 0 || !getHmacCredentials()),
      headers,
      onEvent: (envelope: SSEEnvelope<CommitteeStreamEvent>) => {
        const activity = toActivity(spec.channel, envelope.data, envelope.meta.timestamp);
        if (activity) appendActivity(activity);
      },
    });
  }
}
