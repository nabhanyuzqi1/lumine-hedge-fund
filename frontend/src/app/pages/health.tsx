import * as React from "react";
import { useShallow } from "zustand/react/shallow";
import { ApiError, get } from "@/api/client";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { NumericText } from "@/components/ui/numeric-text";
import { useStreamStore } from "@/stores/streamStore";
import { useQuery } from "@tanstack/react-query";

interface QuoteSnapshot {
  symbol: string;
  bid: number;
  ask: number;
  spread: number;
  timestamp: string;
}

async function fetchQuote(symbol: string): Promise<QuoteSnapshot> {
  const res = await get<Record<string, QuoteSnapshot>>(`market/quotes?symbols=${symbol}`);
  return res[symbol];
}

interface ProbeResult {
  path: string;
  label: string;
  status: "ok" | "error";
  latencyMs: number | null;
  code?: string;
}

const PROBES = [
  // Path relatif ke /api/v1 (client.get prepend base). Catatan:
  // - /health ada di ROOT (bukan /api/v1/health) → probe lewat absolute URL
  // - /journal/entries bukan path valid; endpoint real = /journal
  { path: "/health", label: "API health", absolute: true },
  { path: "/market/quotes?symbols=XAUUSD", label: "Market quotes" },
  { path: "/portfolio/positions", label: "Portfolio" },
  { path: "/workflows", label: "Workflows" },
  { path: "/journal", label: "Journal" },
];

function formatUTC(date: Date): string {
  return date.toISOString().replace("T", " ").slice(0, 19);
}

