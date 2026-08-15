import { motion } from "framer-motion";
import { cn } from "@/lib/utils";

/**
 * RiskEngine — Section 10 of master prompt.
 * Shows that AI decisions pass through deterministic risk gates.
 * "Intelligence Decides. Risk Controls Execution."
 */

interface RiskGateProps {
  label: string;
  description: string;
  status: "ACTIVE" | "INACTIVE";
}

function RiskGate({ label, description, status }: RiskGateProps) {
  return (
    <div className="flex items-start gap-3 rounded-chip border border-line-soft bg-raised/30 p-3 backdrop-blur transition-colors hover:border-line hover:bg-raised/50">
      <div
        className={cn(
          "mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full border-2",
          status === "ACTIVE"
            ? "border-accent bg-accent/20"
            : "border-line bg-abyss/50"
        )}
      >
        {status === "ACTIVE" && (
          <svg
            className="h-3 w-3 text-accent"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={3}
              d="M5 13l4 4L19 7"
            />
          </svg>
        )}
      </div>
      <div className="min-w-0 flex-1 space-y-1">
        <div className="font-display text-xs font-semibold text-ink">
          {label}
        </div>
        <div className="text-[11px] leading-relaxed text-ink-dim">
          {description}
        </div>
      </div>
    </div>
  );
}

const RISK_GATES: RiskGateProps[] = [
  {
    label: "Position Sizing",
    description:
      "Maximum risk per trade enforced before execution. Dynamically adjusted based on volatility and account size.",
    status: "ACTIVE",
  },
  {
    label: "Stop Loss Validation",
    description:
      "Stop loss must be within acceptable distance from entry. Prevents excessive risk on single positions.",
    status: "ACTIVE",
  },
  {
    label: "Maximum Exposure",
    description:
      "Total portfolio exposure cannot exceed defined threshold. Prevents over-concentration in correlated positions.",
    status: "ACTIVE",
  },
  {
    label: "Daily Loss Limit",
    description:
      "Trading halts if daily loss exceeds threshold. Protects capital from cascading losses.",
    status: "ACTIVE",
  },
  {
    label: "Correlation Filter",
    description:
      "Blocks highly correlated positions. Ensures true portfolio diversification.",
    status: "ACTIVE",
  },
  {
    label: "Volatility Filter",
    description:
      "Reduces or blocks trading during extreme volatility spikes. Prevents execution in unstable conditions.",
    status: "ACTIVE",
  },
  {
    label: "News Event Filter",
    description:
      "Restricts trading around high-impact scheduled events. Avoids unpredictable spreads and slippage.",
    status: "ACTIVE",
  },
  {
    label: "Kill Switch",
    description:
      "Emergency manual override to halt all trading immediately. Human supervisor maintains ultimate control.",
    status: "ACTIVE",
  },
];

interface RiskEngineProps {
  className?: string;
  showHeader?: boolean;
  variant?: "full" | "compact";
}

