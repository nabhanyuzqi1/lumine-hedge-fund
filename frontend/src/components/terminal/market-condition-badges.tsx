import { useMarketIndicators } from "@/api/hooks";
import { Badge } from "@/components/ui/badge";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";

/**
 * MarketConditionBadges (roadmap item 8): volatility / spread / session
 * indicators untuk chart header terminal. Data: useMarketIndicators
 * (REST-first, 60s staleTime). Hidden saat data belum tersedia.
 */

// Volatility threshold (ATR-based, XAUUSD): <15 tenang, 15–30 normal, >30 wild.
function volTone(v: number): "ok" | "warn" | "danger" {
  if (v >= 30) return "danger";
  if (v >= 15) return "warn";
  return "ok";
}

// Spread alert: >50 points = lebar (news/rollover), 20–50 sedang.
function spreadTone(s: number): "ok" | "warn" | "danger" {
  if (s > 50) return "danger";
  if (s > 20) return "warn";
  return "ok";
}

const SESSION_LABEL: Record<string, string> = {
  asian: "ASIA",
  london: "LONDON",
  newyork: "NY",
  overlap_ldn_ny: "LDN×NY",
};

export function MarketConditionBadges({ symbol }: { symbol: string }) {
  const { data } = useMarketIndicators(symbol);
  if (!data) return null;

  const vol = data.volatility;
  const spread = data.spread;
  const session = data.session;
  const hasAny = vol > 0 || spread > 0 || (session && session !== "unknown");
  if (!hasAny) return null;

  return (
    <TooltipProvider delayDuration={200}>
      <div className="flex items-center gap-1.5" data-testid="market-condition-badges">
        {vol > 0 && (
          <Tooltip>
            <TooltipTrigger asChild>
              <span>
                <Badge
                  tone={volTone(vol)}
                  label={`VOL ${vol.toFixed(1)}`}
                  className="font-mono text-[10px]"
                />
              </span>
            </TooltipTrigger>
            <TooltipContent>Volatilitas (ATR) — &gt;30 tinggi, &lt;15 tenang</TooltipContent>
          </Tooltip>
        )}
        {spread > 0 && (
          <Tooltip>
            <TooltipTrigger asChild>
              <span>
                <Badge
                  tone={spreadTone(spread)}
                  label={`SPR ${spread.toFixed(0)}`}
                  className="font-mono text-[10px]"
                />
              </span>
            </TooltipTrigger>
            <TooltipContent>Spread poin — &gt;50 lebar (hindari entry)</TooltipContent>
          </Tooltip>
        )}
        {session && session !== "unknown" && (
          <Tooltip>
            <TooltipTrigger asChild>
              <span>
                <Badge
                  tone="neutral"
                  label={SESSION_LABEL[session] ?? session.toUpperCase()}
                  className="font-mono text-[10px]"
                />
              </span>
            </TooltipTrigger>
            <TooltipContent>Sesi pasar aktif</TooltipContent>
          </Tooltip>
        )}
      </div>
    </TooltipProvider>
  );
}