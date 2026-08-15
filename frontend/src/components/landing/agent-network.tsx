import { motion } from "framer-motion";
import { useState, type ReactNode } from "react";
import { cn } from "@/lib/utils";
import { AGENTS } from "@/data/landing/agents";
import {
  TechnicalIcon,
  MacroIcon,
  NewsIcon,
  StructureIcon,
  LumineIcon,
} from "./agent-icons";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";

/**
 * AgentNetwork — Section 17-18 of UI/UX Rebuild V2.
 * Interactive agent constellation. Click a node to inspect the agent
 * (role, description, status) in a Dialog — the landing page behaves
 * like a real product.
 */

const AGENT_ICONS: Record<string, (p: { size?: number }) => ReactNode> = {
  technical: TechnicalIcon,
  macro: MacroIcon,
  news: NewsIcon,
  structure: StructureIcon,
};

interface AgentNetworkProps {
  className?: string;
  showHeader?: boolean;
}

export function AgentNetwork({ className, showHeader = true }: AgentNetworkProps) {
  const [selected, setSelected] = useState<(typeof AGENTS)[number] | null>(null);

  return (
    <div className={cn("flex w-full flex-col items-center", className)}>
      {showHeader && (
        <div className="mb-10 space-y-3 text-center">
          <div className="flex items-center justify-center gap-2">
            <div className="h-px w-12 bg-gradient-to-r from-transparent to-accent" />
            <span className="font-mono text-[10px] uppercase tracking-widest text-accent">
              Intelligence Network
            </span>
            <div className="h-px w-12 bg-gradient-to-l from-transparent to-accent" />
          </div>
          <h3 className="font-display text-2xl font-bold text-ink md:text-3xl">
            Not One AI.
            <br />
            An Intelligence System.
          </h3>
        </div>
      )}

      {/* Four agents */}
      <div className="grid w-full max-w-3xl grid-cols-2 gap-6 md:grid-cols-4 md:gap-10">
        {AGENTS.map((agent, i) => {
          const Icon = AGENT_ICONS[agent.id];
          return (
            <motion.button
              key={agent.id}
              type="button"
              className="group flex cursor-pointer flex-col items-center gap-3"
              initial={{ opacity: 0, y: 24 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, margin: "-60px" }}
              transition={{ duration: 0.5, delay: i * 0.1 }}
              whileHover={{ y: -4 }}
              onClick={() => setSelected(agent)}
              aria-label={`Inspect ${agent.name} agent`}
            >
              {/* Node — 3D sphere */}
              <motion.div
                className="relative flex h-16 w-16 items-center justify-center rounded-full border"
                style={{
                  borderColor: agent.color,
                  background:
                    "radial-gradient(circle at 32% 26%, rgba(255,255,255,0.16) 0%, rgba(255,255,255,0.03) 34%, transparent 48%), linear-gradient(150deg, #1a2436 0%, #0b0f17 100%)",
                  boxShadow:
                    "0 10px 22px rgba(0,0,0,0.55), 0 0 16px rgba(0,0,0,0.3), inset 0 1px 0 rgba(255,255,255,0.12)",
                }}
                animate={{ y: [0, -3, 0] }}
                transition={{
                  duration: 4,
                  repeat: Number.POSITIVE_INFINITY,
                  ease: "easeInOut",
                  delay: i * 0.5,
                }}
              >
                <div
                  className="absolute inset-0 rounded-full opacity-15 blur-md transition-opacity duration-300 group-hover:opacity-35"
                  style={{ backgroundColor: agent.color }}
                />
                {/* Inner ring accent */}
                <div
                  className="absolute inset-[3px] rounded-full border transition-opacity duration-300 group-hover:opacity-60"
                  style={{ borderColor: agent.color, opacity: 0.18 }}
                />
                <span
                  className="relative transition-transform duration-300 group-hover:scale-110"
                  style={{ color: agent.color }}
                >
                  <Icon size={26} />
                </span>
                {/* Status dot */}
                <span
                  className="absolute -right-0.5 -top-0.5 h-2.5 w-2.5 rounded-full ring-2 ring-abyss"
                  style={{ backgroundColor: agent.color }}
                >
                  <span
                    className="absolute inset-0 animate-ping rounded-full"
                    style={{ backgroundColor: agent.color, opacity: 0.5 }}
                  />
                </span>
              </motion.div>
              {/* Label — nama saja (role dilihat di Dialog) */}
              <div className="text-center">
                <div className="font-display text-xs font-semibold text-ink">
                  {agent.name}
                </div>
              </div>
            </motion.button>
          );
        })}
      </div>

      {/* Flow indicator */}
      <motion.div
        className="my-6 flex items-center gap-3"
        initial={{ opacity: 0 }}
        whileInView={{ opacity: 1 }}
        viewport={{ once: true }}
        transition={{ duration: 0.6, delay: 0.4 }}
      >
        <div className="h-px w-10 bg-gradient-to-r from-transparent via-accent to-accent" />
        <svg
          className="h-4 w-4 animate-bounce text-accent"
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
        <div className="h-px w-10 bg-gradient-to-l from-transparent via-accent to-accent" />
      </motion.div>

      {/* Lumine Core */}
      <motion.div
        className="flex flex-col items-center gap-3"
        initial={{ opacity: 0, scale: 0.9 }}
        whileInView={{ opacity: 1, scale: 1 }}
        viewport={{ once: true, margin: "-60px" }}
        transition={{ duration: 0.6, delay: 0.5 }}
      >
        <div className="relative flex h-16 w-16 items-center justify-center rounded-full border-2 border-accent bg-raised/80 shadow-lg backdrop-blur">
          <div className="absolute inset-0 rounded-full bg-accent opacity-20 blur-md" />
          <motion.div
            className="absolute inset-0 rounded-full border border-accent"
            style={{ borderTopColor: "transparent" }}
            animate={{ rotate: 360 }}
            transition={{ duration: 6, repeat: Number.POSITIVE_INFINITY, ease: "linear" }}
          />
          <LumineIcon className="relative text-accent" size={28} />
        </div>
        <div className="text-center">
          <div className="font-display text-sm font-semibold text-ink">
            Master Intelligence
          </div>
          <div className="font-mono text-[9px] uppercase tracking-[0.18em] text-ink-faint">
            Decision Engine
          </div>
        </div>
      </motion.div>

      {/* Agent Inspector Dialog — Section 18 */}
      <Dialog open={!!selected} onOpenChange={(open) => !open && setSelected(null)}>
        <DialogContent className="border-line bg-raised">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-3 font-display text-xl text-ink">
              {selected && (
                <>
                  <span
                    className="flex h-10 w-10 items-center justify-center rounded-full border"
                    style={{
                      borderColor: selected.color,
                      color: selected.color,
                    }}
                  >
                    {selected && (() => {
                      const Icon = AGENT_ICONS[selected.id];
                      return <Icon size={20} />;
                    })()}
                  </span>
                  <span>
                    {selected?.name}
                    <span className="ml-2 font-mono text-[10px] uppercase tracking-[0.2em] text-ink-faint">
                      Intelligence
                    </span>
                  </span>
                </>
              )}
            </DialogTitle>
          </DialogHeader>

          {selected && (
            <div className="space-y-4">
              {/* Role */}
              <div>
                <h4 className="font-mono text-[10px] font-semibold uppercase tracking-[0.22em] text-ink-faint">
                  Role
                </h4>
                <p className="mt-1 text-sm text-ink">{selected.role}</p>
              </div>
              {/* Description */}
              <div>
                <h4 className="font-mono text-[10px] font-semibold uppercase tracking-[0.22em] text-ink-faint">
                  Mandate
                </h4>
                <p className="mt-1 text-sm leading-relaxed text-ink-dim">
                  {selected.description}
                </p>
              </div>
              {/* Status */}
              <div>
                <h4 className="font-mono text-[10px] font-semibold uppercase tracking-[0.22em] text-ink-faint">
                  Status
                </h4>
                <div className="mt-2 inline-flex items-center gap-2 rounded-chip border px-3 py-1.5"
                  style={{ borderColor: `${selected.color}55`, backgroundColor: `${selected.color}14` }}
                >
                  <span className="h-1.5 w-1.5 animate-pulse rounded-full"
                    style={{ backgroundColor: selected.color }}
                  />
                  <span className="font-mono text-[10px] font-semibold uppercase tracking-[0.2em]"
                    style={{ color: selected.color }}
                  >
                    Active
                  </span>
                </div>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
