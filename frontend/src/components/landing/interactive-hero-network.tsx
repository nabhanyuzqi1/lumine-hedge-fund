import { motion } from "framer-motion";
import { useEffect, useState } from "react";
import { cn } from "@/lib/utils";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { AGENTS } from "@/data/landing/agents";
import { TechnicalIcon, MacroIcon, NewsIcon, StructureIcon, LumineIcon } from "./agent-icons";

/**
 * InteractiveHeroNetwork — Section 13-16 of UI/UX Rebuild V2 master prompt.
 * 
 * Interactive 4-agent intelligence constellation feeding into Lumine core.
 * 
 * Features:
 * - Animated connection lines with flowing data particles
 * - Hover states: scale agents, brighten connections
 * - Click agent to open Dialog with details
 * - Cursor proximity effects
 * - Respects prefers-reduced-motion
 * 
 * Layout (cross formation):
 * 
 *           TECHNICAL
 *               ●
 *               │
 *               │
 *   MACRO ● ───CORE─── ● NEWS
 *               │
 *               │
 *               ●
 *           STRUCTURE
 */

interface Agent {
  id: string;
  name: string;
  role: string;
  description: string;
  color: string;
  position: { x: number; y: number };
}

// Agent positions in cross formation (center = 0,0)
const NETWORK_AGENTS: Agent[] = [
  {
    ...AGENTS[0], // Technical
    position: { x: 0, y: -140 }, // top
  },
  {
    ...AGENTS[1], // Macro
    position: { x: -180, y: 0 }, // left
  },
  {
    ...AGENTS[2], // News
    position: { x: 180, y: 0 }, // right
  },
  {
    ...AGENTS[3], // Structure
    position: { x: 0, y: 140 }, // bottom
  },
];

interface AgentNodeProps {
  agent: Agent;
  isHovered: boolean;
  onHover: (id: string | null) => void;
  onClick: (agent: Agent) => void;
  mouseX: number;
  mouseY: number;
}

function AgentNode({ agent, isHovered, onHover, onClick, mouseX, mouseY }: AgentNodeProps) {
  const nodeX = agent.position.x;
  const nodeY = agent.position.y;
  
  // Calculate distance from cursor to node
  const distance = Math.sqrt(
    Math.pow(mouseX - nodeX, 2) + Math.pow(mouseY - nodeY, 2)
  );
  
  // Magnetic effect when cursor within 100px
  const proximity = Math.max(0, 1 - distance / 100);
  const magneticX = proximity * (mouseX - nodeX) * 0.15;
  const magneticY = proximity * (mouseY - nodeY) * 0.15;

  return (
    <motion.div
      className="absolute cursor-pointer"
      style={{
        left: "50%",
        top: "50%",
        x: nodeX + magneticX,
        y: nodeY + magneticY,
      }}
      initial={{ opacity: 0, scale: 0 }}
      animate={{ 
        opacity: 1, 
        scale: 1,
      }}
      transition={{
        type: "spring",
        stiffness: 300,
        damping: 30,
        delay: 0.1,
      }}
      whileHover={{ scale: 1.15 }}
      whileTap={{ scale: 0.95 }}
      onHoverStart={() => onHover(agent.id)}
      onHoverEnd={() => onHover(null)}
      onClick={() => onClick(agent)}
    >
      {/* Glow effect */}
      <motion.div
        className="absolute inset-0 rounded-full blur-xl"
        style={{
          backgroundColor: agent.color,
        }}
        animate={{
          opacity: isHovered ? 0.4 : 0.15,
          scale: isHovered ? 1.5 : 1,
        }}
        transition={{ duration: 0.3 }}
      />
      
      {/* Node circle */}
      <div
        className={cn(
          "relative flex h-16 w-16 items-center justify-center rounded-full border-2 bg-raised/90 backdrop-blur transition-all",
          isHovered && "border-4"
        )}
        style={{
          borderColor: agent.color,
          boxShadow: isHovered ? `0 0 20px ${agent.color}40` : "none",
        }}
      >
        {/* Pulse ring */}
        <motion.div
          className="absolute inset-0 rounded-full border-2"
          style={{ borderColor: agent.color }}
          animate={{
            scale: [1, 1.3, 1],
            opacity: [0.5, 0, 0.5],
          }}
          transition={{
            duration: 2,
            repeat: Number.POSITIVE_INFINITY,
            ease: "easeInOut",
          }}
        />
        
        {/* Agent icon */}
        <span className="text-ink">
          {agent.id === "technical" ? <TechnicalIcon size={28} /> :
           agent.id === "macro" ? <MacroIcon size={28} /> :
           agent.id === "news" ? <NewsIcon size={28} /> :
           <StructureIcon size={28} />}
        </span>
      </div>
      
      {/* Label */}
      <motion.div
        className="absolute left-1/2 -translate-x-1/2 whitespace-nowrap"
        style={{ top: agent.position.y > 0 ? "calc(100% + 12px)" : "auto", bottom: agent.position.y < 0 ? "calc(100% + 12px)" : "auto" }}
        animate={{
          opacity: isHovered ? 1 : 0.7,
        }}
      >
        <span className="font-mono text-[10px] font-semibold uppercase tracking-widest text-ink-dim">
          {agent.name}
        </span>
      </motion.div>
    </motion.div>
  );
}

