import { get } from "@/api/client";
import { useQuery } from "@tanstack/react-query";
import * as React from "react";

/**
 * B10: LLM routing diagram — superadmin. Visualisasi nodes yang saling
 * terhubung (9router → Gateway → agent stages → SSE channels). Node yang
 * baru saja aktif mendapat border menyala (pulse) + verbose log call.
 *
 * v2 (18 Aug 2026): WebSocket realtime — frame `llm_usage` dari decision
 * cycle dipush langsung (tanpa polling). + panel verbose prompt per call.
 */

interface LLMUsageEntry {
  id: string;
  ts: string;
  role: string;
  tier: string;
  model: string | null;
  tokens_in: number;
  tokens_out: number;
  cost_usd: string;
  fallback_hops: number;
  degraded: boolean;
  lane: string | null;
}

interface LiveUsageFrame {
  role: string;
  model: string;
  fallback_hops: number;
  degraded: boolean;
  tokens_in: number;
  tokens_out: number;
  timestamp: string;
}

interface LiveFailureFrame {
  error: string;
  kind: string;
  llm_down: boolean;
  timestamp: string;
}

const STAGE_ORDER = [
  "technical_analyst",
  "macro_analyst",
  "news_analyst",
  "smc_analyst",
  "debate",
  "ic_forum",
  "cio_proposer",
  "risk_officer",
];

const STAGE_LABEL: Record<string, string> = {
  technical_analyst: "Technical",
  macro_analyst: "Macro",
  news_analyst: "News",
  smc_analyst: "SMC",
  debate: "Debate",
  ic_forum: "Investment Committee",
  cio_proposer: "CIO",
  risk_officer: "Risk Officer",
};

/** WS live frames — di-push backend saat tiap stage selesai. */
function useLLMUsageLive(
  onFrame: (f: LiveUsageFrame) => void,
  onFailure: (f: LiveFailureFrame) => void
) {
  const wsRef = React.useRef<WebSocket | null>(null);
  const cbRef = React.useRef(onFrame);
  cbRef.current = onFrame;
  const failRef = React.useRef(onFailure);
  failRef.current = onFailure;

  React.useEffect(() => {
    const proto = window.location.protocol === "https:" ? "wss" : "ws";
    let closed = false;
    const connect = () => {
      if (closed) return;
      try {
        const ws = new WebSocket(`${proto}://${window.location.host}/api/v1/ws/market`);
        wsRef.current = ws;
        ws.onopen = () => {
          // WS menerima SEMUA channel (termasuk llm-usage).
        };
        ws.onmessage = (ev) => {
          try {
            const frame = JSON.parse(String(ev.data));
            if (frame.event === "llm_usage" && frame.data) {
              cbRef.current(frame.data as LiveUsageFrame);
            } else if (frame.event === "analyst_failed" && frame.data) {
              failRef.current(frame.data as LiveFailureFrame);
            }
          } catch {
            /* non-JSON */
          }
        };
        ws.onclose = () => {
          if (!closed) setTimeout(connect, 3000);
        };
      } catch {
        setTimeout(connect, 3000);
      }
    };
    connect();
    return () => {
      closed = true;
      wsRef.current?.close();
    };
  }, []);
}

function useLLMUsage(limit = 30) {
  return useQuery<LLMUsageEntry[]>({
    queryKey: ["admin-llm-usage", limit],
    queryFn: async () => {
      const items = await get<LLMUsageEntry[]>(`/admin/llm-usage`, { limit: String(limit) });
      return Array.isArray(items) ? items : [];
    },
    refetchInterval: 5_000,
    staleTime: 3_000,
  });
}

