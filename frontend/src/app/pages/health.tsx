import { ApiError, get } from "@/api/client";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { NumericText } from "@/components/ui/numeric-text";
import { useQuery } from "@tanstack/react-query";

interface QuoteSnapshot {
  symbol: string;
  bid: number;
  ask: number;
  spread: number;
  timestamp: string;
}

async function fetchQuote(symbol: string): Promise<QuoteSnapshot> {
  return get<QuoteSnapshot>(`market/quotes/${symbol}`);
}

/** Portal liveness check — now a real API probe via TanStack Query. */
export function HealthPage() {
  const { data, isLoading, error, dataUpdatedAt } = useQuery({
    queryKey: ["market", "quotes", "XAUUSD"],
    queryFn: () => fetchQuote("XAUUSD"),
    refetchInterval: 5_000,
    retry: 3,
  });

  const status = error ? "degraded" : "ok";
  const apiError = error instanceof ApiError ? error : null;

  return (
    <div className="p-4 space-y-4">
      {/* Bloomberg-style header */}
      <div className="flex items-center justify-between border-b border-border-subtle pb-3">
        <div className="flex items-center gap-3">
          <span className="font-mono text-[11px] uppercase tracking-widest text-text-muted">SYSTEM HEALTH</span>
          <span className="h-px w-4 bg-border-subtle" aria-hidden="true" />
          <span className="font-mono text-[11px] text-text-secondary">API PROBE · XAUUSD</span>
        </div>
        <div className="flex items-center gap-2">
          <span
            className={`h-2 w-2 rounded-full ${status === "ok" ? "bg-up" : "bg-warn"}`}
            aria-hidden="true"
          />
          <span className={`font-mono text-xs uppercase ${status === "ok" ? "text-up" : "text-warn"}`}>
            {status}
          </span>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
        {/* Quote panel */}
        <Card className="lg:col-span-1">
          <CardHeader className="pb-2">
            <CardTitle className="flex items-center justify-between text-xs uppercase tracking-wider text-text-muted">
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
                  <div key={i} className="h-4 animate-pulse rounded bg-bg-overlay" />
                ))}
              </div>
            )}
            {apiError && (
              <div className="rounded-chip bg-bg-overlay p-3 text-xs">
                <p className="font-mono text-down">{apiError.code}</p>
                <p className="mt-1 text-text-secondary">{apiError.message}</p>
                {apiError.traceId && (
                  <p className="mt-1 text-text-muted">trace: {apiError.traceId}</p>
                )}
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
                  <div key={label} className="flex items-center justify-between border-b border-border-subtle/30 pb-1">
                    <span className="text-text-muted">{label}</span>
                    <span className="tabular-nums text-text-primary">{value}</span>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Timestamps */}
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-xs uppercase tracking-wider text-text-muted">Probe Timestamps</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 font-mono text-xs">
            <div className="flex items-center justify-between">
              <span className="text-text-muted">LAST CHECK</span>
              <span className="tabular-nums text-text-secondary">
                {dataUpdatedAt ? new Date(dataUpdatedAt).toISOString().slice(11, 19) : "—"}
              </span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-text-muted">INTERVAL</span>
              <span className="tabular-nums text-text-secondary">5s</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-text-muted">RETRIES</span>
              <span className="tabular-nums text-text-secondary">3</span>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
