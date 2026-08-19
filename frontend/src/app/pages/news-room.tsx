import { useQuery } from "@tanstack/react-query";

import { get } from "@/api/client";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

/**
 * NewsRoomPage (18 Aug 2026) — user request: "halaman khusus yang
 * menampung berita-berita, rss feed, economic calendar, dan macro data
 * realtime". Sumber: backend RSS worker (BBC/OilPrice/MarketWatch) +
 * eco calendar worker (faireconomy) + quotes realtime.
 */

interface NewsItem {
  title: string;
  source: string;
  ts?: number | string;
  url?: string;
  summary?: string;
}

interface CalendarEvent {
  date: string;
  currency: string;
  event: string;
  impact: string;
  previous?: string;
  forecast?: string;
}

interface Quote {
  symbol: string;
  bid?: number;
  ask?: number;
  last?: number;
  change_pct?: number;
}

function useNews(limit = 30) {
  return useQuery({
    queryKey: ["news", limit],
    queryFn: () => get<{ items: NewsItem[] }>(`/market/news?limit=${limit}`),
    // 18 Aug 2026: 60s → 30s — "halaman news lebih detail realtime".
    refetchInterval: 30_000,
  });
}

/** Tag relevansi headline terhadap XAUUSD (18 Aug 2026): gold/dollar/Fed
 *  langsung mempengaruhi emas; sisanya konteks macro. */
function impactTag(title: string): "gold" | "dollar" | "macro" | null {
  const t = title.toLowerCase();
  const gold =
    /\b(gold|golds|bullion|precious metals|xau|xauusd)\b/.test(t) ||
    /gold (price|spot|rally|drop|steady|slides)/.test(t);
  if (gold) return "gold";
  const dollar =
    /\b(dollar|usd|dxy|fed|treasury|yield|inflation|cpi|nonfarm|payrolls|fomc|powell|rates|interest)\b/.test(t);
  if (dollar) return "dollar";
  const macro =
    /\b(oil|energy|economy|growth|recession|china|trade|gdp|jobs|unemployment|bank)\b/.test(t);
  if (macro) return "macro";
  return null;
}

const TAG_TONE: Record<string, string> = {
  gold: "bg-amber/15 text-amber",
  dollar: "bg-accent/15 text-accent",
  macro: "bg-bg-raised text-ink-faint",
};

function useCalendar() {
  return useQuery({
    queryKey: ["eco-calendar"],
    queryFn: () => get<{ items: CalendarEvent[] }>("/market/economic-calendar"),
    refetchInterval: 180_000,
  });
}

function useQuotes() {
  return useQuery({
    queryKey: ["quotes"],
    queryFn: () =>
      get<Record<string, Quote>>(
        "/market/quotes?symbols=XAUUSD&symbols=XAGUSD&symbols=USOIL&symbols=BTCUSD"
      ),
    refetchInterval: 30_000,
  });
}

function useDXY() {
  return useQuery({
    queryKey: ["dxy"],
    queryFn: () =>
      get<{ price?: number; high?: number; low?: number; source?: string }>(
        "/market/dxy"
      ),
    refetchInterval: 60_000,
  });
}

const IMPACT_TONE: Record<string, string> = {
  high: "bg-crimson/15 text-crimson",
  medium: "bg-amber/15 text-amber",
  low: "bg-ink-faint/15 text-ink-dim",
};

