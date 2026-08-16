import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { motion, useScroll, useMotionValueEvent } from "framer-motion";
import { useState, lazy, Suspense, type ReactNode } from "react";
import { useTranslation } from "react-i18next";

// Lazy load heavy visualization components
const IntelligenceField = lazy(() => 
  import("@/components/landing/intelligence-field").then(m => ({ default: m.IntelligenceField }))
);
const DecisionFlow = lazy(() => 
  import("@/components/landing/decision-flow").then(m => ({ default: m.DecisionFlow }))
);
const BreakEvenVisualization = lazy(() => 
  import("@/components/landing/breakeven-visualization").then(m => ({ default: m.BreakEvenVisualization }))
);
const ResearchPipeline = lazy(() => 
  import("@/components/landing/research-pipeline").then(m => ({ default: m.ResearchPipeline }))
);
const PerformanceDashboard = lazy(() => 
  import("@/components/landing/performance-dashboard").then(m => ({ default: m.PerformanceDashboard }))
);
const EquityCurve = lazy(() => 
  import("@/components/landing/equity-curve").then(m => ({ default: m.EquityCurve }))
);
const RegimeEngine = lazy(() => 
  import("@/components/landing/regime-engine").then(m => ({ default: m.RegimeEngine }))
);
const AuditLog = lazy(() => 
  import("@/components/landing/audit-log").then(m => ({ default: m.AuditLog }))
);
const PhilosophySection = lazy(() => 
  import("@/components/landing/philosophy-section").then(m => ({ default: m.PhilosophySection }))
);
const TickerTape = lazy(() => 
  import("@/components/landing/ticker-tape").then(m => ({ default: m.TickerTape }))
);

import { LumineIcon } from "@/components/landing/agent-icons";
import { LanguageSwitcher } from "@/components/language-switcher";
import { ChartSkeleton, HeroSkeleton } from "@/components/ui/skeleton";

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

function NavBar() {
  const { t } = useTranslation();
  const { scrollY } = useScroll();
  const [scrolled, setScrolled] = useState(false);

  useMotionValueEvent(scrollY, "change", (v) => setScrolled(v > 40));

  const navLinks = [
    { href: "#", label: t("nav.overview", "Overview") },
    { href: "#risk", label: t("nav.risk", "Risk") },
    { href: "#research", label: t("nav.research", "Research") },
    { href: "#performance", label: t("nav.performance", "Performance") },
  ];

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
          {navLinks.map((l) => (
            <a
              key={l.href}
              href={l.href}
              className="font-mono text-[10px] uppercase tracking-[0.22em] text-ink-dim transition-colors hover:text-ink"
            >
              {l.label}
            </a>
          ))}
        </nav>

        {/* Status + Language + Theme + GitHub + CTA */}
        <div className="flex items-center gap-3">
          <div className="hidden items-center gap-2 lg:flex">
            <div className="h-1.5 w-1.5 animate-pulse rounded-full bg-up" />
            <span className="font-mono text-[9px] uppercase tracking-[0.2em] text-ink-faint">
              System Online
            </span>
          </div>
          
          {/* Language Switcher */}
          <LanguageSwitcher />
          
          <a
            href="https://github.com/nabhanyuzqi1/lumine-hedge-fund"
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-2 rounded-chip border border-line-soft bg-raised/50 px-2.5 py-1.5 text-ink-dim transition-colors hover:border-line hover:text-ink"
            aria-label="Lumine on GitHub"
          >
            <GitHubIcon size={14} />
            <span className="hidden font-mono text-[9px] uppercase tracking-[0.18em] sm:inline">
              GitHub
            </span>
          </a>
          <Link to="/login">
            <Button
              size="sm"
              className="bg-accent font-mono text-[10px] uppercase tracking-[0.2em] text-white hover:bg-accent-soft"
            >
              {t("hero.loginButton")}
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
  const { t } = useTranslation();
  
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
            {t('hero.title')}
            <br />
            <span className="text-ink-dim">{t('hero.titleQuantitative')}</span>
            <br />
            <span className="text-accent">{t('hero.titleIntelligence')}</span>
          </motion.h1>

          <motion.p
            className="mt-7 max-w-xl text-base leading-relaxed text-ink-dim md:text-lg"
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.7, delay: 0.35 }}
          >
            {t('hero.subtitle')}
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
                {t('hero.ctaExplore')}
              </Button>
            </a>
            <a href="#research">
              <Button
                size="lg"
                variant="secondary"
                className="border-line font-mono text-[11px] uppercase tracking-[0.22em] text-ink hover:bg-raised"
              >
                {t('hero.ctaResearch')}
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
          <Suspense fallback={<HeroSkeleton />}>
            <IntelligenceField />
          </Suspense>
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
          {t('hero.scroll')}
        </motion.span>
      </motion.div>
    </section>
  );
}

/* ------------------------------------------------------------------ */
/* GitHub icon — open-source badge (octocat mark)                      */
/* ------------------------------------------------------------------ */

