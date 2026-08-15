import { motion } from "framer-motion";
import { useState } from "react";
import { cn } from "@/lib/utils";

/**
 * ArchitectureDiagram — Section 26 of UI/UX Rebuild V2.
 * Interactive architecture map. Hover a layer to see its inputs,
 * outputs, and role in the loop. Not a boring flowchart.
 */

interface Layer {
  id: string;
  name: string;
  role: string;
  inputs: string[];
  outputs: string[];
  color: string;
}

const LAYERS: Layer[] = [
  {
    id: "data",
    name: "Data",
    role: "Market data collection and normalization",
    inputs: ["MT5 ticks & candles", "News feeds", "Macro calendar"],
    outputs: ["Normalized OHLCV", "Event stream"],
    color: "#A7B3C5",
  },
  {
    id: "intelligence",
    name: "Intelligence",
    role: "Specialized agents evaluate independent dimensions",
    inputs: ["Normalized market data"],
    outputs: ["Agent signals", "Confidence scores"],
    color: "#4D8DFF",
  },
  {
    id: "decision",
    name: "Decision",
    role: "Master intelligence assembles a single thesis",
    inputs: ["Agent signals", "Regime state"],
    outputs: ["Directional thesis", "Position proposal"],
    color: "#A78BFA",
  },
  {
    id: "risk",
    name: "Risk",
    role: "Deterministic gates govern every proposal",
    inputs: ["Thesis", "Portfolio state", "Risk limits"],
    outputs: ["Approved / Rejected", "Sized order"],
    color: "#FFB020",
  },
  {
    id: "execution",
    name: "Execution",
    role: "Order routing and fill management",
    inputs: ["Approved order"],
    outputs: ["Broker orders", "Fills & positions"],
    color: "#34D399",
  },
  {
    id: "feedback",
    name: "Feedback",
    role: "Performance closes the loop back to research",
    inputs: ["Fills", "P&L attribution"],
    outputs: ["Learning signals", "Strategy review"],
    color: "#22D3EE",
  },
];

interface ArchitectureDiagramProps {
  className?: string;
  showHeader?: boolean;
}

export function ArchitectureDiagram({ className, showHeader = true }: ArchitectureDiagramProps) {
  const [active, setActive] = useState<string>("intelligence");
  const layer = LAYERS.find((l) => l.id === active) ?? LAYERS[1];

  return (
    <div className={cn("w-full max-w-4xl space-y-6", className)}>
      {showHeader && (
        <div className="space-y-3 text-center">
          <div className="flex items-center justify-center gap-2">
            <div className="h-px w-12 bg-gradient-to-r from-transparent to-accent" />
            <span className="font-mono text-[10px] uppercase tracking-widest text-accent">
              System Architecture
            </span>
            <div className="h-px w-12 bg-gradient-to-l from-transparent to-accent" />
          </div>
          <h3 className="font-display text-2xl font-bold text-ink md:text-3xl">
            Built as Infrastructure,
            <br />
            Not a Script.
          </h3>
          <p className="mx-auto max-w-2xl text-sm leading-relaxed text-ink-dim">
            Hover each layer to inspect its inputs and outputs through the loop.
          </p>
        </div>
      )}

      <motion.div
        className="overflow-hidden rounded-panel border border-line bg-raised shadow-panel"
        initial={{ opacity: 0, y: 28 }}
        whileInView={{ opacity: 1, y: 0 }}
        viewport={{ once: true, margin: "-60px" }}
        transition={{ duration: 0.7, ease: "easeOut" }}
      >
        <div className="grid gap-0 md:grid-cols-[1fr_1.1fr]">
          {/* Layer pipeline */}
          <div className="p-6 md:p-8">
            <div className="space-y-2">
              {LAYERS.map((l, i) => {
                const isActive = active === l.id;
                return (
                  <motion.button
                    key={l.id}
                    type="button"
                    className="block w-full cursor-pointer text-left"
                    initial={{ opacity: 0, x: -14 }}
                    whileInView={{ opacity: 1, x: 0 }}
                    viewport={{ once: true, margin: "-40px" }}
                    transition={{ duration: 0.4, delay: i * 0.06 }}
                    onMouseEnter={() => setActive(l.id)}
                    onFocus={() => setActive(l.id)}
                  >
                    <div
                      className={cn(
                        "flex items-center justify-between rounded-chip border px-4 py-3 transition-all duration-200",
                        isActive
                          ? "border-transparent bg-abyss"
                          : "border-line-soft bg-raised/40 hover:border-line"
                      )}
                      style={
                        isActive
                          ? {
                              boxShadow: `inset 0 0 0 1px ${l.color}55, 0 0 20px ${l.color}1a`,
                            }
                          : undefined
                      }
                    >
                      <span
                        className="font-mono text-xs font-semibold uppercase tracking-widest"
                        style={{ color: isActive ? l.color : "var(--color-ink)" }}
                      >
                        {l.name}
                      </span>
                      <span className="font-mono text-[9px] uppercase tracking-widest text-ink-faint">
                        Layer {i + 1}
                      </span>
                    </div>
                    {i < LAYERS.length - 1 && (
                      <div className="ml-5 h-3 w-px bg-line" />
                    )}
                  </motion.button>
                );
              })}
            </div>
          </div>

          {/* Layer detail */}
          <div className="border-t border-line-soft bg-abyss/40 p-6 md:border-l md:border-t-0 md:p-8">
            <motion.div
              key={layer.id}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.25 }}
              className="space-y-5"
            >
              <div className="flex items-center gap-3">
                <span
                  className="h-2 w-2 rounded-full"
                  style={{ backgroundColor: layer.color }}
                />
                <span
                  className="font-display text-xl font-bold"
                  style={{ color: layer.color }}
                >
                  {layer.name}
                </span>
              </div>
              <p className="text-sm leading-relaxed text-ink-dim">{layer.role}</p>

              <div className="grid gap-4 sm:grid-cols-2">
                <div className="space-y-2">
                  <div className="font-mono text-[9px] uppercase tracking-[0.2em] text-ink-faint">
                    Inputs
                  </div>
                  <ul className="space-y-1.5">
                    {layer.inputs.map((input) => (
                      <li
                        key={input}
                        className="flex items-center gap-2 font-mono text-[11px] text-ink-dim"
                      >
                        <span
                          className="h-1 w-1 rounded-full"
                          style={{ backgroundColor: layer.color }}
                        />
                        {input}
                      </li>
                    ))}
                  </ul>
                </div>
                <div className="space-y-2">
                  <div className="font-mono text-[9px] uppercase tracking-[0.2em] text-ink-faint">
                    Outputs
                  </div>
                  <ul className="space-y-1.5">
                    {layer.outputs.map((output) => (
                      <li
                        key={output}
                        className="flex items-center gap-2 font-mono text-[11px] text-ink-dim"
                      >
                        <span className="h-1 w-1 rounded-full bg-line" />
                        {output}
                      </li>
                    ))}
                  </ul>
                </div>
              </div>
            </motion.div>
          </div>
        </div>

        {/* Loop footer */}
        <div className="border-t border-line-soft bg-raised/40 px-6 py-3">
          <p className="text-center font-mono text-[9px] uppercase tracking-[0.25em] text-ink-faint">
            Data → Intelligence → Decision → Risk → Execution → Feedback → Loop
          </p>
        </div>
      </motion.div>
    </div>
  );
}
