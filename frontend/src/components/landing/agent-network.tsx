import { cn } from "@/lib/utils";
import { AGENTS } from "@/data/landing/agents";

/**
 * AgentNetwork — Multi-agent architecture visualization.
 * Shows the four specialized agents feeding into Master Intelligence.
 * Subtle animations respect prefers-reduced-motion.
 */

interface AgentNodeProps {
  agent: typeof AGENTS[number];
  delay: number;
}

function AgentNode({ agent, delay }: AgentNodeProps) {
  return (
    <div
      className="group relative flex flex-col items-center gap-2"
      style={{ animationDelay: `${delay}ms` }}
    >
      {/* Agent icon */}
      <div
        className={cn(
          "relative flex h-12 w-12 items-center justify-center rounded-full border-2 transition-all duration-300",
          "bg-raised/80 backdrop-blur",
          "group-hover:scale-110 group-hover:shadow-lg"
        )}
        style={{ borderColor: agent.color }}
      >
        <div
          className="absolute inset-0 rounded-full opacity-20 blur-sm"
          style={{ backgroundColor: agent.color }}
        />
        <span
          className="relative font-mono text-xs font-bold"
          style={{ color: agent.color }}
        >
          {agent.name.split(" ")[0].slice(0, 3).toUpperCase()}
        </span>
      </div>

      {/* Agent label */}
      <div className="text-center">
        <div className="font-display text-xs font-semibold text-ink">
          {agent.name.split(" ")[0]}
        </div>
        <div className="font-mono text-[9px] uppercase tracking-widest text-ink-faint">
          {agent.role.split(" ")[0]}
        </div>
      </div>

      {/* Pulse animation */}
      <div
        className="absolute inset-0 -z-10 rounded-full opacity-0 blur-md transition-opacity duration-1000 group-hover:opacity-30"
        style={{ backgroundColor: agent.color }}
      />
    </div>
  );
}

interface AgentNetworkProps {
  className?: string;
}

export function AgentNetwork({ className }: AgentNetworkProps) {
  return (
    <div className={cn("flex flex-col items-center gap-8 py-12", className)}>
      {/* Four agents */}
      <div className="grid grid-cols-2 gap-8 md:grid-cols-4 md:gap-12">
        {AGENTS.map((agent, i) => (
          <AgentNode key={agent.id} agent={agent} delay={i * 100} />
        ))}
      </div>

      {/* Flow indicator */}
      <div className="flex items-center gap-3">
        <div className="h-px w-8 bg-gradient-to-r from-transparent via-accent to-transparent" />
        <svg
          className="h-4 w-4 text-accent"
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
        <div className="h-px w-8 bg-gradient-to-r from-transparent via-accent to-transparent" />
      </div>

      {/* Master Intelligence node */}
      <div className="relative flex flex-col items-center gap-3">
        <div className="relative flex h-16 w-16 items-center justify-center rounded-full border-2 border-accent bg-raised/80 shadow-lg backdrop-blur">
          <div className="absolute inset-0 rounded-full bg-accent opacity-20 blur-md" />
          <span className="relative font-mono text-sm font-bold text-accent">
            MI
          </span>
        </div>
        <div className="text-center">
          <div className="font-display text-sm font-semibold text-ink">
            Master Intelligence
          </div>
          <div className="font-mono text-[9px] uppercase tracking-widest text-ink-faint">
            Decision Engine
          </div>
        </div>
      </div>
    </div>
  );
}
