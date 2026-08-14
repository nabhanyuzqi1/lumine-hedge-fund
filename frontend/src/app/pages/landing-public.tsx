import { Link } from "react-router-dom";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";

/**
 * `/` — Public landing page (Lumine Hedge Fund).
 *
 * Design: Linear-app principles (dark luminance-stacked canvas, translucent
 * borders, compressed display tracking, reserved accent) applied on Lumine's
 * institutional tokens (abyss/ink/accent from index.css). Built on the
 * shadcn-style ui kit (Button/Badge/Card) — no external CSS.
 */

const NAV_LINKS = [
  { label: "Platform", href: "#platform" },
  { label: "Security", href: "#security" },
  { label: "Docs", href: "#docs" },
];

const STATS = [
  { value: "XAUUSD", label: "First market" },
  { value: "8", label: "Instruments on tape" },
  { value: "100%", label: "Auditable decisions" },
  { value: "<120ms", label: "API p95 latency" },
];

const FEATURES = [
  {
    title: "AI Investment Committee",
    body: "Technical, macro, news and SMC analysts debate every position; CIO arbitrates. Full deliberation transcript on-chain of record.",
  },
  {
    title: "Risk Engine",
    body: "Exposure, correlation, daily-loss and kill-switch gates execute deterministically — before any order reaches the broker.",
  },
  {
    title: "Institutional Execution",
    body: "MT5 bridge with order state machines, TCA benchmarking and replay protection. Every fill reconciles to a decision.",
  },
  {
    title: "Decision Lineage",
    body: "Every trade links back to the models, prompts, data and committee vote that produced it. Reproducible by design.",
  },
  {
    title: "Realtime Terminal",
    body: "Bloomberg-class workspace: live SSE streams, candlesticks, risk gauges and keyboard-first workflows at 60fps.",
  },
  {
    title: "Observability",
    body: "Prometheus metrics, structured logs, container-level monitoring and a control center for the whole stack.",
  },
];

function NavBar() {
  return (
    <header className="sticky top-0 z-40 border-b border-line-soft bg-abyss/80 backdrop-blur">
      <div className="mx-auto flex h-14 w-full max-w-6xl items-center justify-between px-6">
        <div className="flex items-center gap-2">
          <div className="flex h-7 w-7 items-center justify-center rounded-chip bg-accent">
            <span className="font-display text-xs font-bold text-white">L</span>
          </div>
          <span className="font-display text-sm font-semibold tracking-tight text-ink">LUMINE</span>
        </div>
        <nav className="hidden items-center gap-6 md:flex" aria-label="Primary">
          {NAV_LINKS.map((link) => (
            <a
              key={link.href}
              href={link.href}
              className="text-[13px] font-medium text-ink-dim transition-colors hover:text-ink"
            >
              {link.label}
            </a>
          ))}
        </nav>
        <div className="flex items-center gap-2">
          <Link to="/login">
            <Button variant="ghost" size="sm">
              Sign in
            </Button>
          </Link>
          <Link to="/login">
            <Button variant="primary" size="sm">
              Get access
            </Button>
          </Link>
        </div>
      </div>
    </header>
  );
}

