import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { motion, useScroll, useMotionValueEvent } from "framer-motion";
import { useState, type ReactNode } from "react";

// Landing components
import { IntelligenceField } from "@/components/landing/intelligence-field";
import { AgentNetwork } from "@/components/landing/agent-network";
import { MasterDecision } from "@/components/landing/master-decision";
import { AnimatedRiskValidation } from "@/components/landing/animated-risk-validation";
import { RiskEngine } from "@/components/landing/risk-engine";
import { BreakEvenVisualization } from "@/components/landing/breakeven-visualization";
import { ResearchPipeline } from "@/components/landing/research-pipeline";
import { PerformanceDashboard } from "@/components/landing/performance-dashboard";
import { EquityCurve } from "@/components/landing/equity-curve";
import { RegimeEngine } from "@/components/landing/regime-engine";
import { AuditLog } from "@/components/landing/audit-log";
import { PhilosophySection } from "@/components/landing/philosophy-section";
import { RoadmapSection } from "@/components/landing/roadmap-section";
import { TickerTape } from "@/components/landing/ticker-tape";
import { LumineIcon } from "@/components/landing/agent-icons";

/**
 * Lumine Landing Page — UI/UX Rebuild V2 (from scratch).
 *
 * Art direction: "A living quantitative intelligence instrument."
 * Bloomberg Terminal × Quant Research Lab × AI Infrastructure × Premium Fintech.
 *
 * Visual rhythm (dense → sparse → editorial → technical → quiet):
 *   HERO [dense split] → INTELLIGENCE [visual] → MASTER [dense data]
 *   → RISK [technical] → BREAKEVEN [interactive] → RESEARCH [editorial]
 *   → VALIDATION [technical] → PERFORMANCE [data-dense] → REGIME [visual]
 *   → AUDIT [terminal] → ARCHITECTURE [map] → PHILOSOPHY [minimal]
 *   → ROADMAP [timeline] → CTA [quiet] → FOOTER
 */

/* ------------------------------------------------------------------ */
/* Navigation — compact technical bar with system status (Section 12)  */
/* ------------------------------------------------------------------ */

const NAV_LINKS = [
  { href: "#intelligence", label: "Intelligence" },
  { href: "#risk", label: "Risk" },
  { href: "#research", label: "Research" },
  { href: "#performance", label: "Performance" },
];

function NavBar() {
  const { scrollY } = useScroll();
  const [scrolled, setScrolled] = useState(false);

  useMotionValueEvent(scrollY, "change", (v) => setScrolled(v > 40));

  return (
    <header
      className={`fixed inset-x-0 top-0 z-50 transition-all duration-300 ${
        scrolled
          ? "border-b border-line bg-abyss/90 backdrop-blur-md"
          : "border-b border-transparent bg-transparent"
      }`}
    >
      <div
        className={`mx-auto flex w-full max-w-7xl items-center justify-between px-6 transition-all duration-300 ${
          scrolled ? "h-12" : "h-16"
        }`}
      >
        {/* Logo */}
        <Link to="/" className="flex items-center gap-2.5">
          <LumineIcon className="h-6 w-6 text-accent" />
          <span className="font-display text-sm font-bold tracking-[0.2em] text-ink">
            LUMINE
          </span>
        </Link>

        {/* Technical nav */}
        <nav className="hidden items-center gap-7 md:flex">
          {NAV_LINKS.map((l) => (
            <a
              key={l.href}
              href={l.href}
              className="font-mono text-[10px] uppercase tracking-[0.22em] text-ink-dim transition-colors hover:text-ink"
            >
              {l.label}
            </a>
          ))}
        </nav>

        {/* Status + CTA */}
        <div className="flex items-center gap-4">
          <div className="hidden items-center gap-2 lg:flex">
            <div className="h-1.5 w-1.5 animate-pulse rounded-full bg-up" />
            <span className="font-mono text-[9px] uppercase tracking-[0.2em] text-ink-faint">
              System Online
            </span>
          </div>
          <Link to="/login">
            <Button
              size="sm"
              className="bg-accent font-mono text-[10px] uppercase tracking-[0.2em] text-white hover:bg-accent-soft"
            >
              Enter System
            </Button>
          </Link>
        </div>
      </div>
    </header>
  );
}

