import { useExposure } from "@/api/hooks";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

/**
 * ExposureSummaryCard (F-07): per-symbol weight of NAV from
 * GET /api/v1/portfolio/exposure (REST-first, fixture fallback).
 */
export function ExposureSummaryCard() {
  const { data, isPending } = useExposure();

  return (
    <Card data-testid="exposure-summary-card">
      <CardHeader>
        <CardTitle>Exposure</CardTitle>
        <CardDescription>% of NAV per asset</CardDescription>
      </CardHeader>
      <CardContent className="space-y-2">
        {isPending && <p className="py-2 text-center text-xs text-text-tertiary">Loading exposure…</p>}
        {data?.map((item) => (
          <div key={item.symbol} className="text-xs">
            <div className="flex items-center justify-between">
              <span className="text-text-secondary">{item.symbol}</span>
              <span className="font-mono text-text-primary">
                {(item.weight * 100).toFixed(1)}%
              </span>
            </div>
            <div className="mt-0.5 h-1.5 overflow-hidden rounded-full bg-bg-overlay">
              <div
                className="h-full rounded-full bg-accent"
                style={{ width: `${Math.min(item.weight * 100, 100)}%` }}
              />
            </div>
          </div>
        ))}
      </CardContent>
    </Card>
  );
}
