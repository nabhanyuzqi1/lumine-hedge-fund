import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { motion } from "framer-motion";

// Landing page components
import { InteractiveHeroNetwork } from "@/components/landing/interactive-hero-network";
import { SystemTelemetry } from "@/components/landing/system-telemetry";
import { AgentNetwork } from "@/components/landing/agent-network";
import { MasterDecision } from "@/components/landing/master-decision";
import { RiskEngine } from "@/components/landing/risk-engine";
import { AnimatedRiskValidation } from "@/components/landing/animated-risk-validation";
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
    <section className="relative min-h-screen overflow-hidden border-b border-line bg-abyss">
      {/* System telemetry overlay — repositioned top-right */}
      <div className="absolute right-6 top-20 z-10">
        <SystemTelemetry />
      </div>

      {/* Hero content — asymmetric layout, left-aligned */}
      <div className="relative mx-auto flex min-h-screen w-full max-w-7xl flex-col items-start justify-center px-6 py-32">
        {/* System status badge */}
        <motion.div
          className="mb-8 inline-flex items-center gap-2 rounded-chip border border-line-soft bg-raised/50 px-4 py-2 backdrop-blur"
          initial={{ opacity: 0, y: -10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6 }}
        >
          <div className="h-2 w-2 animate-pulse rounded-full bg-up" />
          <span className="font-mono text-[10px] font-semibold uppercase tracking-widest text-ink">
            Lumine Intelligence System — Online
          </span>
        </motion.div>

        {/* Main headline — asymmetric typography, split alignment */}
        <motion.div
          className="mb-12 max-w-4xl"
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.8, delay: 0.2 }}
        >
          <h1 className="font-display text-5xl font-bold leading-[1.1] tracking-tight text-ink md:text-6xl lg:text-7xl xl:text-8xl">
            AI-Native
            <br />
            <span className="text-ink-dim">Quantitative</span>
            <br />
            Intelligence.
          </h1>
        </motion.div>

        {/* Supporting text */}
        <motion.p
          className="mb-16 max-w-2xl text-base leading-relaxed text-ink-dim md:text-lg"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.8, delay: 0.4 }}
        >
          A multi-agent intelligence system engineered to research, evaluate,
          and execute systematic trading strategies under disciplined risk
          controls.
        </motion.p>

        {/* CTAs */}
        <motion.div
          className="mb-20 flex flex-wrap items-center gap-4"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.8, delay: 0.6 }}
        >
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
              className="border-line font-mono text-xs uppercase tracking-widest text-ink hover:bg-raised"
            >
              View Research
            </Button>
          </a>
        </motion.div>

        {/* Interactive intelligence network */}
        <motion.div
          className="w-full"
          initial={{ opacity: 0, scale: 0.95 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 1, delay: 0.8 }}
        >
          <InteractiveHeroNetwork />
        </motion.div>
      </div>

      {/* Scroll indicator */}
      <motion.div
        className="absolute bottom-8 left-1/2 -translate-x-1/2"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 0.8, delay: 1.2 }}
      >
        <motion.div
          className="flex flex-col items-center gap-2"
          animate={{ y: [0, 8, 0] }}
          transition={{ duration: 2, repeat: Number.POSITIVE_INFINITY, ease: "easeInOut" }}
        >
          <span className="font-mono text-[10px] uppercase tracking-widest text-ink-faint">
            Scroll
          </span>
          <div className="h-6 w-[1px] bg-gradient-to-b from-ink-faint to-transparent" />
        </motion.div>
      </motion.div>
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
        <div className="mx-auto w-full max-w-7xl px-6">
          <div className="mb-16 text-center">
            <h2 className="mb-4 font-display text-3xl font-bold text-ink md:text-4xl lg:text-5xl">
              Intelligence Decides.
              <br />
              <span className="text-ink-dim">Risk Controls Execution.</span>
            </h2>
            <p className="mx-auto max-w-2xl text-base leading-relaxed text-ink-dim md:text-lg">
              AI can propose a trade. It cannot override the system's risk boundaries.
              Every proposal passes through deterministic validation gates.
            </p>
          </div>

          {/* Animated validation sequence */}
          <div className="mb-16">
            <AnimatedRiskValidation />
          </div>

          {/* Original risk engine component */}
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