interface ConnectionLineProps {
  from: { x: number; y: number };
  to: { x: number; y: number };
  color: string;
  isActive: boolean;
}

function ConnectionLine({ from, to, color, isActive }: ConnectionLineProps) {
  return (
    <svg
      className="pointer-events-none absolute left-1/2 top-1/2"
      style={{
        width: Math.abs(to.x - from.x) + 40,
        height: Math.abs(to.y - from.y) + 40,
        transform: `translate(-50%, -50%)`,
      }}
    >
      <motion.line
        x1={from.x > to.x ? "100%" : "0%"}
        y1={from.y > to.y ? "100%" : "0%"}
        x2={to.x > from.x ? "100%" : "0%"}
        y2={to.y > from.y ? "100%" : "0%"}
        stroke={color}
        strokeWidth={isActive ? 2 : 1}
        strokeDasharray="4 4"
        animate={{
          opacity: isActive ? 0.8 : 0.3,
          strokeDashoffset: [0, -8],
        }}
        transition={{
          opacity: { duration: 0.3 },
          strokeDashoffset: {
            duration: 1,
            repeat: Number.POSITIVE_INFINITY,
            ease: "linear",
          },
        }}
      />
      
      {/* Flowing data particle */}
      {isActive && (
        <motion.circle
          r={3}
          fill={color}
          animate={{
            cx: [from.x > to.x ? "100%" : "0%", to.x > from.x ? "100%" : "0%"],
            cy: [from.y > to.y ? "100%" : "0%", to.y > from.y ? "100%" : "0%"],
          }}
          transition={{
            duration: 2,
            repeat: Number.POSITIVE_INFINITY,
            ease: "linear",
          }}
        />
      )}
    </svg>
  );
}