/** Terminal mock — static preview using live design tokens (no data calls). */
function TerminalMock() {
  const rows = [
    { symbol: "XAUUSD", last: "2,420.30", change: "+0.42%", tone: "text-up" },
    { symbol: "XAGUSD", last: "28.421", change: "+0.18%", tone: "text-up" },
    { symbol: "EURUSD", last: "1.08500", change: "-0.07%", tone: "text-down" },
    { symbol: "BTCUSD", last: "64,120.0", change: "+1.24%", tone: "text-up" },
  ] as const;
  return (
    <div className="overflow-hidden rounded-panel border border-line bg-raised shadow-panel">
      <div className="flex items-center justify-between border-b border-line px-4 py-2">
        <span className="font-mono text-[10px] uppercase tracking-widest text-ink-faint">
          LUMINE TERMINAL
        </span>
        <div className="flex items-center gap-2">
          <span className="h-1.5 w-1.5 rounded-full bg-up" aria-hidden="true" />
          <span className="font-mono text-[10px] text-ink-faint">SSE LIVE</span>
        </div>
      </div>
      <div className="grid grid-cols-2 divide-x divide-line md:grid-cols-4">
        {rows.map((row) => (
          <div key={row.symbol} className="px-4 py-3">
            <div className="font-mono text-[10px] uppercase text-ink-faint">{row.symbol}</div>
            <div className="font-mono text-sm font-medium tabular-nums text-ink">{row.last}</div>
            <div className={`font-mono text-[10px] tabular-nums ${row.tone}`}>{row.change}</div>
          </div>
        ))}
      </div>
      <div className="grid grid-cols-1 divide-y divide-line border-t border-line md:grid-cols-2 md:divide-x md:divide-y-0">
        <div className="px-4 py-3">
          <div className="mb-2 flex items-center justify-between">
            <span className="font-mono text-[10px] uppercase tracking-wider text-ink-faint">Positions</span>
            <Badge tone="ok" label="2 OPEN" />
          </div>
          <div className="space-y-1 font-mono text-[11px]">
            <div className="flex justify-between">
              <span className="text-ink-dim">XAUUSD LONG</span>
              <span className="tabular-nums text-up">+$1,284.50</span>
            </div>
            <div className="flex justify-between">
              <span className="text-ink-dim">EURUSD SHORT</span>
              <span className="tabular-nums text-up">+$312.08</span>
            </div>
          </div>
        </div>
        <div className="px-4 py-3">
          <div className="mb-2 flex items-center justify-between">
            <span className="font-mono text-[10px] uppercase tracking-wider text-ink-faint">Committee</span>
            <Badge tone="info" label="DELIBERATING" />
          </div>
          <div className="space-y-1 font-mono text-[11px] text-ink-dim">
            <div>Technical · momentum bullish</div>
            <div>Macro · USD real yield easing</div>
            <div>Risk · exposure within limits</div>
          </div>
        </div>
      </div>
    </div>
  );
}

