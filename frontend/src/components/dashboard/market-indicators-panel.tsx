import { useMarketIndicators } from "@/api/hooks";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

/**
 * Market indicators panel (F-04 features + F-06 volatility/spread/session).
 * All values come from live endpoints (market/volatility|spread|session|features).
 */
export function MarketIndicatorsPanel({ symbol }: { symbol: string }) {
  const { data, isError } = useMarketIndicators(symbol);

  const sessionTone =
    data?.session === "asian" ? "ok" : data?.session === "american" ? "warn" : "neutral";

  return (
    <Card data-testid="market-indicators-panel">
      <CardHeader>
        <CardTitle>Market Indicators</CardTitle>
        <CardDescription>{symbol} — live</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {isError && (
          <p className="text-xs text-danger" role="alert">
            Indicators unavailable — backend offline.
          </p>
        )}
        {data && (
          <>
            <div className="grid grid-cols-3 gap-2 text-xs">
              <div>
                <dt className="text-text-tertiary">Volatility</dt>
                <dd className="font-mono text-text-primary">{(data.volatility * 100).toFixed(2)}%</dd>
              </div>
              <div>
                <dt className="text-text-tertiary">Spread</dt>
                <dd className="font-mono text-text-primary">{data.spread.toFixed(2)}</dd>
              </div>
              <div>
                <dt className="text-text-tertiary">Session</dt>
                <dd className="pt-0.5">
                  <Badge tone={sessionTone} label={data.session} />
                </dd>
              </div>
            </div>
            <div className="grid grid-cols-3 gap-2 border-t border-border-subtle pt-2 text-xs">
              {(["rsi_14", "atr_14", "vwap"] as const).map((key) => (
                <div key={key}>
                  <dt className="text-text-tertiary">{key}</dt>
                  <dd className="font-mono text-text-primary">
                    {data.features[key] != null ? Number(data.features[key]).toFixed(2) : "—"}
                  </dd>
                </div>
              ))}
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}
