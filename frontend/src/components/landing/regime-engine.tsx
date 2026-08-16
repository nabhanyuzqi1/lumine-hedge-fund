import { motion } from "framer-motion";
import { useState } from "react";
import { cn } from "@/lib/utils";
import { useTranslation } from "react-i18next";
import { MARKET_REGIME } from "@/data/landing/performance";

/**
 * RegimeEngine — Section 24 of UI/UX Rebuild V2.
 * Full-width regime visualization. Bars animate in on scroll.
 * Hover a regime to inspect how Lumine responds (preferred behavior,
 * risk adjustment). SIMULATED data.
 */

interface RegimeDetail {
  confidence: number;
  preferred: string;
  riskAdjustment: string;
}

const REGIME_DETAILS: Record<string, RegimeDetail> = {
  TRENDING: {
    confidence: 82,
    preferred: "Trend-following strategies",
    riskAdjustment: "NORMAL",
  },
  RANGING: {
    confidence: 64,
    preferred: "Mean-reversion strategies",
    riskAdjustment: "REDUCED",
  },
  "HIGH VOL": {
    confidence: 71,
    preferred: "Volatility-scaled positioning",
    riskAdjustment: "TIGHTENED",
  },
  "LOW VOL": {
    confidence: 58,
    preferred: "Range-based intraday setups",
    riskAdjustment: "NORMAL",
  },
  "RISK-ON": {
    confidence: 76,
    preferred: "Full strategy allocation",
    riskAdjustment: "NORMAL",
  },
  "NEWS RISK": {
    confidence: 69,
    preferred: "Event-aware trading only",
    riskAdjustment: "RESTRICTED",
  },
};

const REGIME_COLORS: Record<string, string> = {
  TRENDING: "#4D8DFF",
  RANGING: "#A7B3C5",
  "HIGH VOL": "#FFB020",
  "LOW VOL": "#22D3EE",
  "RISK-ON": "#34D399",
  "NEWS RISK": "#F0555B",
};

const REGIME_DESC_KEYS: Record<string, string> = {
  TRENDING: "regime.descTrending",
  RANGING: "regime.descRanging",
  "HIGH VOL": "regime.descHighVol",
  "LOW VOL": "regime.descLowVol",
  "RISK-ON": "regime.descRiskOn",
  "NEWS RISK": "regime.descNewsRisk",
};

const REGIME_PREF_KEYS: Record<string, string> = {
  TRENDING: "regime.prefTrending",
  RANGING: "regime.prefRanging",
  "HIGH VOL": "regime.prefHighVol",
  "LOW VOL": "regime.prefLowVol",
  "RISK-ON": "regime.prefRiskOn",
  "NEWS RISK": "regime.prefNewsRisk",
};

const REGIME_ADJ_KEYS: Record<string, string> = {
  NORMAL: "regime.adjNormal",
  REDUCED: "regime.adjReduced",
  TIGHTENED: "regime.adjTightened",
  RESTRICTED: "regime.adjRestricted",
};

interface RegimeEngineProps {
  className?: string;
  showHeader?: boolean;
}

