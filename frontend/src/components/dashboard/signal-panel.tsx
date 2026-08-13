import { useSignals } from "@/api/hooks";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { AnalystCard } from "./analyst-card";

/**
 * SignalPanel (F-04): live analyst signals for a symbol, newest first.
 * Backed by GET /api/v1/market/signals/{symbol} (REST-first, fixture fallback).
 */
export function SignalPanel({ symbol }: { symbol: string }) {
  const { data, isPending } = useSignals(symbol);

  return (
    <Card data-testid="signal-panel">
      <CardHeader>
        <CardTitle>Analyst Signals</CardTitle>
        <CardDescription>{symbol} — committee inputs</CardDescription>
      </CardHeader>
      <CardContent className="space-y-2">
        {isPending && <p className="py-2 text-center text-xs text-text-tertiary">Loading signals…</p>}
        {data && data.length === 0 && (
          <p className="py-2 text-center text-xs text-text-tertiary">No signals yet.</p>
        )}
        {data?.map((signal, i) => (
          <AnalystCard key={`${signal.analyst}-${i}`} signal={signal} />
        ))}
      </CardContent>
    </Card>
  );
}
