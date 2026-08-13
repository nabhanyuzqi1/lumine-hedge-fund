import { Link } from "react-router-dom";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

/**
 * `/` — Landing portal (card hub). Entry surface for the Lumine operating
 * system. Each card routes into a deep surface; the Terminal is the live
 * trading workspace (F-Sprint 5/6) and lives at `/terminal`. Reinstated at
 * root after F-Sprint 6 moved Terminal to `/terminal` (2026-08-12).
 */

type PortalEntry = {
  href: string;
  title: string;
  blurb: string;
  group: "Live" | "Surfaces" | "Ops";
};

const PORTAL: PortalEntry[] = [
  {
    href: "/terminal",
    title: "Terminal",
    blurb: "Live XAUUSD trading workspace — chart, quote, positions, orders, risk, committee.",
    group: "Live",
  },
  {
    href: "/dashboard",
    title: "Dashboard",
    blurb: "Portfolio, risk, and execution overview with institutional chart grid.",
    group: "Surfaces",
  },
  {
    href: "/streams",
    title: "Streams",
    blurb: "Realtime market, agent, and committee event streams with health.",
    group: "Live",
  },
  {
    href: "/journal",
    title: "Journal",
    blurb: "Trade journal and performance review across sessions.",
    group: "Surfaces",
  },
  {
    href: "/health",
    title: "Health",
    blurb: "Infrastructure and data-freshness health dashboard.",
    group: "Ops",
  },
  {
    href: "/admin/keys",
    title: "Admin Keys",
    blurb: "API key and credential management for operators.",
    group: "Ops",
  },
];

const GROUP_TONE: Record<PortalEntry["group"], "ok" | "info" | "warn"> = {
  Live: "ok",
  Surfaces: "info",
  Ops: "warn",
};

export function LandingPage() {
  return (
    <div className="mx-auto w-full max-w-[1200px] space-y-8 p-6">
      <header className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="space-y-3">
          <div className="flex items-center gap-2">
            <span className="h-2.5 w-2.5 rounded-full bg-emerald-500" aria-hidden="true" />
            <span className="font-mono text-xs uppercase tracking-widest text-text-secondary">
              Lumine · AI-Native Quantitative Fund
            </span>
          </div>
          <h1 className="font-display text-3xl font-semibold text-text-primary">
            Institutional operating system for autonomous trading
          </h1>
          <p className="max-w-2xl text-sm text-text-secondary">
            A hierarchical AI committee — CIO, Investment Committee, Risk, Portfolio Manager — makes
            auditable, replayable decisions on XAUUSD. Select a portal below to enter a surface.
          </p>
        </div>
        <div className="flex-shrink-0">
          <Link to="/auth" data-testid="portal-signin">
            <Button variant="secondary" className="w-full sm:w-auto">
              Sign In
            </Button>
          </Link>
        </div>
      </header>

      <section aria-labelledby="portal-heading" className="space-y-4">
        <h2 id="portal-heading" className="sr-only">
          Portal entries
        </h2>
        <ul className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {PORTAL.map((entry) => (
            <li key={entry.href}>
              <Link
                to={entry.href}
                data-testid={`portal-${entry.title.toLowerCase().replace(/\s+/g, "-")}`}
                className="group block h-full rounded-panel border border-border-subtle bg-bg-raised p-0 shadow-panel outline-none transition-colors hover:border-accent/60 focus-visible:ring-2 focus-visible:ring-accent"
              >
                <Card className="border-0 bg-transparent shadow-none">
                  <CardHeader className="flex-row items-start justify-between gap-2 space-y-0">
                    <CardTitle>{entry.title}</CardTitle>
                    <Badge tone={GROUP_TONE[entry.group]} label={entry.group} />
                  </CardHeader>
                  <CardContent>
                    <CardDescription className="text-sm leading-relaxed text-text-secondary">
                      {entry.blurb}
                    </CardDescription>
                    <span className="mt-3 inline-flex items-center gap-1 text-xs font-medium text-accent">
                      Enter
                      <span
                        aria-hidden="true"
                        className="transition-transform group-hover:translate-x-0.5"
                      >
                        →
                      </span>
                    </span>
                  </CardContent>
                </Card>
              </Link>
            </li>
          ))}
        </ul>
      </section>

      <footer className="border-t border-border-subtle pt-4 text-xs text-text-tertiary">
        Backend Phase 9 pending — surfaces run on demo fixtures. All decisions carry an auditable,
        replayable chain.
      </footer>
    </div>
  );
}