export function RegimeEngine({ className, showHeader = true }: RegimeEngineProps) {
  const { t } = useTranslation();
  const regimes = MARKET_REGIME;
  const [active, setActive] = useState<string | null>("TRENDING");
  const detail = active ? REGIME_DETAILS[active] : null;
  const activeColor = active ? REGIME_COLORS[active] : "#4D8DFF";

  return (
    <div className={cn("mx-auto w-full max-w-4xl space-y-6", className)}>
      {showHeader && (
        <div className="space-y-3 text-center">
          <div className="flex items-center justify-center gap-2">
            <div className="h-px w-12 bg-gradient-to-r from-transparent to-accent" />
            <span className="font-mono text-[10px] uppercase tracking-widest text-accent">
                          {t("regime.engineTitle")}
                        </span>
                        <div className="h-px w-12 bg-gradient-to-l from-transparent to-accent" />
                      </div>
                      <h3 className="font-display text-2xl font-bold text-ink md:text-3xl">
                        {t("regime.adaptTitle")}
                      </h3>
                      <p className="mx-auto max-w-2xl text-sm leading-relaxed text-ink-dim">
                        {t("regime.adaptDescription")}
                      </p>
        </div>
      )}

      <motion.div
        className="rounded-panel border border-line bg-raised shadow-panel"
        initial={{ opacity: 0, y: 28 }}
        whileInView={{ opacity: 1, y: 0 }}
        viewport={{ once: true, margin: "-60px" }}
        transition={{ duration: 0.7, ease: "easeOut" }}
      >
        <div className="grid gap-0 md:grid-cols-[1.2fr_1fr]">
          {/* Regime bars */}
          <div className="space-y-5 p-6 md:p-8">
            <div className="font-mono text-[10px] uppercase tracking-widest text-ink-faint">
                          {t("regime.currentRegime")}
                        </div>
            {regimes.map((regime, i) => {
              const isActive = active === regime.regime;
              const color = REGIME_COLORS[regime.regime];
              return (
                <button
                  key={regime.regime}
                  type="button"
                  className="group block w-full cursor-pointer text-left"
                  onMouseEnter={() => setActive(regime.regime)}
                  onFocus={() => setActive(regime.regime)}
                >
                  <div className="flex items-center justify-between gap-3">
                    <span
                      className="font-mono text-xs font-semibold uppercase tracking-widest transition-colors duration-200"
                      style={{ color: isActive ? color : "var(--color-ink)" }}
                    >
                      {regime.regime}
                    </span>
                    <span className="font-mono text-xs text-ink-dim">
                      {regime.strength}%
                    </span>
                  </div>
                  <div className="relative mt-1.5 h-1.5 overflow-hidden rounded-full bg-raised">
                    <motion.div
                      className="absolute inset-y-0 left-0 rounded-full"
                      style={{ backgroundColor: color }}
                      initial={{ width: 0 }}
                      whileInView={{ width: `${regime.strength}%` }}
                      viewport={{ once: true, margin: "-40px" }}
                      transition={{
                        duration: 0.9,
                        delay: 0.2 + i * 0.1,
                        ease: "easeOut",
                      }}
                    />
                  </div>
                  <p
                                      className={cn(
                                        "mt-1 text-[11px] leading-relaxed transition-colors duration-200",
                                        isActive ? "text-ink-dim" : "text-ink-faint"
                                      )}
                                    >
                                      {t(REGIME_DESC_KEYS[regime.regime] ?? "regime.descTrending")}
                                    </p>
                </button>
              );
            })}
          </div>

          {/* Hover detail panel */}
          <div className="border-t border-line-soft bg-abyss/40 p-6 md:border-l md:border-t-0 md:p-8">
            <motion.div
              key={active ?? "none"}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.25 }}
              className="space-y-5"
            >
              <div className="font-mono text-[10px] uppercase tracking-widest text-ink-faint">
                              {t("regime.currentRegimeShort")}
                            </div>

                            <div>
                              <div
                                className="font-display text-2xl font-bold md:text-3xl"
                                style={{ color: activeColor }}
                              >
                                {active}
                              </div>
                              <div className="mt-1 font-mono text-[10px] uppercase tracking-widest text-ink-faint">
                                {detail?.confidence}% {t("regime.confidence")}
                              </div>
                            </div>

                            <div className="h-px bg-line" />

                            <div className="space-y-1.5">
                              <div className="font-mono text-[10px] uppercase tracking-widest text-ink-faint">
                                {t("regime.preferredBehavior")}
                              </div>
                              <div className="text-sm text-ink">
                                {t(REGIME_PREF_KEYS[active ?? ""] ?? "regime.prefTrending")}
                              </div>
                            </div>

                            <div className="space-y-1.5">
                              <div className="font-mono text-[10px] uppercase tracking-widest text-ink-faint">
                                {t("regime.riskAdjustment")}
                              </div>
                              <div
                                className="inline-flex items-center gap-2 rounded-chip border px-2.5 py-1"
                                style={{
                                  borderColor: `${activeColor}55`,
                                  backgroundColor: `${activeColor}14`,
                                  color: activeColor,
                                }}
                              >
                                <span
                                  className="h-1.5 w-1.5 animate-pulse rounded-full"
                                  style={{ backgroundColor: activeColor }}
                                />
                                <span className="font-mono text-[10px] font-semibold uppercase tracking-[0.18em]">
                                  {t(REGIME_ADJ_KEYS[detail?.riskAdjustment ?? ""] ?? "regime.adjNormal")}
                                </span>
                              </div>
                            </div>
            </motion.div>
          </div>
        </div>

        <div className="border-t border-warn/20 bg-warn/5 px-4 py-2 md:px-6">
                  <span className="font-mono text-[9px] font-semibold uppercase tracking-widest text-warn">
                    {t("regime.simulatedData")}
                  </span>
                </div>
      </motion.div>
    </div>
  );
}
