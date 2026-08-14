import { Link } from "react-router-dom";

/**
 * Lumine Hedge Fund — Public Landing Page
 *
 * Design: Linear-inspired dark system (institutional, not retail)
 * - Deep navy abyss background
 * - Inter Variable typography, IBM Plex Mono for data
 * - Restrained accent (#4d8dff), emerald positive, crimson risk
 * - No generic SaaS patterns, no glassmorphism decoration
 */

const FEATURES = [
  {
    icon: "◈",
    title: "AI Investment Committee",
    desc: "Multi-agent consensus driven by GPT-5.5, DeepSeek V4, and Kimi K3. Every decision is auditable.",
  },
  {
    icon: "◎",
    title: "Institutional Risk Engine",
    desc: "Real-time exposure monitoring, drawdown controls, and kill-switch at every tier.",
  },
  {
    icon: "⟐",
    title: "Quantitative Execution",
    desc: "MetaTrader 5 integration with sub-second order routing, slippage tracking, and fill audit.",
  },
  {
    icon: "⊞",
    title: "Research Infrastructure",
    desc: "Backtesting, regime detection, and strategy versioning with full lineage tracing.",
  },
  {
    icon: "⊕",
    title: "Observability Stack",
    desc: "Prometheus metrics, structured logs, and real-time portfolio equity curve streaming.",
  },
  {
    icon: "◉",
    title: "Multi-Portfolio Architecture",
    desc: "Isolated portfolios, capital allocation buckets, and per-strategy performance attribution.",
  },
];

const STATS = [
  { label: "Markets", value: "XAUUSD" },
  { label: "Latency", value: "<50ms" },
  { label: "Audit trail", value: "100%" },
  { label: "Uptime SLO", value: "99.9%" },
];

