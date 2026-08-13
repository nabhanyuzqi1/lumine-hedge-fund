import { ApiError, get } from "@/api/client";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
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
    <main className="flex min-h-screen flex-col items-center justify-center bg-abyss text-ink">
      <Card className="w-full max-w-md">
        <CardHeader>
          <CardTitle>System health</CardTitle>
          <CardDescription>Realtime API probe for XAUUSD</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center justify-between">
            <span className="text-text-secondary">Status</span>
            <Badge tone={status === "ok" ? "ok" : "warn"} label={status} />
          </div>

          {isLoading && <p className="text-sm text-text-muted">Loading quote...</p>}

          {apiError && (
            <div className="rounded-panel bg-bg-raised p-3 text-sm">
              <p className="text-danger">{apiError.code}</p>
              <p className="text-text-secondary">{apiError.message}</p>
              {apiError.traceId && <p className="text-text-muted">trace: {apiError.traceId}</p>}
            </div>
          )}

          {data && (
            <div className="space-y-2 font-mono text-sm">
              <div className="flex justify-between">
                <span className="text-text-secondary">Symbol</span>
                <span>{data.symbol}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-text-secondary">Bid</span>
                <NumericText value={data.bid} decimals={2} />
              </div>
              <div className="flex justify-between">
                <span className="text-text-secondary">Ask</span>
                <NumericText value={data.ask} decimals={2} />
              </div>
              <div className="flex justify-between">
                <span className="text-text-secondary">Spread</span>
                <NumericText value={data.spread} decimals={4} />
              </div>
              <div className="flex justify-between">
                <span className="text-text-secondary">Updated</span>
                <span className="text-text-muted">
                  {new Date(data.timestamp).toLocaleTimeString()}
                </span>
              </div>
            </div>
          )}

          <p className="text-xs text-text-muted">
            Last checked: {dataUpdatedAt ? new Date(dataUpdatedAt).toISOString() : "—"}
          </p>
        </CardContent>
      </Card>
    </main>
  );
}
