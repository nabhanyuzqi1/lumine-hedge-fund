import { get } from "@/api/client";
import { useQuery } from "@tanstack/react-query";

/**
 * B10: LLM routing diagram — superadmin. Visualisasi nodes yang saling
 * terhubung (9router → Gateway → agent stages → SSE channels). Node yang
 * baru saja aktif mendapat border menyala (pulse) + verbose log call.
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

  const lastTs = usage.length > 0 ? Date.parse(usage[0].ts) : 0;
  const isActive = (role: string) =>
    usage.some((u) => u.role === role && Date.now() - Date.parse(u.ts) < 60_000);

  const rolesSeen = new Set(usage.map((u) => u.role));

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-sm font-medium text-ink">LLM Routing — Live</h2>
          <p className="text-xs text-ink-faint">
            Node menyala (border glow) = stage aktif &lt;60s terakhir. Data real dari
            tabel llm_usage (polling 5s).
          </p>
        </div>
        <span className="font-mono text-[10px] text-ink-faint tabular-nums">
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
              {usage.length === 0 ? (
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
        </>
      )}
    </div>
  );
}