/* ------------------------------------------------------------------ */
/* Section header primitive — varied rhythm per section                 */
/* ------------------------------------------------------------------ */

interface SectionHeaderProps {
  kicker: string;
  title: ReactNode;
  description?: string;
  align?: "left" | "center";
  className?: string;
}

function SectionHeader({
  kicker,
  title,
  description,
  align = "left",
  className = "",
}: SectionHeaderProps) {
  const alignCls =
    align === "center" ? "items-center text-center" : "items-start text-left";
  return (
    <motion.div
      className={`flex flex-col gap-4 ${alignCls} ${className}`}
      initial={{ opacity: 0, y: 24 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: "-80px" }}
      transition={{ duration: 0.7, ease: "easeOut" }}
    >
      <div className="flex items-center gap-3">
        <span className="h-px w-8 bg-accent/60" />
        <span className="font-mono text-[10px] uppercase tracking-[0.3em] text-accent">
          {kicker}
        </span>
      </div>
      <h2 className="max-w-3xl font-display text-3xl font-bold leading-[1.15] tracking-tight text-ink md:text-4xl lg:text-5xl">
        {title}
      </h2>
      {description && (
        <p className="max-w-2xl text-base leading-relaxed text-ink-dim md:text-lg">
          {description}
        </p>
      )}
    </motion.div>
  );
}

/* ------------------------------------------------------------------ */
/* HERO — split layout: typography left, intelligence field right      */
/* ------------------------------------------------------------------ */

function Hero() {
  return (
    <section className="relative overflow-hidden border-b border-line bg-abyss">
      {/* Ambient background */}
      <div className="pointer-events-none absolute inset-0">
        <div className="absolute -left-40 top-1/4 h-[480px] w-[480px] rounded-full bg-accent/[0.04] blur-[120px]" />
        <div className="absolute bottom-0 right-0 h-[360px] w-[360px] rounded-full bg-cyan/[0.03] blur-[100px]" />
        <div
          className="absolute inset-0 opacity-[0.05]"
          style={{
            backgroundImage:
              "linear-gradient(var(--color-line) 1px, transparent 1px), linear-gradient(90deg, var(--color-line) 1px, transparent 1px)",
            backgroundSize: "80px 80px",
          }}
        />
      </div>

      <div className="relative mx-auto grid w-full max-w-7xl gap-12 px-6 pb-20 pt-32 md:pt-36 lg:grid-cols-[1.1fr_1fr] lg:items-center lg:gap-8 lg:pb-28">
        {/* Left — editorial typography */}
        <div className="flex flex-col items-start">
          <motion.div
            className="mb-7 inline-flex items-center gap-2.5 rounded-chip border border-line-soft bg-raised/60 px-3.5 py-1.5 backdrop-blur"
            initial={{ opacity: 0, y: -12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6 }}
          >
            <div className="h-1.5 w-1.5 animate-pulse rounded-full bg-up" />
            <span className="font-mono text-[9px] font-semibold uppercase tracking-[0.25em] text-ink">
              Multi-Agent Intelligence System
            </span>
          </motion.div>

          <motion.h1
            className="font-display text-[2.75rem] font-bold leading-[1.05] tracking-tight text-ink sm:text-6xl lg:text-[4.5rem] xl:text-[5rem]"
            initial={{ opacity: 0, y: 28 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.8, delay: 0.15, ease: "easeOut" }}
          >
            AI-Native
            <br />
            <span className="text-ink-dim">Quantitative</span>
            <br />
            <span className="text-accent">Intelligence.</span>
          </motion.h1>

          <motion.p
            className="mt-7 max-w-xl text-base leading-relaxed text-ink-dim md:text-lg"
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.7, delay: 0.35 }}
          >
            A coordinated system of specialized agents that research, evaluate,
            and execute systematic strategies — every decision passing through
            deterministic validation and disciplined risk controls.
          </motion.p>

          <motion.div
            className="mt-9 flex flex-wrap items-center gap-4"
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.7, delay: 0.5 }}
          >
            <a href="#intelligence">
              <Button
                size="lg"
                className="bg-accent font-mono text-[11px] uppercase tracking-[0.22em] text-white hover:bg-accent-soft"
              >
                Explore the System
              </Button>
            </a>
            <a href="#research">
              <Button
                size="lg"
                variant="secondary"
                className="border-line font-mono text-[11px] uppercase tracking-[0.22em] text-ink hover:bg-raised"
              >
                View Research
              </Button>
            </a>
          </motion.div>
        </div>

        {/* Right — interactive intelligence field */}
        <motion.div
          className="flex items-center justify-center"
          initial={{ opacity: 0, scale: 0.94 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 1, delay: 0.45, ease: "easeOut" }}
        >
          <IntelligenceField />
        </motion.div>
      </div>

      {/* Scroll indicator */}
      <motion.div
        className="pointer-events-none absolute bottom-5 left-1/2 hidden -translate-x-1/2 flex-col items-center gap-2 lg:flex"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 1.4 }}
      >
        <motion.span
          className="font-mono text-[9px] uppercase tracking-[0.3em] text-ink-faint"
          animate={{ y: [0, 5, 0] }}
          transition={{ duration: 2, repeat: Number.POSITIVE_INFINITY }}
        >
          Scroll
        </motion.span>
      </motion.div>
    </section>
  );
}

