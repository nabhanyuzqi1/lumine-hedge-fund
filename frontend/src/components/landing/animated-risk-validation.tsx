import { motion } from "framer-motion";
import { useState, useEffect } from "react";
import { Check } from "lucide-react";

/**
 * AnimatedRiskValidation — Section 20 of UI/UX Rebuild V2 master prompt.
 * 
 * "Intelligence Decides. Risk Controls Execution."
 * 
 * Animated validation sequence showing AI proposal passing through
 * deterministic risk gates before execution approval.
 * 
 * Animation sequence:
 * 1. AI PROPOSAL appears
 * 2. Each check fades in sequentially with 200ms delay
 * 3. Checkmark animates in after text
 * 4. Final APPROVED glows green
 */

interface ValidationCheck {
  id: string;
  label: string;
  delay: number;
}

const RISK_CHECKS: ValidationCheck[] = [
  { id: "exposure", label: "Position Size", delay: 0.2 },
  { id: "volatility", label: "Volatility Filter", delay: 0.4 },
  { id: "drawdown", label: "Max Drawdown", delay: 0.6 },
  { id: "correlation", label: "Correlation Limit", delay: 0.8 },
  { id: "news", label: "News Risk Filter", delay: 1.0 },
];

export function AnimatedRiskValidation() {
  const [isVisible, setIsVisible] = useState(false);

  useEffect(() => {
    // Trigger animation when component is in viewport
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting) {
          setIsVisible(true);
        }
      },
      { threshold: 0.3 }
    );

    const element = document.getElementById("risk-validation");
    if (element) observer.observe(element);

    return () => observer.disconnect();
  }, []);

  return (
    <div id="risk-validation" className="flex flex-col items-center gap-8">
      {/* AI Proposal */}
      <motion.div
        className="w-full max-w-md rounded-panel border border-line bg-raised/50 p-6 backdrop-blur"
        initial={{ opacity: 0, y: 20 }}
        animate={isVisible ? { opacity: 1, y: 0 } : {}}
        transition={{ duration: 0.6 }}
      >
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-full bg-accent/20">
            <span className="text-xl">🤖</span>
          </div>
          <div>
            <div className="font-mono text-xs uppercase tracking-widest text-ink-faint">
              AI Proposal
            </div>
            <div className="mt-1 font-semibold text-ink">
              LONG XAUUSD @ 3350.20
            </div>
          </div>
        </div>
      </motion.div>

      {/* Arrow down */}
      <motion.div
        className="flex flex-col items-center gap-2"
        initial={{ opacity: 0 }}
        animate={isVisible ? { opacity: 1 } : {}}
        transition={{ duration: 0.4, delay: 0.2 }}
      >
        <div className="h-6 w-[2px] bg-gradient-to-b from-line to-transparent" />
      </motion.div>

      {/* Risk Checks */}
      <div className="w-full max-w-md space-y-3">
        {RISK_CHECKS.map((check) => (
          <motion.div
            key={check.id}
            className="flex items-center gap-3 rounded-panel border border-line bg-raised/30 p-4 backdrop-blur"
            initial={{ opacity: 0, x: -20 }}
            animate={isVisible ? { opacity: 1, x: 0 } : {}}
            transition={{ duration: 0.4, delay: check.delay }}
          >
            {/* Checkmark */}
            <motion.div
              className="flex h-6 w-6 items-center justify-center rounded-full bg-up/20"
              initial={{ scale: 0 }}
              animate={isVisible ? { scale: 1 } : {}}
              transition={{
                duration: 0.3,
                delay: check.delay + 0.2,
                type: "spring",
                stiffness: 300,
                damping: 20,
              }}
            >
              <Check className="h-4 w-4 text-up" strokeWidth={3} />
            </motion.div>

            {/* Label */}
            <span className="font-mono text-sm text-ink">{check.label}</span>

            {/* Status */}
            <motion.span
              className="ml-auto font-mono text-xs uppercase tracking-wider text-up"
              initial={{ opacity: 0 }}
              animate={isVisible ? { opacity: 1 } : {}}
              transition={{ duration: 0.3, delay: check.delay + 0.3 }}
            >
              Passed
            </motion.span>
          </motion.div>
        ))}
      </div>

      {/* Arrow down */}
      <motion.div
        className="flex flex-col items-center gap-2"
        initial={{ opacity: 0 }}
        animate={isVisible ? { opacity: 1 } : {}}
        transition={{ duration: 0.4, delay: 1.2 }}
      >
        <div className="h-6 w-[2px] bg-gradient-to-b from-line to-transparent" />
      </motion.div>

      {/* Approved */}
      <motion.div
        className="w-full max-w-md rounded-panel border border-up/30 bg-up/5 p-6 backdrop-blur"
        initial={{ opacity: 0, scale: 0.95 }}
        animate={isVisible ? { opacity: 1, scale: 1 } : {}}
        transition={{ duration: 0.6, delay: 1.4 }}
      >
        <div className="flex items-center justify-center gap-3">
          {/* Glow effect */}
          <motion.div
            className="absolute inset-0 rounded-panel bg-up/10 blur-xl"
            animate={isVisible ? { opacity: [0, 0.5, 0] } : {}}
            transition={{
              duration: 2,
              repeat: Number.POSITIVE_INFINITY,
              delay: 1.4,
            }}
          />

          <div className="relative flex h-12 w-12 items-center justify-center rounded-full bg-up/20">
            <Check className="h-6 w-6 text-up" strokeWidth={3} />
          </div>

          <div className="relative">
            <div className="font-mono text-xs uppercase tracking-widest text-up/80">
              Execution Ready
            </div>
            <div className="mt-1 font-display text-2xl font-bold text-up">
              APPROVED
            </div>
          </div>
        </div>
      </motion.div>
    </div>
  );
}