function GitHubIcon({ size = 16 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
      <path d="M12 0C5.37 0 0 5.37 0 12c0 5.3 3.438 9.8 8.205 11.387.6.113.82-.258.82-.577 0-.285-.01-1.04-.015-2.04-3.338.724-4.042-1.61-4.042-1.61-.546-1.387-1.333-1.756-1.333-1.756-1.09-.745.082-.73.082-.73 1.205.085 1.838 1.236 1.838 1.236 1.07 1.835 2.809 1.305 3.495.998.108-.776.417-1.305.76-1.605-2.665-.3-5.466-1.332-5.466-5.93 0-1.31.465-2.38 1.235-3.22-.135-.303-.54-1.523.105-3.176 0 0 1.005-.322 3.3 1.23.96-.267 1.98-.399 3-.405 1.02.006 2.04.138 3 .405 2.28-1.552 3.285-1.23 3.285-1.23.645 1.653.24 2.873.12 3.176.765.84 1.23 1.91 1.23 3.22 0 4.61-2.805 5.625-5.475 5.92.42.36.81 1.096.81 2.22 0 1.606-.015 2.896-.015 3.286 0 .315.21.69.825.57C20.565 21.795 24 17.295 24 12c0-6.63-5.37-12-12-12" />
    </svg>
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
  const { t } = useTranslation();
  
  return (
    <div className="min-h-screen bg-abyss text-ink">
      <NavBar />

      {/* HERO — dense split */}
      <Hero />

      {/* Ticker tape — simulated market strip */}
      <Suspense fallback={<ChartSkeleton />}>
            <TickerTape />
          </Suspense>

      {/* DECISION & RISK — 3-step flow: signals → thesis → risk gates */}
            <section id="risk" className="border-b border-line bg-raised py-16 md:py-24">
              <div className="mx-auto w-full max-w-7xl px-6">
                <SectionHeader
                  kicker={t('decision.sectionKicker')}
                  align="center"
                  title={
                    <>
                      {t('decision.titleFirst')}
                      <br />
                      <span className="text-ink-dim">{t('decision.titleSecond')}</span>
                    </>
                  }
                  description={t('decision.description')}
                  className="mb-10"
                />
                <Suspense fallback={<ChartSkeleton />}>
                  <DecisionFlow className="mx-auto" />
                </Suspense>
              </div>
            </section>

                  {/* BREAKEVEN — interactive (Section 21) */}
                  <section className="border-b border-line bg-bg py-16 md:py-24">
                    <div className="mx-auto w-full max-w-7xl px-6">
                      <SectionHeader
                        kicker={t('breakeven.sectionKicker')}
                        title={t('breakeven.sectionTitle')}
                        description={t('breakeven.description')}
                        className="mb-10"
                      />
                      <Suspense fallback={<ChartSkeleton />}>
                        <BreakEvenVisualization showHeader={false} />
                      </Suspense>
                    </div>
                  </section>

                  {/* RESEARCH — strategy lifecycle (Section 22) */}
                  <section id="research" className="border-b border-line bg-raised py-16 md:py-24">
                    <div className="mx-auto w-full max-w-7xl px-6">
                      <SectionHeader
                        kicker={t('research.sectionKicker')}
                        title={t('research.sectionTitle')}
                        description={t('research.description')}
                        className="mb-10"
                      />
                      <Suspense fallback={<ChartSkeleton />}>
                        <ResearchPipeline showHeader={false} />
                      </Suspense>
                    </div>
                  </section>

                  {/* PERFORMANCE — data-dense (Section 23) */}
                  <section id="performance" className="border-b border-line bg-bg py-16 md:py-24">
                    <div className="mx-auto w-full max-w-7xl px-6">
                      <SectionHeader
                        kicker={t('performance.sectionKicker')}
                        align="center"
                        title={t('performance.sectionTitle')}
                        description={t('performance.description')}
                        className="mb-10"
                      />
                      <Suspense fallback={<ChartSkeleton />}>
                        <PerformanceDashboard showHeader={false} />
                      </Suspense>
                      <div className="mt-16">
                        <Suspense fallback={<ChartSkeleton />}>
                          <EquityCurve showHeader={false} />
                        </Suspense>
                      </div>
                    </div>
                  </section>

                  {/* REGIME — full-width visual (Section 24) */}
                  <section className="border-b border-line bg-raised py-16 md:py-24">
                    <div className="mx-auto w-full max-w-7xl px-6">
                      <SectionHeader
                        kicker={t('regime.sectionKicker')}
                        title={t('regime.sectionTitle')}
                        description={t('regime.description')}
                        className="mb-10"
                      />
                      <Suspense fallback={<ChartSkeleton />}>
                        <RegimeEngine showHeader={false} />
                      </Suspense>
                    </div>
                  </section>

                  {/* AUDIT — terminal-style stream (Section 25) */}
                  <section className="border-b border-line bg-abyss py-16 md:py-24">
                    <div className="mx-auto w-full max-w-7xl px-6">
                      <SectionHeader
                        kicker={t('audit.sectionKicker')}
                        title={t('audit.sectionTitle')}
                        description={t('audit.description')}
                        className="mb-10"
                      />
                      <Suspense fallback={<ChartSkeleton />}>
                        <AuditLog showHeader={false} />
                      </Suspense>
                    </div>
                  </section>

      {/* PHILOSOPHY — minimal editorial (Section 41) */}
      <section className="border-b border-line bg-abyss py-16 md:py-24">
        <Suspense fallback={<ChartSkeleton />}>
          <PhilosophySection />
        </Suspense>
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
                {t('cta.label')}
              </span>
            </div>
            <h2 className="font-display text-3xl font-bold tracking-tight text-ink md:text-5xl">
              {t('cta.title')}
            </h2>
            <p className="max-w-xl text-base leading-relaxed text-ink-dim">
              {t('cta.description')}
            </p>
            {/* Magnetic CTA */}
            <MagneticButton>
              <Link to="/login">
                <Button
                  size="lg"
                  className="group bg-accent font-mono text-[11px] uppercase tracking-[0.22em] text-white hover:bg-accent-soft"
                >
                  {t('cta.button')}
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
                <a href="#" className="text-sm text-ink-dim transition-colors hover:text-ink">
                  System Overview
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
                  href="https://github.com/nabhanyuzqi1/lumine-hedge-fund"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-center gap-2 text-sm text-ink-dim transition-colors hover:text-ink"
                >
                  <GitHubIcon size={14} />
                  GitHub — Open Source
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