export function NewsRoomPage() {
  const news = useNews(30);
  const calendar = useCalendar();
  const quotes = useQuotes();
  const dxyQuery = useDXY();

  const items = Array.isArray(news.data?.items) ? news.data.items : [];
  const events = Array.isArray(calendar.data?.items) ? calendar.data.items : [];
  const quoteMap = (quotes.data ?? {}) as Record<string, Quote>;
  const quoteItems = Object.entries(quoteMap).map(([symbol, q]) => ({
    symbol,
    ...(typeof q === "object" && q !== null ? q : {}),
  }));
  const dxy = dxyQuery.data;

  return (
    <div className="space-y-4 p-4">
      {/* Macro quotes strip */}
      <div className="flex flex-wrap gap-2">
        {dxy?.price != null && (
          <div className="rounded-chip border border-accent/30 bg-accent/5 px-3 py-1.5">
            <p className="font-mono text-[10px] uppercase text-ink-faint">
              DXY (USD Index)
            </p>
            <p className="font-mono text-sm text-ink">
              {dxy.price}
              {dxy.low != null && (
                <span className="ml-1.5 text-[10px] text-ink-faint">
                  L {dxy.low}
                </span>
              )}
              {dxy.high != null && (
                <span className="ml-1.5 text-[10px] text-ink-faint">
                  H {dxy.high}
                </span>
              )}
            </p>
            <p className="font-mono text-[9px] text-ink-faint">
              inverse corr emas · {dxy.source ?? ""}
            </p>
          </div>
        )}
        {quoteItems.length === 0 && !dxy?.price && (
          <p className="text-xs text-ink-faint">memuat quotes…</p>
        )}
        {quoteItems.slice(0, 8).map((q) => (
          <div
            key={q.symbol}
            className="rounded-chip border border-line bg-bg px-3 py-1.5"
          >
            <p className="font-mono text-[10px] uppercase text-ink-faint">
              {q.symbol}
            </p>
            <p className="font-mono text-sm text-ink">
              {q.last ?? q.bid ?? "—"}
              {typeof q.change_pct === "number" && (
                <span
                  className={
                    q.change_pct >= 0
                      ? "ml-1.5 text-[10px] text-up"
                      : "ml-1.5 text-[10px] text-down"
                  }
                >
                  {q.change_pct >= 0 ? "+" : ""}
                  {q.change_pct.toFixed(2)}%
                </span>
              )}
            </p>
          </div>
        ))}
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        {/* News / RSS feed */}
        <Card className="lg:col-span-2">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-text-secondary">
              Berita & RSS Feed — macro / emas
            </CardTitle>
          </CardHeader>
          <CardContent>
            {items.length === 0 ? (
              <p className="py-4 text-xs text-ink-faint">
                Belum ada headline dari worker RSS (refresh tiap 5 menit).
              </p>
            ) : (
              <div className="space-y-2.5">
                {items.map((n, i) => (
                  <div key={`${n.source}-${i}`} className="border-b border-line/40 pb-2 last:border-0">
                    <a
                      href={n.url}
                      target="_blank"
                      rel="noreferrer"
                      className="text-sm leading-snug text-ink hover:text-accent"
                    >
                      {n.title}
                    </a>
                    <p className="mt-0.5 flex items-center gap-2 font-mono text-[10px] text-ink-faint">
                      <span className="rounded bg-bg-raised px-1 py-0.5">
                        {n.source}
                      </span>
                      {(() => {
                        const tag = impactTag(n.title);
                        return tag ? (
                          <span className={`rounded px-1 py-0.5 ${TAG_TONE[tag]}`}>
                            {tag}
                          </span>
                        ) : null;
                      })()}
                      {n.ts ? <span>{new Date(n.ts as number).toLocaleString()}</span> : null}
                    </p>
                    {n.summary && (
                      <p className="mt-1 text-[11px] leading-relaxed text-ink-dim">
                        {n.summary}
                      </p>
                    )}
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Economic calendar */}
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-text-secondary">
              Economic Calendar — 72 jam ke depan
            </CardTitle>
          </CardHeader>
          <CardContent>
            {events.length === 0 ? (
              <p className="py-4 text-xs text-ink-faint">
                Belum ada event dari worker calendar (refresh tiap 30 menit).
              </p>
            ) : (
              <div className="space-y-1.5">
                {events.map((e, i) => (
                  <div
                    key={i}
                    className="flex items-center justify-between gap-2 rounded-chip border border-line/40 bg-bg px-2.5 py-1.5"
                  >
                    <div className="min-w-0">
                      <p className="truncate text-[11px] font-medium text-ink">
                        {e.event}
                      </p>
                      <p className="font-mono text-[10px] text-ink-faint">
                        {new Date(e.date).toLocaleDateString("id-ID", {
                          weekday: "short",
                          day: "numeric",
                          month: "short",
                          hour: "2-digit",
                          minute: "2-digit",
                        })}{" "}
                        · {e.currency}
                        {e.forecast ? ` · F: ${e.forecast}` : ""}
                      </p>
                    </div>
                    <span
                      className={`shrink-0 rounded px-1.5 py-0.5 font-mono text-[9px] uppercase ${IMPACT_TONE[e.impact] ?? "bg-bg-raised text-ink-faint"}`}
                    >
                      {e.impact}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}