/* ------------------------------------------------------------------ */
/* Magnetic button — CTA follows cursor subtly (Section 28)             */
/* ------------------------------------------------------------------ */

function MagneticButton({ children }: { children: ReactNode }) {
  const [offset, setOffset] = useState({ x: 0, y: 0 });

  return (
    <motion.div
      className="inline-block"
      style={{ x: offset.x, y: offset.y }}
      transition={{ type: "spring", stiffness: 300, damping: 20 }}
      onMouseMove={(e) => {
        const r = e.currentTarget.getBoundingClientRect();
        const dx = (e.clientX - r.left - r.width / 2) * 0.18;
        const dy = (e.clientY - r.top - r.height / 2) * 0.18;
        setOffset({ x: dx, y: dy });
      }}
      onMouseLeave={() => setOffset({ x: 0, y: 0 })}
    >
      {children}
    </motion.div>
  );
}

/* ------------------------------------------------------------------ */
/* PAGE                                                               */
/* ------------------------------------------------------------------ */

export function LandingPublicPage() {
  return (
    <div className="min-h-screen bg-abyss text-ink">
      <NavBar />

      {/* HERO — dense split */}
      <Hero />

      {/* Ticker tape — simulated market strip */}
      <TickerTape />

      {/* INTELLIGENCE — visual network (Section 17-18) */}
      <section id="intelligence" className="border-b border-line bg-bg py-16 md:py-24">
        <div className="mx-auto w-full max-w-7xl px-6">
          <SectionHeader
            kicker="Intelligence Network"
            title={
              <>
                Not one AI.
                <br />
                An intelligence system.
              </>
            }
            description="Four specialized agents evaluate independent dimensions of the market. Their signals converge on Lumine Core, which assembles a single directional thesis."
            className="mb-10"
          />
          <motion.div
            initial={{ opacity: 0, y: 30 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, margin: "-60px" }}
            transition={{ duration: 0.8 }}
          >
            <AgentNetwork className="mx-auto" showHeader={false} />
          </motion.div>
        </div>
      </section>

      {/* DECISION & RISK — satu alur: thesis → validation → approved (S19-20) */}
      <section id="risk" className="border-b border-line bg-raised py-16 md:py-24">
        <div className="mx-auto w-full max-w-7xl px-6">
          <SectionHeader
            kicker="Decision & Risk"
            align="center"
            title={
              <>
                Intelligence proposes.
                <br />
                <span className="text-ink-dim">Risk decides.</span>
              </>
            }
            description="Agent signals converge into one thesis. The thesis passes through deterministic validation gates before execution is approved."
            className="mb-10"
          />
          <MasterDecision className="mx-auto" showHeader={false} variant="compact" />
          <div className="mt-16">
            <AnimatedRiskValidation />
          </div>
          <div className="mt-14">
            <RiskEngine showHeader={false} variant="compact" />
          </div>
        </div>
      </section>

      {/* BREAKEVEN — interactive (Section 21) */}
      <section className="border-b border-line bg-bg py-16 md:py-24">
        <div className="mx-auto w-full max-w-7xl px-6">
          <SectionHeader
            kicker="Structure-Based Breakeven"
            title="Break-even is a decision, not a price."
            description="Lumine evaluates whether to hold or move stop-loss to break-even based on market structure and momentum — not arbitrary price levels."
            className="mb-10"
          />
          <BreakEvenVisualization showHeader={false} />
        </div>
      </section>

      {/* RESEARCH — editorial (Section 22) */}
      <section id="research" className="border-b border-line bg-raised py-16 md:py-24">
        <div className="mx-auto w-full max-w-7xl px-6">
          <SectionHeader
            kicker="Research Pipeline"
            title="From observation to deployment."
            description="Every strategy moves through a disciplined lifecycle. Nothing reaches execution without out-of-sample validation."
            className="mb-10"
          />
          <ResearchPipeline showHeader={false} />
        </div>
      </section>

      {/* PERFORMANCE — data-dense (Section 23) */}
      <section id="performance" className="border-b border-line bg-bg py-16 md:py-24">
        <div className="mx-auto w-full max-w-7xl px-6">
          <SectionHeader
            kicker="Performance"
            align="center"
            title="An analytics laboratory, not a scoreboard."
            description="Illustrative data showing how Lumine evaluates strategy quality across backtest, paper, and live phases."
            className="mb-10"
          />
          <PerformanceDashboard showHeader={false} />
          <div className="mt-16">
            <EquityCurve showHeader={false} />
          </div>
        </div>
      </section>

      {/* REGIME — full-width visual (Section 24) */}
      <section className="border-b border-line bg-raised py-16 md:py-24">
        <div className="mx-auto w-full max-w-7xl px-6">
          <SectionHeader
            kicker="Market Regime"
            title="The system adapts to the market's current state."
            description="Regime detection shapes strategy selection and risk posture. Hover each regime to inspect how Lumine responds."
            className="mb-10"
          />
          <RegimeEngine showHeader={false} />
        </div>
      </section>

      {/* AUDIT — terminal-style stream (Section 25) */}
      <section className="border-b border-line bg-abyss py-16 md:py-24">
        <div className="mx-auto w-full max-w-7xl px-6">
          <SectionHeader
            kicker="Audit Trail"
            title="Every decision, logged."
            description="A complete, inspectable record of how each thesis was assembled, validated, and executed. Pause the stream to read it."
            className="mb-10"
          />
          <AuditLog showHeader={false} />
        </div>
      </section>

      {/* PHILOSOPHY — minimal editorial (Section 41) */}
      <section className="border-b border-line bg-abyss py-16 md:py-24">
        <PhilosophySection />
      </section>

      {/* ROADMAP — timeline (Section 42) */}
      <section id="roadmap" className="border-b border-line bg-bg py-16 md:py-24">
        <div className="mx-auto w-full max-w-7xl px-6">
          <SectionHeader
            kicker="Roadmap"
            align="center"
            title="Built in phases. Verified at every step."
            className="mb-10"
          />
          <RoadmapSection showHeader={false} />
        </div>
      </section>

      {/* CTA — quiet (Section 42) */}
      <section className="border-b border-line bg-raised py-16 md:py-24">
        <div className="mx-auto w-full max-w-4xl px-6">
          <motion.div
            className="flex flex-col items-center gap-8 text-center"
            initial={{ opacity: 0, y: 24 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, margin: "-80px" }}
            transition={{ duration: 0.8 }}
          >
            <div className="flex flex-col items-center gap-2">
              <LumineIcon className="h-10 w-10 text-accent" />
              <span className="font-mono text-[10px] uppercase tracking-[0.3em] text-ink-faint">
                Research Environment
              </span>
            </div>
            <h2 className="font-display text-3xl font-bold tracking-tight text-ink md:text-5xl">
              Explore the system.
            </h2>
            <p className="max-w-xl text-base leading-relaxed text-ink-dim">
              See how specialized agents form a thesis, how risk governs every
              decision, and how validation keeps the pipeline honest.
            </p>
            {/* Magnetic CTA */}
            <MagneticButton>
              <Link to="/login">
                <Button
                  size="lg"
                  className="group bg-accent font-mono text-[11px] uppercase tracking-[0.22em] text-white hover:bg-accent-soft"
                >
                  Enter the System
                  <span className="ml-2 inline-block transition-transform duration-300 group-hover:translate-x-1">
                    →
                  </span>
                </Button>
              </Link>
            </MagneticButton>
          </motion.div>
        </div>
      </section>

      {/* FOOTER */}
      <footer className="border-t border-line bg-abyss">
        <div className="mx-auto w-full max-w-7xl px-6 py-14">
          <div className="grid gap-12 md:grid-cols-4">
            {/* Brand */}
            <div className="space-y-4 md:col-span-2">
              <div className="flex items-center gap-2.5">
                <LumineIcon className="h-6 w-6 text-accent" />
                <span className="font-display text-sm font-bold tracking-[0.2em] text-ink">
                  LUMINE
                </span>
              </div>
              <p className="max-w-sm text-sm leading-relaxed text-ink-dim">
                AI-native quantitative intelligence. A coordinated system of
                specialized agents under disciplined risk controls.
              </p>
              <div className="font-mono text-[10px] uppercase tracking-[0.2em] text-ink-faint">
                © 2026 Lumine — Institutional AI-native platform
              </div>
            </div>

            {/* Platform */}
            <div className="space-y-3">
              <div className="font-mono text-[10px] font-semibold uppercase tracking-[0.25em] text-ink-faint">
                Platform
              </div>
              <nav className="flex flex-col gap-2">
                <a href="#intelligence" className="text-sm text-ink-dim transition-colors hover:text-ink">
                  Intelligence
                </a>
                <a href="#risk" className="text-sm text-ink-dim transition-colors hover:text-ink">
                  Risk Engine
                </a>
                <a href="#research" className="text-sm text-ink-dim transition-colors hover:text-ink">
                  Research Pipeline
                </a>
              </nav>
            </div>

            {/* Connect */}
            <div className="space-y-3">
              <div className="font-mono text-[10px] font-semibold uppercase tracking-[0.25em] text-ink-faint">
                Connect
              </div>
              <nav className="flex flex-col gap-2">
                <Link to="/login" className="text-sm text-ink-dim transition-colors hover:text-ink">
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

          {/* Disclaimer */}
          <div className="mt-12 rounded-panel border border-warn/25 bg-warn/5 p-4">
            <p className="text-xs leading-relaxed text-ink-dim">
              <span className="font-semibold text-warn">Disclaimer:</span>{" "}
              Lumine is a technology and quantitative research platform. Nothing
              on this website constitutes financial advice or a guarantee of
              investment performance. Historical, simulated, and backtested
              results do not guarantee future results. All trading involves
              risk. All data shown on this page is illustrative and simulated.
            </p>
          </div>
        </div>
      </footer>
    </div>
  );
}
