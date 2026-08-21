import { useMarketIndicators } from "@/api/hooks";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

/**
 * FeaturePanel (F-06): computed technical features + volatility/spread/session.
 * Backed by GET /api/v1/market/features/{symbol} + volatility/spread/session.
 * Live data via SSE; REST-first fallback ke fixture.
 */
export function FeaturePanel({ symbol }: { symbol: string }) {
  const { data, isPending } = useMarketIndicators(symbol);
  const features = data?.features;
  const vol = data?.volatility;
  const spread = data?.spread;
  const session = data?.session;

  if (isPending) {
    return (
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm">Features</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-2">
            {[...Array(5)].map((_, i) => (
              <div key={i} className="h-3 animate-pulse rounded bg-raised" />
            ))}
          </div>
        </CardContent>
      </Card>
    );
  }

  // If no features data at all, show nothing (don't occupy space).
  const rows: { label: string; value: string }[] = [];

  if (vol) {
    rows.push({ label: "Volatility", value: `${(vol as number).toFixed(2)}` });
  }
  if (spread) {
    rows.push({ label: "Spread", value: `${(spread as number).toFixed(1)}` });
  }
  if (session) {
    rows.push({ label: "Session", value: (session as string) });
  }
  if (features) {
    const order = ["atr_14", "rsi_14", "ema_20", "ema_50", "ema_200", "volume_ratio", "bb_width", "adx_14"];
    for (const key of order) {
      const v = features[key];
      if (v != null) {
        const label = key.replace(/_/g, " ").toUpperCase();
        rows.push({ label, value: typeof v === "number" ? v.toFixed(2) : String(v) });
      }
    }
  }

  // Tidak ada data sama sekali — jangan tampilkan card kosong.
  if (rows.length === 0) {
    return null;
  }

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm">Features</CardTitle>
      </CardHeader>
      <CardContent className="space-y-1">
        {rows.map((r) => (
          <div key={r.label} className="flex items-center justify-between py-0.5">
            <span className="text-[10px] font-medium uppercase tracking-wider text-ink-faint">
              {r.label}
            </span>
            <span className="font-mono text-[11px] tabular-nums text-ink">{r.value}</span>
          </div>
        ))}
      </CardContent>
    </Card>
  );
}