export function LandingPublicPage() {
  return (
    <div
      className="min-h-screen bg-abyss text-ink"
      style={{ fontFeatureSettings: '"cv01", "ss03"' }}
    >
      {/* Nav */}
      <header className="fixed inset-x-0 top-0 z-50 border-b border-white/5 bg-abyss/80 backdrop-blur-sm">
        <div className="mx-auto flex h-14 max-w-6xl items-center justify-between px-6">
          <div className="flex items-center gap-2.5">
            <div className="flex h-7 w-7 items-center justify-center rounded-[6px] bg-accent/20 ring-1 ring-accent/30">
              <span className="font-display text-xs font-bold text-accent">L</span>
            </div>
            <span className="font-display text-sm font-semibold tracking-tight text-ink">
              LUMINE
            </span>
            <span className="hidden rounded-chip bg-bg-raised px-1.5 py-0.5 font-mono text-[10px] text-text-muted sm:inline">
              HEDGE FUND
            </span>
          </div>

          <nav className="hidden items-center gap-6 text-sm text-text-secondary sm:flex">
            <a href="#platform" className="transition-colors hover:text-ink">Platform</a>
            <a href="#features" className="transition-colors hover:text-ink">Features</a>
            <a href="#tech" className="transition-colors hover:text-ink">Technology</a>
          </nav>

          <div className="flex items-center gap-3">
            <Link
              to="/login"
              className="rounded-chip border border-border-subtle bg-bg-raised px-4 py-1.5 text-sm text-text-secondary transition-colors hover:border-accent/40 hover:text-ink"
            >
              Sign In
            </Link>
          </div>
        </div>
      </header>

      {/* Hero */}
      <section className="relative flex min-h-screen flex-col items-center justify-center overflow-hidden px-6 pt-14">
        {/* Background grid */}
        <div
          className="pointer-events-none absolute inset-0 opacity-[0.03]"
          style={{
            backgroundImage:
              "linear-gradient(rgba(77,141,255,0.5) 1px, transparent 1px), linear-gradient(90deg, rgba(77,141,255,0.5) 1px, transparent 1px)",
            backgroundSize: "80px 80px",
          }}
        />
        {/* Radial glow */}
        <div className="pointer-events-none absolute inset-0 flex items-center justify-center">
          <div
            className="h-[600px] w-[600px] rounded-full opacity-10"
            style={{
              background:
                "radial-gradient(circle, rgba(77,141,255,0.4) 0%, transparent 70%)",
            }}
          />
        </div>

        <div className="relative mx-auto max-w-4xl space-y-6 text-center">
          <div className="inline-flex items-center gap-2 rounded-full border border-accent/20 bg-accent/5 px-3 py-1">
            <span className="h-1.5 w-1.5 rounded-full bg-up" />
            <span className="font-mono text-[11px] uppercase tracking-widest text-text-secondary">
              AI-Native Quantitative Platform
            </span>
          </div>

          <h1
            className="font-display text-5xl font-semibold leading-none tracking-tight text-ink md:text-6xl lg:text-7xl"
            style={{ letterSpacing: "-0.04em" }}
          >
            Institutional-grade
            <br />
            <span className="text-accent">algorithmic trading</span>
            <br />
            infrastructure
          </h1>

          <p className="mx-auto max-w-2xl text-lg leading-relaxed text-text-secondary">
            Lumine combines multi-agent AI, quantitative research, and institutional
            risk controls into a single platform. Built for systematic strategies,
            not retail speculation.
          </p>

          {/* Stats */}
          <div className="flex flex-wrap items-center justify-center gap-8 pt-4">
            {STATS.map((s) => (
              <div key={s.label} className="text-center">
                <div className="font-mono text-2xl font-semibold tabular-nums text-ink">
                  {s.value}
                </div>
                <div className="font-mono text-[11px] uppercase tracking-wider text-text-muted">
                  {s.label}
                </div>
              </div>
            ))}
          </div>

          <div className="flex flex-wrap items-center justify-center gap-3 pt-2">
            <Link
              to="/login"
              className="rounded-chip bg-accent px-6 py-2.5 font-medium text-white transition-opacity hover:opacity-90"
            >
              Access Platform →
            </Link>
            <a
              href="#features"
              className="rounded-chip border border-border-subtle px-6 py-2.5 font-medium text-text-secondary transition-colors hover:border-accent/40 hover:text-ink"
            >
              Learn more
            </a>
          </div>
        </div>

        {/* Scroll indicator */}
        <div className="absolute bottom-8 flex flex-col items-center gap-2">
          <div className="h-8 w-px bg-gradient-to-b from-transparent to-border-subtle" />
          <span className="font-mono text-[10px] uppercase tracking-widest text-text-muted">scroll</span>
        </div>
      </section>

      {/* Platform overview */}
      <section id="platform" className="border-t border-border-subtle px-6 py-24">
        <div className="mx-auto max-w-6xl">
          <div className="mb-12 flex items-center gap-4">
            <span className="font-mono text-[11px] uppercase tracking-widest text-accent">
              Platform
            </span>
            <div className="h-px flex-1 bg-border-subtle/40" />
          </div>
          <div className="grid grid-cols-1 gap-8 md:grid-cols-2">
            <div className="space-y-4">
              <h2
                className="font-display text-3xl font-semibold tracking-tight text-ink"
                style={{ letterSpacing: "-0.02em" }}
              >
                Built like a real hedge fund,
                not a retail trading app
              </h2>
              <p className="text-text-secondary">
                Lumine implements the full institutional workflow: data collection, feature
                engineering, AI committee consensus, risk committee review, execution
                control, journal, and learning loops — each as an independent, auditable
                agent.
              </p>
              <p className="text-text-secondary">
                Every trade decision carries a complete evidence chain from raw signal to
                fill receipt. No black boxes. Full replayability.
              </p>
            </div>
            <div className="rounded-panel border border-border-subtle bg-bg-raised p-6 font-mono text-sm">
              <div className="mb-3 font-mono text-[10px] uppercase tracking-widest text-text-muted">
                Agent Hierarchy
              </div>
              {[
                { depth: 0, label: "CEO" },
                { depth: 1, label: "Chief Investment Officer" },
                { depth: 2, label: "Investment Committee" },
                { depth: 3, label: "Technical Analyst" },
                { depth: 3, label: "Macro Analyst" },
                { depth: 3, label: "News Analyst" },
                { depth: 3, label: "SMC Analyst" },
                { depth: 2, label: "Risk Officer" },
                { depth: 2, label: "Portfolio Manager" },
                { depth: 3, label: "Execution Controller" },
              ].map((item, i) => (
                <div
                  key={i}
                  className="flex items-center gap-2 py-0.5 text-xs"
                  style={{ paddingLeft: item.depth * 16 }}
                >
                  <span className="text-accent/50">{item.depth > 0 ? "└" : ""}</span>
                  <span className={item.depth === 0 ? "text-ink" : "text-text-secondary"}>
                    {item.label}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* Features */}
      <section id="features" className="border-t border-border-subtle px-6 py-24">
        <div className="mx-auto max-w-6xl">
          <div className="mb-12 flex items-center gap-4">
            <span className="font-mono text-[11px] uppercase tracking-widest text-accent">
              Capabilities
            </span>
            <div className="h-px flex-1 bg-border-subtle/40" />
          </div>
          <div className="grid grid-cols-1 gap-6 md:grid-cols-2 lg:grid-cols-3">
            {FEATURES.map((f) => (
              <div
                key={f.title}
                className="rounded-panel border border-border-subtle bg-bg-raised p-6 transition-colors hover:border-accent/20"
              >
                <div className="mb-3 font-mono text-xl text-accent">{f.icon}</div>
                <h3 className="mb-2 font-semibold text-ink">{f.title}</h3>
                <p className="text-sm leading-relaxed text-text-secondary">{f.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Technology */}
      <section id="tech" className="border-t border-border-subtle px-6 py-24">
        <div className="mx-auto max-w-6xl">
          <div className="mb-12 flex items-center gap-4">
            <span className="font-mono text-[11px] uppercase tracking-widest text-accent">
              Technology Stack
            </span>
            <div className="h-px flex-1 bg-border-subtle/40" />
          </div>
          <div className="grid grid-cols-2 gap-4 md:grid-cols-3 lg:grid-cols-5">
            {[
              { category: "LLM", items: ["GPT-5.5", "DeepSeek V4", "Kimi K3"] },
              { category: "Backend", items: ["FastAPI", "Python 3.12", "AutoGen"] },
              { category: "Data", items: ["PostgreSQL", "Redis", "TimescaleDB"] },
              { category: "Trading", items: ["MetaTrader 5", "EA Bridge"] },
              { category: "Frontend", items: ["React", "Vite", "TanStack"] },
            ].map((g) => (
              <div key={g.category} className="space-y-2">
                <div className="font-mono text-[11px] uppercase tracking-widest text-accent">
                  {g.category}
                </div>
                {g.items.map((item) => (
                  <div key={item} className="text-sm text-text-secondary">
                    {item}
                  </div>
                ))}
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="border-t border-border-subtle px-6 py-24">
        <div className="mx-auto max-w-2xl space-y-6 text-center">
          <h2
            className="font-display text-3xl font-semibold tracking-tight text-ink"
            style={{ letterSpacing: "-0.02em" }}
          >
            Ready to trade systematically?
          </h2>
          <p className="text-text-secondary">
            Lumine is a private platform. Access requires authorization.
            Contact your administrator to request access.
          </p>
          <Link
            to="/login"
            className="inline-flex items-center gap-2 rounded-chip bg-accent px-8 py-3 font-medium text-white transition-opacity hover:opacity-90"
          >
            Sign In to Platform →
          </Link>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-border-subtle px-6 py-8">
        <div className="mx-auto flex max-w-6xl items-center justify-between text-xs text-text-muted">
          <div className="flex items-center gap-2">
            <span className="font-display font-semibold text-text-secondary">LUMINE</span>
            <span>·</span>
            <span>Institutional Hedge Fund Platform</span>
          </div>
          <span className="font-mono">lumine.biz.id</span>
        </div>
      </footer>
    </div>
  );
}
