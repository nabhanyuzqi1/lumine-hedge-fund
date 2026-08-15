import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";

// Landing page components
import { SystemTelemetry } from "@/components/landing/system-telemetry";
import { AgentNetwork } from "@/components/landing/agent-network";
import { MasterDecision } from "@/components/landing/master-decision";
import { RiskEngine } from "@/components/landing/risk-engine";
import { BreakEvenVisualization } from "@/components/landing/breakeven-visualization";
import { ResearchPipeline } from "@/components/landing/research-pipeline";
import { ValidationPipeline } from "@/components/landing/validation-pipeline";
import { PerformanceDashboard } from "@/components/landing/performance-dashboard";
import { EquityCurve } from "@/components/landing/equity-curve";
import { RegimeEngine } from "@/components/landing/regime-engine";
import { AuditLog } from "@/components/landing/audit-log";
import { ArchitectureDiagram } from "@/components/landing/architecture-diagram";
import { PhilosophySection } from "@/components/landing/philosophy-section";
import { RoadmapSection } from "@/components/landing/roadmap-section";

/**
 * Lumine Landing Page — AI-Native Quantitative Intelligence
 * 
 * Complete rebuild following 39-section master prompt.
 * Design philosophy: Bloomberg Terminal × Quant Research Lab × 
 * Institutional Trading Infrastructure × Modern AI Laboratory
 * 
 * NOT a trading bot landing page. This is a serious quantitative
 * intelligence system with institutional-grade risk controls.
 */

function NavBar() {
  return (
    <header className="sticky top-0 z-50 border-b border-line-soft bg-abyss/80 backdrop-blur">
      <div className="mx-auto flex h-14 w-full max-w-7xl items-center justify-between px-6">
        {/* Logo */}
        <Link to="/" className="flex items-center gap-2">
          <div className="flex h-7 w-7 items-center justify-center rounded-chip bg-accent">
            <span className="font-display text-xs font-bold text-white">L</span>
          </div>
          <span className="font-display text-sm font-semibold tracking-tight text-ink">
            LUMINE
          </span>
        </Link>

        {/* Nav links */}
        <nav className="hidden items-center gap-6 md:flex">
          <a
            href="#intelligence"
            className="font-mono text-[11px] uppercase tracking-widest text-ink-dim transition-colors hover:text-ink"
          >
            Intelligence
          </a>
          <a
            href="#risk"
            className="font-mono text-[11px] uppercase tracking-widest text-ink-dim transition-colors hover:text-ink"
          >
            Risk
          </a>
          <a
            href="#research"
            className="font-mono text-[11px] uppercase tracking-widest text-ink-dim transition-colors hover:text-ink"
          >
            Research
          </a>
          <a
            href="#roadmap"
            className="font-mono text-[11px] uppercase tracking-widest text-ink-dim transition-colors hover:text-ink"
          >
            Roadmap
          </a>
        </nav>

        {/* CTA */}
        <Link to="/login">
          <Button
            size="sm"
            className="hidden bg-accent font-mono text-[11px] uppercase tracking-widest text-white hover:bg-accent-soft md:inline-flex"
          >
            System Access
          </Button>
        </Link>
      </div>
    </header>
  );
}

function Hero() {
  return (
    <section className="relative min-h-[80vh] overflow-hidden border-b border-line bg-abyss">
      {/* System telemetry overlay */}
      <SystemTelemetry />

      {/* Hero content */}
      <div className="relative mx-auto flex min-h-[80vh] w-full max-w-7xl flex-col items-center justify-center px-6 py-20 text-center">
        {/* System status badge */}
        <div className="mb-8 inline-flex items-center gap-2 rounded-chip border border-line-soft bg-raised/50 px-4 py-2 backdrop-blur">
          <div className="h-2 w-2 animate-pulse rounded-full bg-up" />
          <span className="font-mono text-[10px] font-semibold uppercase tracking-widest text-ink">
            Lumine Intelligence System — Online
          </span>
        </div>

        {/* Main headline */}
        <h1 className="mb-6 font-display text-4xl font-bold leading-tight text-ink md:text-6xl lg:text-7xl">
          AI-Native
          <br />
          Quantitative Intelligence.
        </h1>

        {/* Supporting text */}
        <p className="mb-10 max-w-2xl text-base leading-relaxed text-ink-dim md:text-lg">
          A multi-agent intelligence system engineered to research, evaluate,
          and execute systematic trading strategies under disciplined risk
          controls.
        </p>

        {/* CTAs */}
        <div className="flex flex-wrap items-center justify-center gap-4">
          <a href="#intelligence">
            <Button
              size="lg"
              className="bg-accent font-mono text-xs uppercase tracking-widest text-white hover:bg-accent-soft"
            >
              Explore the System
            </Button>
          </a>
          <a href="#research">
            <Button
              size="lg"
              variant="secondary"
              className="border-line font-mono text-xs uppercase tracking-widest text-ink hover:border-accent hover:bg-accent/10"
            >
              View Research
            </Button>
          </a>
        </div>

        {/* Small telemetry */}
        <div className="mt-16 grid grid-cols-3 gap-8 border-t border-line-soft pt-8 font-mono text-xs">
          <div className="space-y-1">
            <div className="text-[10px] uppercase tracking-widest text-ink-faint">
              Markets
            </div>
            <div className="font-semibold text-ink">XAUUSD · FX · EQUITIES</div>
          </div>
          <div className="space-y-1">
            <div className="text-[10px] uppercase tracking-widest text-ink-faint">
              Mode
            </div>
            <div className="font-semibold text-accent">RESEARCH / PAPER</div>
          </div>
          <div className="space-y-1">
            <div className="text-[10px] uppercase tracking-widest text-ink-faint">
              Engine
            </div>
            <div className="font-semibold text-ink">Multi-Agent</div>
          </div>
        </div>
      </div>
    </section>
  );
}