export function RiskEngine({
  className,
  showHeader = true,
  variant = "full",
}: RiskEngineProps) {
  return (
    <div className={cn("w-full max-w-4xl space-y-6", className)}>
      {/* Header */}
      {showHeader && (
        <div className="space-y-3 text-center">
          <div className="flex items-center justify-center gap-2">
            <div className="h-px w-12 bg-gradient-to-r from-transparent to-accent" />
            <span className="font-mono text-[10px] uppercase tracking-widest text-accent">
              Risk Engine
            </span>
            <div className="h-px w-12 bg-gradient-to-l from-transparent to-accent" />
          </div>
          <h3 className="font-display text-2xl font-bold text-ink md:text-3xl">
            Intelligence Decides.
            <br />
            Risk Controls Execution.
          </h3>
          <p className="mx-auto max-w-2xl text-sm leading-relaxed text-ink-dim">
            AI can propose a trade. It cannot override the system's risk
            boundaries.
          </p>
        </div>
      )}

      {/* Compact: gate chips only */}
      {variant === "compact" ? (
        <>
          <div className="flex flex-wrap items-center justify-center gap-2">
            {["Position Sizing", "Max Exposure", "Daily Loss Limit", "Kill Switch"].map(
              (label, i) => (
                <motion.div
                  key={label}
                  initial={{ opacity: 0, y: 10 }}
                  whileInView={{ opacity: 1, y: 0 }}
                  viewport={{ once: true, margin: "-40px" }}
                  transition={{ duration: 0.4, delay: i * 0.08 }}
                >
                  <div className="flex items-center gap-2 rounded-chip border border-line-soft bg-raised/40 px-3 py-1.5 backdrop-blur">
                    <svg
                      className="h-3.5 w-3.5 text-up"
                      fill="none"
                      viewBox="0 0 24 24"
                      stroke="currentColor"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={3}
                        d="M5 13l4 4L19 7"
                      />
                    </svg>
                    <span className="font-mono text-[10px] font-semibold uppercase tracking-widest text-ink">
                      {label}
                    </span>
                  </div>
                </motion.div>
              )
            )}
          </div>

          {/* Important notice */}
          <div className="rounded-chip border border-accent/30 bg-accent/5 p-4 backdrop-blur">
            <p className="text-center text-xs leading-relaxed text-ink-dim">
              <span className="font-semibold text-accent">Important:</span> AI does
              not have unlimited authority. Every proposal passes through
              deterministic risk validation before reaching execution.
            </p>
          </div>
        </>
      ) : (
        /* Full variant: flow diagram + gate grid (unchanged) */
        <>
      {/* Flow diagram */}
      <div className="flex flex-col items-center gap-4 rounded-panel border border-line bg-raised/50 p-6 shadow-panel">
        <div className="flex w-full max-w-md flex-col items-center gap-3">
          <div className="w-full rounded-chip border border-accent/30 bg-accent/10 px-4 py-2 text-center">
            <span className="font-mono text-xs font-semibold uppercase tracking-widest text-accent">
              AI Proposal
            </span>
          </div>

          <svg
            className="h-6 w-6 text-accent"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M19 14l-7 7m0 0l-7-7m7 7V3"
            />
          </svg>

          <div className="w-full rounded-chip border border-line bg-raised px-4 py-2 text-center">
            <span className="font-mono text-xs font-semibold uppercase tracking-widest text-ink">
              Deterministic Validator
            </span>
          </div>

          <svg
            className="h-6 w-6 text-accent"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M19 14l-7 7m0 0l-7-7m7 7V3"
            />
          </svg>

          <div className="w-full rounded-chip border border-accent bg-accent/20 px-4 py-2 text-center backdrop-blur">
            <span className="font-mono text-xs font-bold uppercase tracking-widest text-accent">
              Risk Check
            </span>
          </div>

          <svg
            className="h-6 w-6 text-accent"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M19 14l-7 7m0 0l-7-7m7 7V3"
            />
          </svg>

          <div className="flex w-full gap-2">
            <div className="flex-1 rounded-chip border border-up/30 bg-up/10 px-3 py-2 text-center">
              <span className="font-mono text-[10px] font-semibold uppercase tracking-widest text-up">
                Approved
              </span>
            </div>
            <div className="flex-1 rounded-chip border border-down/30 bg-down/10 px-3 py-2 text-center">
              <span className="font-mono text-[10px] font-semibold uppercase tracking-widest text-down">
                Rejected
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* Risk gates grid */}
      <div className="space-y-3">
        <div className="font-mono text-[10px] uppercase tracking-widest text-ink-faint">
          Active Risk Controls
        </div>
        <div className="grid gap-3 md:grid-cols-2">
          {RISK_GATES.map((gate, i) => (
            <motion.div
              key={gate.label}
              initial={{ opacity: 0, y: 14 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, margin: "-40px" }}
              transition={{ duration: 0.4, delay: (i % 4) * 0.08 }}
            >
              <RiskGate {...gate} />
            </motion.div>
          ))}
        </div>
      </div>

      {/* Important notice */}
      <div className="rounded-chip border border-accent/30 bg-accent/5 p-4 backdrop-blur">
        <p className="text-center text-xs leading-relaxed text-ink-dim">
          <span className="font-semibold text-accent">Important:</span> AI does
          not have unlimited authority. Every proposal passes through
          deterministic risk validation before reaching execution.
        </p>
      </div>
        </>
      )}
    </div>
  );
}