export function LandingPublicPage() {
  return (
    <div className="min-h-screen bg-abyss text-ink">
      <NavBar />

      {/* Hero */}
      <section className="relative overflow-hidden">
        <div
          className="pointer-events-none absolute inset-0"
          aria-hidden="true"
          style={{
            background:
              "radial-gradient(600px 300px at 50% -10%, rgba(77,141,255,0.14), transparent 70%)",
          }}
        />
        <div className="relative mx-auto w-full max-w-6xl px-6 pb-20 pt-24 text-center md:pt-32">
          <div className="mx-auto mb-6 flex justify-center">
            <Badge tone="info" label="AI-NATIVE QUANTITATIVE PLATFORM" />
          </div>
          <h1 className="mx-auto max-w-3xl font-display text-4xl font-medium leading-[1.05] tracking-[-0.03em] text-ink md:text-6xl">
            An autonomous hedge fund,
            <br />
            engineered like infrastructure.
          </h1>
          <p className="mx-auto mt-6 max-w-xl text-base leading-relaxed text-ink-dim md:text-lg">
            Lumine runs a hierarchical team of AI agents — analysts, risk
            officers, portfolio managers — that deliberate, decide and execute
            with institutional discipline. Every decision is auditable,
            replayable and reversible.
          </p>
          <div className="mt-8 flex flex-wrap items-center justify-center gap-3">
            <Link to="/login">
              <Button variant="primary" size="lg">
                Open Terminal
              </Button>
            </Link>
            <a href="#platform">
              <Button variant="secondary" size="lg">
                Explore the platform
              </Button>
            </a>
          </div>
          <div className="mt-14 text-left">
            <TerminalMock />
          </div>
        </div>
      </section>

      {/* Stats strip */}
      <section className="border-y border-line-soft bg-bg">
        <div className="mx-auto grid w-full max-w-6xl grid-cols-2 divide-x divide-line-soft md:grid-cols-4">
          {STATS.map((stat) => (
            <div key={stat.label} className="px-6 py-8 text-center">
              <div className="font-display text-2xl font-semibold tracking-tight text-ink tabular-nums">
                {stat.value}
              </div>
              <div className="mt-1 font-mono text-[10px] uppercase tracking-widest text-ink-faint">
                {stat.label}
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* Features */}
      <section id="platform" className="mx-auto w-full max-w-6xl px-6 py-24">
        <div className="mb-14 max-w-2xl">
          <h2 className="font-display text-3xl font-medium tracking-[-0.02em] text-ink md:text-4xl">
            Built like a real fund.
            <br />
            Run like software.
          </h2>
          <p className="mt-4 text-base leading-relaxed text-ink-dim">
            Not a signal bot. A hierarchy of specialized AI agents collaborating
            under a strict risk framework — with the audit trail to prove it.
          </p>
        </div>
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
          {FEATURES.map((feature) => (
            <Card key={feature.title} className="transition-colors hover:bg-raised">
              <CardContent className="p-6">
                <h3 className="text-[15px] font-semibold tracking-tight text-ink">
                  {feature.title}
                </h3>
                <p className="mt-2 text-sm leading-relaxed text-ink-dim">{feature.body}</p>
              </CardContent>
            </Card>
          ))}
        </div>
      </section>

      {/* Agent hierarchy */}
      <section id="docs" className="border-y border-line-soft bg-bg">
        <div className="mx-auto w-full max-w-6xl px-6 py-24">
          <div className="mb-10 max-w-2xl">
            <h2 className="font-display text-3xl font-medium tracking-[-0.02em] text-ink">
              A hierarchy, not a swarm.
            </h2>
            <p className="mt-4 text-base leading-relaxed text-ink-dim">
              Autonomy is bounded by design. Analysts propose, the committee
              debates, the risk officer vetoes, the portfolio manager executes.
            </p>
          </div>
          <div className="overflow-x-auto rounded-panel border border-line bg-abyss p-6">
            <pre className="font-mono text-xs leading-6 text-ink-dim">{`CEO
└── Chief Investment Officer (CIO)
    └── Investment Committee
        ├── Technical Analyst
        ├── Macro Analyst
        ├── News Analyst
        └── SMC Analyst
    ├── Risk Officer
    └── Portfolio Manager
        └── Execution Controller
            └── Trade Journal
                └── Performance Reviewer`}</pre>
          </div>
        </div>
      </section>

      {/* Security */}
      <section id="security" className="mx-auto w-full max-w-6xl px-6 py-24">
        <div className="grid grid-cols-1 gap-12 md:grid-cols-2">
          <div>
            <Badge tone="ok" label="SECURITY" />
            <h2 className="mt-4 font-display text-3xl font-medium tracking-[-0.02em] text-ink">
              Institutional guardrails.
            </h2>
            <p className="mt-4 text-base leading-relaxed text-ink-dim">
              First-party session auth with PBKDF2-HMAC-SHA256 credentials,
              HMAC-signed API contracts with replay protection, and
              role-scoped access from analyst to superadmin.
            </p>
            <ul className="mt-6 space-y-3 text-sm text-ink-dim">
              <li className="flex gap-3">
                <span className="text-accent">→</span> HttpOnly session cookies, constant-time verification
              </li>
              <li className="flex gap-3">
                <span className="text-accent">→</span> HMAC-SHA256 signed requests, ±300s window, replay cache
              </li>
              <li className="flex gap-3">
                <span className="text-accent">→</span> Role hierarchy: user → admin → superadmin at proxy + SPA
              </li>
            </ul>
          </div>
          <div className="rounded-panel border border-line bg-raised p-6 font-mono text-xs leading-6">
            <div className="text-ink-faint"># session verify — Caddy forward_auth</div>
            <div className="text-ink-dim">
              <span className="text-up">200</span> GET /api/auth/verify?role=superadmin
            </div>
            <div className="text-ink-dim">
              <span className="text-down">401</span> GET /api/auth/verify?role=superadmin
            </div>
            <div className="mt-3 text-ink-faint"># HMAC request contract</div>
            <div className="text-ink-dim">X-Lumine-Signature: hmac_sha256(…)</div>
            <div className="text-ink-dim">X-Lumine-Timestamp: ±300s window</div>
            <div className="text-ink-dim">Replay cache: (key, ts, body) unique</div>
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="border-t border-line-soft">
        <div className="mx-auto w-full max-w-6xl px-6 py-24 text-center">
          <h2 className="mx-auto max-w-2xl font-display text-3xl font-medium tracking-[-0.02em] text-ink md:text-4xl">
            Operate with the discipline of an institution.
          </h2>
          <p className="mx-auto mt-4 max-w-lg text-base leading-relaxed text-ink-dim">
            Request access to the Lumine terminal and control center.
          </p>
          <div className="mt-8 flex justify-center">
            <Link to="/login">
              <Button variant="primary" size="lg">
                Sign in to Lumine
              </Button>
            </Link>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-line-soft bg-bg">
        <div className="mx-auto flex w-full max-w-6xl flex-col items-center justify-between gap-4 px-6 py-8 md:flex-row">
          <div className="flex items-center gap-2">
            <div className="flex h-6 w-6 items-center justify-center rounded-chip bg-accent">
              <span className="font-display text-[10px] font-bold text-white">L</span>
            </div>
            <span className="font-display text-xs font-semibold text-ink">LUMINE</span>
            <span className="font-mono text-[10px] text-ink-faint">© 2026</span>
          </div>
          <div className="font-mono text-[10px] uppercase tracking-widest text-ink-faint">
            Institutional AI-native quantitative platform
          </div>
        </div>
      </footer>
    </div>
  );
}