/** Portal liveness — real API probes + SSE stream health. */
export function HealthPage() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["market", "quotes", "XAUUSD"],
    queryFn: () => fetchQuote("XAUUSD"),
    refetchInterval: 5_000,
    retry: 3,
  });

  const [utc, setUtc] = React.useState(() => formatUTC(new Date()));
  React.useEffect(() => {
    const id = setInterval(() => setUtc(formatUTC(new Date())), 1000);
    return () => clearInterval(id);
  }, []);

  // Probe batch — real round-trip latency per endpoint.
  const probes = useQuery({
    queryKey: ["health", "probes"],
    queryFn: async (): Promise<ProbeResult[]> => {
      const results = await Promise.allSettled(
        PROBES.map(async (probe) => {
          const start = performance.now();
          try {
            if (probe.absolute) {
              // /health ada di root API (tanpa prefix /api/v1) dan TANPA auth
              const res = await fetch(probe.path);
              if (!res.ok)
                throw new ApiError("health probe failed", res.status, "HTTP_ERROR", "");
            } else {
              await get<unknown>(probe.path);
            }
            return {
              path: probe.path,
              label: probe.label,
              status: "ok" as const,
              latencyMs: Math.round(performance.now() - start),
            };
          } catch (err) {
            return {
              path: probe.path,
              label: probe.label,
              status: "error" as const,
              latencyMs: Math.round(performance.now() - start),
              code: err instanceof ApiError ? err.code : "UNKNOWN",
            };
          }
        })
      );
      return results.map((r) => (r.status === "fulfilled" ? r.value : r.reason));
    },
    refetchInterval: 15_000,
  });

  const streams = useStreamStore(useShallow((s) => s.getAllStreams()));
  const openStreams = streams.filter((s) => s.status === "open" && !s.stale);

  const status = error ? "degraded" : "ok";
  const apiError = error instanceof ApiError ? error : null;
  const okProbes = probes.data?.filter((p) => p.status === "ok").length ?? 0;

  return (
    <div className="space-y-4 p-3 md:p-4">
      {/* Bloomberg-style header */}
      <header className="flex items-center justify-between border-b border-line pb-2">
        <div className="flex items-center gap-3">
          <span className="font-mono text-[11px] uppercase tracking-widest text-ink-faint">SYSTEM HEALTH</span>
          <span className="h-px w-4 bg-line" aria-hidden="true" />
          <span className="font-mono text-[11px] text-ink-dim">API + SSE PROBES</span>
        </div>
        <div className="flex items-center gap-3">
          <span className="font-mono text-[10px] text-ink-faint tabular-nums">{utc} UTC</span>
          <span
            className={`h-2 w-2 rounded-full ${status === "ok" ? "bg-up" : "bg-warn"}`}
            aria-hidden="true"
          />
          <span className={`font-mono text-xs uppercase ${status === "ok" ? "text-up" : "text-warn"}`}>
            {status}
          </span>
        </div>
      </header>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
        {/* Market quote probe */}
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="flex items-center justify-between text-xs uppercase tracking-wider text-ink-faint">
              <span>Market Quote</span>
              {data && <Badge tone="ok" label="LIVE" />}
              {isLoading && <Badge tone="neutral" label="LOADING" />}
              {error && !isLoading && <Badge tone="warn" label="ERROR" />}
            </CardTitle>
          </CardHeader>
          <CardContent>
            {isLoading && (
              <div className="space-y-2">
                {[1, 2, 3, 4].map((i) => (
                  <div key={i} className="h-4 animate-pulse rounded bg-raised" />
                ))}
              </div>
            )}
            {apiError && (
              <div className="rounded-chip bg-raised p-3 text-xs">
                <p className="font-mono text-down">{apiError.code}</p>
                <p className="mt-1 text-ink-dim">{apiError.message}</p>
                {apiError.traceId && <p className="mt-1 text-ink-faint">trace: {apiError.traceId}</p>}
              </div>
            )}
            {data && (
              <div className="space-y-2 font-mono text-xs">
                {[
                  { label: "SYM", value: data.symbol },
                  { label: "BID", value: <NumericText value={data.bid} decimals={2} /> },
                  { label: "ASK", value: <NumericText value={data.ask} decimals={2} /> },
                  { label: "SPR", value: <NumericText value={data.spread} decimals={4} /> },
                  { label: "UPD", value: new Date(data.timestamp).toLocaleTimeString() },
                ].map(({ label, value }) => (
                  <div
                    key={label}
                    className="flex items-center justify-between border-b border-line/30 pb-1"
                  >
                    <span className="text-ink-faint">{label}</span>
                    <span className="tabular-nums text-ink">{value}</span>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Endpoint probes */}
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="flex items-center justify-between text-xs uppercase tracking-wider text-ink-faint">
              <span>API Probes</span>
              <Badge
                tone={probes.data && okProbes === PROBES.length ? "ok" : "warn"}
                label={`${okProbes}/${PROBES.length}`}
              />
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-1 font-mono text-[11px]">
            {probes.isLoading && <p className="text-ink-faint">Probing endpoints…</p>}
            {probes.data?.map((probe) => (
              <div
                key={probe.path}
                className="flex items-center justify-between rounded-chip px-1 py-1 hover:bg-raised"
              >
                <span className="flex items-center gap-2">
                  <span
                    className={`h-1.5 w-1.5 rounded-full ${probe.status === "ok" ? "bg-up" : "bg-down"}`}
                    aria-hidden="true"
                  />
                  <span className="text-ink-dim">{probe.label}</span>
                </span>
                <span className="tabular-nums text-ink-faint">
                  {probe.status === "ok" ? `${probe.latencyMs}ms` : probe.code ?? "ERR"}
                </span>
              </div>
            ))}
          </CardContent>
        </Card>

        {/* SSE streams */}
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="flex items-center justify-between text-xs uppercase tracking-wider text-ink-faint">
              <span>SSE Streams</span>
              <Badge tone={openStreams.length > 0 ? "ok" : "warn"} label={`${openStreams.length} OPEN`} />
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-1 font-mono text-[11px]">
            {streams.length === 0 && <p className="text-ink-faint">No active stream subscriptions.</p>}
            {streams.map((stream) => (
              <div
                key={stream.key}
                className="flex items-center justify-between rounded-chip px-1 py-1"
              >
                <span className="text-ink-dim">{stream.key}</span>
                <span
                  className={`uppercase ${stream.status === "open" ? "text-up" : "text-warn"}`}
                >
                  {stream.status}
                </span>
              </div>
            ))}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