export function InteractiveHeroNetwork() {
  const [hoveredAgent, setHoveredAgent] = useState<string | null>(null);
  const [selectedAgent, setSelectedAgent] = useState<Agent | null>(null);
  const [mousePosition, setMousePosition] = useState({ x: 0, y: 0 });

  // Track mouse position relative to network center
  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      const networkEl = document.getElementById("hero-network");
      if (!networkEl) return;
      
      const rect = networkEl.getBoundingClientRect();
      const centerX = rect.width / 2;
      const centerY = rect.height / 2;
      
      setMousePosition({
        x: e.clientX - rect.left - centerX,
        y: e.clientY - rect.top - centerY,
      });
    };

    window.addEventListener("mousemove", handleMouseMove);
    return () => window.removeEventListener("mousemove", handleMouseMove);
  }, []);

  return (
    <>
      <div 
        id="hero-network"
        className="relative mx-auto h-[500px] w-full max-w-3xl"
      >
        {/* Connection lines */}
        {NETWORK_AGENTS.map((agent) => (
          <ConnectionLine
            key={`connection-${agent.id}`}
            from={agent.position}
            to={{ x: 0, y: 0 }}
            color={agent.color}
            isActive={hoveredAgent === agent.id || hoveredAgent === "core"}
          />
        ))}

        {/* Lumine Core (center) */}
        <motion.div
          className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 cursor-pointer"
          initial={{ opacity: 0, scale: 0 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{
            type: "spring",
            stiffness: 300,
            damping: 30,
            delay: 0.5,
          }}
          whileHover={{ scale: 1.1 }}
          onHoverStart={() => setHoveredAgent("core")}
          onHoverEnd={() => setHoveredAgent(null)}
        >
          {/* Core glow */}
          <motion.div
            className="absolute inset-0 rounded-full bg-accent blur-2xl"
            animate={{
              opacity: hoveredAgent === "core" ? 0.5 : 0.2,
              scale: hoveredAgent === "core" ? 1.5 : 1,
            }}
            transition={{ duration: 0.3 }}
          />
          
          {/* Core circle */}
          <div className="relative flex h-24 w-24 items-center justify-center rounded-full border-2 border-accent bg-raised/90 backdrop-blur">
            {/* Rotating ring */}
            <motion.div
              className="absolute inset-0 rounded-full border-2 border-accent/50 border-t-accent"
              animate={{ rotate: 360 }}
              transition={{
                duration: 4,
                repeat: Number.POSITIVE_INFINITY,
                ease: "linear",
              }}
            />
            
            {/* L icon */}
            <LumineIcon className="text-accent" size={36} />
          </div>
          
          {/* Core label */}
          <div className="absolute left-1/2 top-full mt-3 -translate-x-1/2 whitespace-nowrap">
            <span className="font-mono text-xs font-semibold uppercase tracking-widest text-accent">
              Lumine Core
            </span>
          </div>
        </motion.div>

        {/* Agent nodes */}
        {NETWORK_AGENTS.map((agent) => (
          <AgentNode
            key={agent.id}
            agent={agent}
            isHovered={hoveredAgent === agent.id}
            onHover={setHoveredAgent}
            onClick={setSelectedAgent}
            mouseX={mousePosition.x}
            mouseY={mousePosition.y}
          />
        ))}
      </div>

      {/* Agent Detail Dialog */}
      <Dialog open={!!selectedAgent} onOpenChange={(open) => !open && setSelectedAgent(null)}>
        <DialogContent className="border-line bg-raised">
          <DialogHeader>
            <DialogTitle className="font-display text-2xl text-ink">
              {selectedAgent?.name}
            </DialogTitle>
          </DialogHeader>
          
          <div className="space-y-4">
            <div>
              <h4 className="font-mono text-xs font-semibold uppercase tracking-widest text-ink-dim">Role</h4>
              <p className="mt-1 text-sm text-ink">{selectedAgent?.role}</p>
            </div>
            
            <div>
              <h4 className="font-mono text-xs font-semibold uppercase tracking-widest text-ink-dim">Description</h4>
              <p className="mt-1 text-sm leading-relaxed text-ink-dim">{selectedAgent?.description}</p>
            </div>
            
            <div>
              <h4 className="font-mono text-xs font-semibold uppercase tracking-widest text-ink-dim">Status</h4>
              <div className="mt-2 inline-flex items-center gap-2 rounded-chip border border-line-soft bg-abyss px-3 py-1.5">
                <div className="h-2 w-2 animate-pulse rounded-full bg-up" />
                <span className="font-mono text-[10px] font-semibold uppercase tracking-widest text-up">
                  Active
                </span>
              </div>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}