function Node({
  label,
  sub,
  active,
  color = "border-accent",
}: {
  label: string;
  sub?: string;
  active: boolean;
  color?: string;
}) {
  return (
    <div
      className={`flex min-w-[120px] flex-col items-center rounded-panel border px-3 py-2 text-center transition-all duration-300 ${
        active
          ? `${color} bg-accent/10 shadow-[0_0_12px_rgba(255,255,255,0.15)]`
          : "border-line bg-bg"
      }`}
      style={active ? { boxShadow: "0 0 16px rgba(99,179,237,0.35)" } : undefined}
    >
      <span className={`font-mono text-[10px] uppercase tracking-wider ${active ? "text-accent" : "text-ink-dim"}`}>
        {label}
      </span>
      {sub && <span className="mt-0.5 font-mono text-[9px] text-ink-faint">{sub}</span>}
      {active && (
        <span className="mt-1 inline-flex h-1.5 w-1.5 animate-pulse rounded-full bg-accent" aria-hidden="true" />
      )}
    </div>
  );
}

function Edge({ active }: { active: boolean }) {
  return (
    <div
      className={`flex h-8 items-center justify-center`}
      aria-hidden="true"
    >
      <div className={`h-px w-12 ${active ? "bg-accent" : "bg-line"}`} />
    </div>
  );
}