export function LandingPublicPage() {
  return (
    <div className="min-h-screen bg-abyss">
      <NavBar />

      {/* Hero */}
      <Hero />

      {/* Section 8: Not One AI — Multi-Agent System */}
      <section
        id="intelligence"
        className="border-b border-line bg-bg py-20 md:py-32"
      >
        <div className="mx-auto w-full max-w-7xl space-y-12 px-6">
          <div className="space-y-4 text-center">
            <h2 className="font-display text-3xl font-bold text-ink md:text-5xl">
              Not One AI.
              <br />
              An Intelligence System.
            </h2>
            <p className="mx-auto max-w-3xl text-base leading-relaxed text-ink-dim md:text-lg">
              Lumine combines specialized agents into a coordinated quantitative
              research and decision-making architecture. Each agent evaluates a
              different dimension of the market before decisions pass through
              deterministic validation and risk controls.
            </p>
          </div>

          {/* Agent network visualization */}
          <AgentNetwork className="mx-auto" />
        </div>
      </section>

      {/* Section 9: Master Decision */}
      <section className="border-b border-line bg-raised py-20 md:py-32">
        <div className="mx-auto flex w-full max-w-7xl justify-center px-6">
          <MasterDecision />
        </div>
      </section>

      {/* Section 10: Risk Engine */}
      <section id="risk" className="border-b border-line bg-bg py-20 md:py-32">
        <div className="mx-auto flex w-full max-w-7xl justify-center px-6">
          <RiskEngine />
        </div>
      </section>

      {/* Section 11: Break-Even Visualization */}
      <section className="border-b border-line bg-raised py-20 md:py-32">
        <div className="mx-auto flex w-full max-w-7xl justify-center px-6">
          <BreakEvenVisualization />
        </div>
      </section>

      {/* Section 12: Research Pipeline */}
      <section
        id="research"
        className="border-b border-line bg-bg py-20 md:py-32"
      >
        <div className="mx-auto flex w-full max-w-7xl justify-center px-6">
          <ResearchPipeline />
        </div>
      </section>

      {/* Section 13: Validation Pipeline */}
      <section className="border-b border-line bg-raised py-20 md:py-32">
        <div className="mx-auto flex w-full max-w-7xl justify-center px-6">
          <ValidationPipeline />
        </div>
      </section>

      {/* Section 14: Performance Dashboard */}
      <section className="border-b border-line bg-bg py-20 md:py-32">
        <div className="mx-auto flex w-full max-w-7xl justify-center px-6">
          <PerformanceDashboard />
        </div>
      </section>

      {/* Section 15: Equity Curve */}
      <section className="border-b border-line bg-raised py-20 md:py-32">
        <div className="mx-auto flex w-full max-w-7xl justify-center px-6">
          <EquityCurve />
        </div>
      </section>

      {/* Section 16: Market Regime Engine */}
      <section className="border-b border-line bg-bg py-20 md:py-32">
        <div className="mx-auto flex w-full max-w-7xl justify-center px-6">
          <RegimeEngine />
        </div>
      </section>

      {/* Section 17: Auditability */}
      <section className="border-b border-line bg-raised py-20 md:py-32">
        <div className="mx-auto flex w-full max-w-7xl justify-center px-6">
          <AuditLog />
        </div>
      </section>

      {/* Section 18: System Architecture */}
      <section className="border-b border-line bg-bg py-20 md:py-32">
        <div className="mx-auto flex w-full max-w-7xl justify-center px-6">
          <ArchitectureDiagram />
        </div>
      </section>

      {/* Section 20: Philosophy */}
      <section className="border-b border-line bg-abyss py-20 md:py-32">
        <div className="mx-auto flex w-full max-w-7xl justify-center px-6">
          <PhilosophySection />
        </div>
      </section>

      {/* Section 21: Roadmap */}
      <section
        id="roadmap"
        className="border-b border-line bg-bg py-20 md:py-32"
      >
        <div className="mx-auto flex w-full max-w-7xl justify-center px-6">
          <RoadmapSection />
        </div>
      </section>

      {/* Section 22: Final CTA */}
      <section className="border-b border-line bg-raised py-20 md:py-32">
        <div className="mx-auto w-full max-w-4xl space-y-8 px-6 text-center">
          <h2 className="font-display text-3xl font-bold text-ink md:text-5xl">
            Enter the Lumine
            <br />
            Research Environment.
          </h2>
          <p className="mx-auto max-w-2xl text-base leading-relaxed text-ink-dim">
            Explore an AI-native approach to quantitative research, systematic
            decision-making, and disciplined execution.
          </p>
          <div className="flex flex-wrap items-center justify-center gap-4">
            <Link to="/login">
              <Button
                size="lg"
                className="bg-accent font-mono text-xs uppercase tracking-widest text-white hover:bg-accent-soft"
              >
                Explore Lumine
              </Button>
            </Link>
            <a href="#intelligence">
              <Button
                size="lg"
                variant="secondary"
                className="border-line font-mono text-xs uppercase tracking-widest text-ink hover:border-accent hover:bg-accent/10"
              >
                View System
              </Button>
            </a>
          </div>
        </div>
      </section>

      {/* Section 23: Footer */}
      <footer className="border-t border-line-soft bg-abyss">
        <div className="mx-auto w-full max-w-7xl px-6 py-12">
          <div className="grid gap-12 md:grid-cols-3">
            {/* Brand */}
            <div className="space-y-4">
              <div className="flex items-center gap-2">
                <div className="flex h-6 w-6 items-center justify-center rounded-chip bg-accent">
                  <span className="font-display text-[10px] font-bold text-white">
                    L
                  </span>
                </div>
                <span className="font-display text-sm font-semibold text-ink">
                  LUMINE
                </span>
              </div>
              <p className="text-sm leading-relaxed text-ink-dim">
                AI-Native Quantitative Intelligence.
              </p>
            </div>

            {/* Links */}
            <div className="space-y-3">
              <div className="font-mono text-[10px] font-semibold uppercase tracking-widest text-ink-faint">
                Platform
              </div>
              <nav className="flex flex-col gap-2">
                <a
                  href="#intelligence"
                  className="text-sm text-ink-dim transition-colors hover:text-ink"
                >
                  Intelligence System
                </a>
                <a
                  href="#risk"
                  className="text-sm text-ink-dim transition-colors hover:text-ink"
                >
                  Risk Engine
                </a>
                <a
                  href="#research"
                  className="text-sm text-ink-dim transition-colors hover:text-ink"
                >
                  Research Pipeline
                </a>
                <a
                  href="#roadmap"
                  className="text-sm text-ink-dim transition-colors hover:text-ink"
                >
                  Roadmap
                </a>
              </nav>
            </div>

            {/* Contact */}
            <div className="space-y-3">
              <div className="font-mono text-[10px] font-semibold uppercase tracking-widest text-ink-faint">
                Connect
              </div>
              <nav className="flex flex-col gap-2">
                <Link
                  to="/login"
                  className="text-sm text-ink-dim transition-colors hover:text-ink"
                >
                  System Access
                </Link>
                <a
                  href="https://github.com"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-sm text-ink-dim transition-colors hover:text-ink"
                >
                  GitHub
                </a>
              </nav>
            </div>
          </div>

          {/* Footer bottom */}
          <div className="mt-12 space-y-4 border-t border-line-soft pt-8">
            <div className="flex flex-wrap items-center justify-between gap-4">
              <div className="flex items-center gap-2">
                <span className="font-mono text-[10px] text-ink-faint">
                  © 2026 LUMINE
                </span>
                <span className="font-mono text-[10px] uppercase tracking-widest text-ink-faint">
                  Institutional AI-native quantitative platform
                </span>
              </div>
            </div>

            {/* Disclaimer */}
            <div className="rounded-chip border border-warn/30 bg-warn/5 p-4">
              <p className="text-xs leading-relaxed text-ink-dim">
                <span className="font-semibold text-warn">Disclaimer:</span>{" "}
                Lumine is a technology and quantitative research platform.
                Nothing on this website constitutes financial advice or a
                guarantee of investment performance. Historical, simulated, and
                backtested results do not guarantee future results. All trading
                involves risk.
              </p>
            </div>
          </div>
        </div>
      </footer>
    </div>
  );
}