export function LLMRoutingTab() {
  const { data: usage = [], isLoading } = useLLMUsage();
  // Live frames via WS — merge ke usage list (role unik per frame).
  const [liveRows, setLiveRows] = React.useState<LiveUsageFrame[]>([]);
  const [failures, setFailures] = React.useState<LiveFailureFrame[]>([]);
  useLLMUsageLive(
    (frame) => {
      setLiveRows((prev) => [frame, ...prev].slice(0, 30));
    },
    (failure) => {
      setFailures((prev) => [failure, ...prev].slice(0, 20));
    }
  );

  const lastTs = usage.length > 0 ? Date.parse(usage[0].ts) : 0;
  const isActive = (role: string) =>
    usage.some((u) => u.role === role && Date.now() - Date.parse(u.ts) < 60_000) ||
    liveRows.some((f) => f.role === role && Date.now() - Date.parse(f.timestamp) < 60_000);

  const rolesSeen = new Set(usage.map((u) => u.role));

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-sm font-medium text-ink">LLM Routing — Live</h2>
          <p className="text-xs text-ink-faint">
            Node menyala (border glow) = stage aktif &lt;60s. Data real dari tabel
            llm_usage + push WebSocket realtime (frame llm_usage per stage).
          </p>
        </div>
        <span className="font-mono text-[10px] text-ink-faint tabular-nums">
          {liveRows.length > 0 && (
            <span className="mr-2 inline-flex items-center gap-1 text-cyan-400">
              <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-cyan-400" />
              WS live
            </span>
          )}
          {usage.length} calls · last {lastTs ? new Date(lastTs).toLocaleTimeString() : "—"}
        </span>
      </div>

      {isLoading ? (
        <p className="text-xs text-ink-faint">Loading…</p>
      ) : (
        <>
          {/* Diagram: 9router → Gateway → stages → SSE */}
          <div className="flex flex-col items-center rounded-panel border border-line bg-bg p-4">
            <Node label="9router" sub="oc/deepseek-v4-flash-free" active={usage.length > 0} />
            <Edge active={usage.length > 0} />
            <Node label="LLM Gateway" sub={`${usage.length} calls`} active={usage.length > 0} />
            <Edge active={usage.length > 0} />

            <div className="flex flex-wrap items-start justify-center gap-3">
              {STAGE_ORDER.map((role) => {
                const seen = rolesSeen.has(role);
                return (
                  <Node
                    key={role}
                    label={STAGE_LABEL[role] ?? role}
                    sub={seen ? `✓ ${usage.filter((u) => u.role === role).length}` : "idle"}
                    active={isActive(role)}
                  />
                );
              })}
            </div>

            <Edge active={usage.length > 0} />
            <Node label="SSE Channels" sub="analyst/ic/cio/risk" active={usage.length > 0} />
          </div>

          {/* Verbose: recent calls */}
          <div className="rounded-panel border border-line bg-bg">
            <div className="border-b border-line px-3 py-2">
              <h3 className="font-mono text-[10px] uppercase tracking-widest text-ink-dim">
                Verbose — Recent LLM Calls
              </h3>
            </div>
            <div className="max-h-64 overflow-y-auto">
              {usage.length === 0 && liveRows.length === 0 ? (
                <p className="px-3 py-4 text-xs text-ink-faint">
                  Belum ada LLM call tercatat. Trigger decision cycle untuk melihat routing live.
                </p>
              ) : (
                <table className="w-full text-left font-mono text-[10px]">
                  <thead className="sticky top-0 bg-bg-raised text-ink-faint">
                    <tr>
                      <th className="px-3 py-1.5">time</th>
                      <th className="px-3 py-1.5">stage</th>
                      <th className="px-3 py-1.5">model</th>
                      <th className="px-3 py-1.5 text-right">tokens</th>
                      <th className="px-3 py-1.5 text-right">cost</th>
                      <th className="px-3 py-1.5">state</th>
                    </tr>
                  </thead>
                  <tbody>
                    {liveRows.map((f, i) => (
                      <tr key={`live-${i}`} className="border-t border-cyan-400/20 bg-cyan-400/5">
                        <td className="px-3 py-1 text-ink-dim">
                          {new Date(f.timestamp).toLocaleTimeString()}
                        </td>
                        <td className="px-3 py-1 text-ink">
                          {STAGE_LABEL[f.role] ?? f.role}
                        </td>
                        <td className="px-3 py-1 text-ink-dim">{f.model}</td>
                        <td className="px-3 py-1 text-right text-ink-dim">
                          {f.tokens_in + f.tokens_out}
                        </td>
                        <td className="px-3 py-1 text-right text-ink-dim">—</td>
                        <td className="px-3 py-1">
                          {f.degraded ? (
                            <span className="text-amber-400">degraded</span>
                          ) : (
                            <span className="text-up">ok</span>
                          )}
                          {f.fallback_hops > 0 && (
                            <span className="ml-1 text-ink-faint">hops={f.fallback_hops}</span>
                          )}
                        </td>
                      </tr>
                    ))}
                    {usage.slice(0, 30).map((u) => (
                      <tr key={u.id} className="border-t border-line/50">
                        <td className="px-3 py-1 text-ink-dim">
                          {new Date(u.ts).toLocaleTimeString()}
                        </td>
                        <td className="px-3 py-1 text-ink">
                          {STAGE_LABEL[u.role] ?? u.role}
                        </td>
                        <td className="px-3 py-1 text-ink-dim">{u.model ?? "—"}</td>
                        <td className="px-3 py-1 text-right text-ink-dim">
                          {u.tokens_in + u.tokens_out}
                        </td>
                        <td className="px-3 py-1 text-right text-ink-dim">
                          ${Number(u.cost_usd).toFixed(6)}
                        </td>
                        <td className="px-3 py-1">
                          {u.degraded ? (
                            <span className="text-amber-400">degraded</span>
                          ) : (
                            <span className="text-up">ok</span>
                          )}
                          {u.fallback_hops > 0 && (
                            <span className="ml-1 text-amber-400">+{u.fallback_hops}hop</span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          </div>

          {/* Monitoring: analyst failures / LLM down (18 Aug 2026) */}
          {failures.length > 0 && (
            <div className="rounded-panel border border-danger/40 bg-danger/5">
              <div className="border-b border-danger/30 px-3 py-2">
                <h3 className="font-mono text-[10px] uppercase tracking-widest text-danger">
                  ⚠ Analyst Failures / LLM Down — {failures.filter((f) => f.llm_down).length} down
                </h3>
              </div>
              <div className="max-h-40 space-y-1 overflow-y-auto p-2">
                {failures.map((f, i) => (
                  <div
                    key={`fail-${i}`}
                    className="flex items-start justify-between gap-2 rounded bg-bg px-2 py-1 font-mono text-[10px]"
                  >
                    <div className="min-w-0">
                      <span
                        className={
                          f.llm_down
                            ? "mr-1 font-semibold text-danger"
                            : "mr-1 font-semibold text-warn"
                        }
                      >
                        {f.llm_down ? "LLM DOWN" : f.kind}
                      </span>
                      <span className="text-ink-dim">{f.error.slice(0, 120)}</span>
                    </div>
                    <span className="shrink-0 text-ink-faint">
                      {new Date(f.timestamp).toLocaleTimeString()}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
