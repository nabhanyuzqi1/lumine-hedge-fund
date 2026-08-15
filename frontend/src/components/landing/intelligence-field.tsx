import { motion } from "framer-motion";
import { useEffect, useRef, useState } from "react";
import { cn } from "@/lib/utils";
import { AGENTS } from "@/data/landing/agents";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import {
  TechnicalIcon,
  MacroIcon,
  NewsIcon,
  StructureIcon,
  LumineIcon,
} from "./agent-icons";

/**
 * IntelligenceField — Hero intelligence network (UI/UX Rebuild V2, Section 13-16).
 *
 * Interactive 4-agent cross formation feeding Lumine core.
 * Connecting lines are drawn in a SINGLE SVG with absolute viewBox
 * coordinates (0 0 400 400), so lines always connect node edges to
 * the core edge regardless of container size. No percentage-based
 * line hacks.
 *
 * Layout (viewBox 400x400, center 200,200):
 *
 *                 TECHNICAL (200,50)
 *                     |
 *   MACRO (50,200) ───CORE─── NEWS (350,200)
 *                     |
 *              STRUCTURE (200,350)
 */

const VB = 400; // viewBox size
const CENTER = 200;
const NODE_R = 30; // node radius in viewBox units
const CORE_R = 42;

interface NodeDef {
  id: string;
  name: string;
  x: number; // viewBox coords
  y: number;
  color: string;
}

const NODES: NodeDef[] = [
  { id: "technical", name: "Technical", x: 200, y: 50, color: "#4D8DFF" },
  { id: "macro", name: "Macro", x: 50, y: 200, color: "#A78BFA" },
  { id: "news", name: "News", x: 350, y: 200, color: "#F59E0B" },
  { id: "structure", name: "Structure", x: 200, y: 350, color: "#34D399" },
];

/** Line endpoints from node edge to core edge (viewBox coords). */
function lineEndpoints(node: NodeDef) {
  const dx = CENTER - node.x;
  const dy = CENTER - node.y;
  const len = Math.sqrt(dx * dx + dy * dy);
  const ux = dx / len;
  const uy = dy / len;
  return {
    x1: node.x + ux * NODE_R,
    y1: node.y + uy * NODE_R,
    x2: CENTER - ux * CORE_R,
    y2: CENTER - uy * CORE_R,
  };
}

interface TelemetryItem {
  label: string;
  value: string;
  accent?: boolean;
}

const TELEMETRY: TelemetryItem[] = [
  { label: "System", value: "Online" },
  { label: "Market", value: "XAUUSD" },
  { label: "Agents", value: "04 / 04" },
  { label: "Mode", value: "Research", accent: true },
];

export function IntelligenceField() {
  const containerRef = useRef<HTMLDivElement>(null);
  const [hovered, setHovered] = useState<string | null>(null);
  const [mouse, setMouse] = useState({ nx: 0, ny: 0 }); // normalized -1..1
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const selectedAgent = AGENTS.find((a) => a.id === selectedId) ?? null;

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const onMove = (e: MouseEvent) => {
      const r = el.getBoundingClientRect();
      const nx = ((e.clientX - r.left) / r.width - 0.5) * 2;
      const ny = ((e.clientY - r.top) / r.height - 0.5) * 2;
      setMouse({ nx, ny });
    };
    window.addEventListener("mousemove", onMove);
    return () => window.removeEventListener("mousemove", onMove);
  }, []);

  const coreActive = hovered === "core";

  return (
    <div className="w-full">
      {/* Network field */}
      <div
        ref={containerRef}
        className="relative mx-auto aspect-square w-full max-w-[460px] select-none"
        onMouseLeave={() => setHovered(null)}
      >
        {/* Subtle grid backdrop */}
        <div
          className="absolute inset-0 opacity-[0.15]"
          style={{
            backgroundImage:
              "linear-gradient(var(--color-line) 1px, transparent 1px), linear-gradient(90deg, var(--color-line) 1px, transparent 1px)",
            backgroundSize: "40px 40px",
          }}
        />
        <div className="absolute inset-0 rounded-full bg-[radial-gradient(circle,rgba(77,141,255,0.06)_0%,transparent_60%)]" />

        {/* Connecting lines — single SVG, absolute coords */}
        <svg
          viewBox={`0 0 ${VB} ${VB}`}
          className="pointer-events-none absolute inset-0 h-full w-full"
          aria-hidden="true"
        >
          {NODES.map((node) => {
            const { x1, y1, x2, y2 } = lineEndpoints(node);
            const active = hovered === node.id || coreActive;
            const midX = (x1 + x2) / 2;
            const midY = (y1 + y2) / 2;
            return (
              <g key={node.id}>
                {/* Base line */}
                <motion.line
                  x1={x1}
                  y1={y1}
                  x2={x2}
                  y2={y2}
                  stroke={node.color}
                  strokeWidth={active ? 1.6 : 1}
                  strokeDasharray="5 5"
                  initial={{ opacity: 0 }}
                  animate={{ opacity: active ? 0.85 : 0.3 }}
                  transition={{ duration: 0.3 }}
                />
                {/* Flowing dash overlay */}
                <motion.line
                  x1={x1}
                  y1={y1}
                  x2={x2}
                  y2={y2}
                  stroke={node.color}
                  strokeWidth={1.6}
                  strokeDasharray="10 90"
                  initial={{ pathLength: 0, opacity: 0 }}
                  animate={{
                    opacity: active ? 1 : 0.5,
                    strokeDashoffset: [0, -200],
                  }}
                  transition={{
                    strokeDashoffset: {
                      duration: 1.6,
                      repeat: Number.POSITIVE_INFINITY,
                      ease: "linear",
                    },
                  }}
                />
                {/* Data particle traveling to core */}
                <motion.circle
                  r={2.4}
                  fill={node.color}
                  initial={{ opacity: 0 }}
                  animate={{
                    opacity: active ? 1 : 0.6,
                    cx: [x1, x2],
                    cy: [y1, y2],
                  }}
                  transition={{
                    cx: {
                      duration: 1.6,
                      repeat: Number.POSITIVE_INFINITY,
                      ease: "easeInOut",
                    },
                    cy: {
                      duration: 1.6,
                      repeat: Number.POSITIVE_INFINITY,
                      ease: "easeInOut",
                    },
                  }}
                />
                {/* Midpoint pulse */}
                <motion.circle
                  r={active ? 4 : 2.5}
                  fill={node.color}
                  opacity={0.5}
                  animate={{
                    cx: [midX, midX],
                    cy: [midY, midY],
                    opacity: [0.1, 0.6, 0.1],
                  }}
                  transition={{
                    opacity: {
                      duration: 2,
                      repeat: Number.POSITIVE_INFINITY,
                    },
                  }}
                />
              </g>
            );
          })}
        </svg>

        {/* Nodes — HTML absolutely positioned at viewBox-relative % */}
        {NODES.map((node) => {
          const active = hovered === node.id;
          const dx = node.x === CENTER ? 0 : mouse.nx * 6;
          const dy = node.y === CENTER ? 0 : mouse.ny * 6;
          const labelAbove = node.y > CENTER; // bottom node → label on top
          return (
            <motion.div
              key={node.id}
              className="absolute z-10 cursor-pointer"
              style={{
                left: `${(node.x / VB) * 100}%`,
                top: `${(node.y / VB) * 100}%`,
                x: dx,
                y: dy,
              }}
              initial={{ opacity: 0, scale: 0 }}
              animate={{ opacity: 1, scale: 1 }}
              transition={{
                type: "spring",
                stiffness: 300,
                damping: 25,
                delay: 0.3,
              }}
              whileHover={{ scale: 1.12 }}
              whileTap={{ scale: 0.95 }}
              onHoverStart={() => setHovered(node.id)}
              onHoverEnd={() => setHovered(null)}
              onClick={() => setSelectedId(node.id)}
              role="button"
              aria-label={`${node.name} intelligence agent — inspect`}
            >
              {/* Node disc */}
              <div
                className="relative flex h-[58px] w-[58px] -translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-full border backdrop-blur transition-all duration-300"
                style={{
                  borderColor: active ? node.color : "var(--color-line)",
                  background:
                    "linear-gradient(145deg, var(--color-raised) 0%, var(--color-abyss) 100%)",
                  boxShadow: active
                    ? `0 0 28px ${node.color}59, inset 0 0 14px ${node.color}1f, 0 4px 16px rgba(0,0,0,0.5)`
                    : `0 0 14px ${node.color}1f, 0 2px 10px rgba(0,0,0,0.4)`,
                }}
              >
                {/* Inner ring accent */}
                <div
                  className="absolute inset-[3px] rounded-full border transition-opacity duration-300"
                  style={{
                    borderColor: node.color,
                    opacity: active ? 0.45 : 0.12,
                  }}
                />
                {/* Icon */}
                <span
                  className="transition-colors duration-300"
                  style={{
                    color: active ? node.color : "var(--color-ink-dim)",
                  }}
                >
                  {node.id === "technical" ? (
                    <TechnicalIcon size={24} />
                  ) : node.id === "macro" ? (
                    <MacroIcon size={24} />
                  ) : node.id === "news" ? (
                    <NewsIcon size={24} />
                  ) : (
                    <StructureIcon size={24} />
                  )}
                </span>
                {/* Live status dot */}
                <span
                  className="absolute -bottom-0.5 -right-0.5 h-2.5 w-2.5 rounded-full ring-2 ring-abyss"
                  style={{ backgroundColor: node.color }}
                >
                  <span
                    className="absolute inset-0 animate-ping rounded-full"
                    style={{ backgroundColor: node.color, opacity: 0.5 }}
                  />
                </span>
              </div>

              {/* Label — solid chip so connecting lines never collide */}
              <div
                className="absolute left-1/2 -translate-x-1/2 whitespace-nowrap"
                style={{
                  top: labelAbove ? "auto" : "calc(100% + 6px)",
                  bottom: labelAbove ? "calc(100% + 6px)" : "auto",
                }}
              >
                <span
                  className="inline-flex items-center gap-1.5 rounded-chip border border-line-soft bg-abyss/90 px-2 py-0.5 font-mono text-[9px] font-semibold uppercase tracking-[0.2em] backdrop-blur transition-colors duration-300"
                  style={{
                    color: active ? node.color : "var(--color-ink-dim)",
                    borderColor: active ? `${node.color}66` : undefined,
                  }}
                >
                  <span
                    className="h-1 w-1 rounded-full"
                    style={{ backgroundColor: node.color }}
                  />
                  {node.name}
                </span>
              </div>
            </motion.div>
          );
        })}

        {/* Lumine Core */}
        <motion.div
          className="absolute left-1/2 top-1/2 z-10 -translate-x-1/2 -translate-y-1/2 cursor-pointer"
          style={{ x: mouse.nx * 3, y: mouse.ny * 3 }}
          initial={{ opacity: 0, scale: 0 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{
            type: "spring",
            stiffness: 260,
            damping: 24,
            delay: 0.5,
          }}
          whileHover={{ scale: 1.08 }}
          onHoverStart={() => setHovered("core")}
          onHoverEnd={() => setHovered(null)}
          role="button"
          aria-label="Lumine core intelligence"
        >
          {/* Glow */}
          <motion.div
            className="absolute inset-0 rounded-full bg-accent blur-2xl"
            animate={{
              opacity: coreActive ? 0.5 : 0.22,
              scale: coreActive ? 1.4 : 1.1,
            }}
            transition={{ duration: 0.3 }}
          />
          {/* Core disc */}
          <div className="relative flex h-[76px] w-[76px] items-center justify-center rounded-full border-2 border-accent bg-raised backdrop-blur">
            <motion.div
              className="absolute inset-0 rounded-full border border-accent"
              style={{ borderTopColor: "transparent" }}
              animate={{ rotate: 360 }}
              transition={{
                duration: 5,
                repeat: Number.POSITIVE_INFINITY,
                ease: "linear",
              }}
            />
            <LumineIcon className="text-accent" size={34} />
          </div>
          {/* Core label */}
          <div className="absolute left-1/2 top-full mt-2.5 -translate-x-1/2 whitespace-nowrap">
            <span className="inline-flex items-center gap-1.5 rounded-chip border border-accent/30 bg-abyss/90 px-2.5 py-0.5 font-mono text-[10px] font-bold uppercase tracking-[0.25em] text-accent backdrop-blur">
              <span className="h-1 w-1 animate-pulse rounded-full bg-accent" />
              Lumine Core
            </span>
          </div>
        </motion.div>
      </div>

      {/* Telemetry strip — Section 15 */}
      <div className="mx-auto mt-8 grid w-full max-w-[460px] grid-cols-4 gap-px overflow-hidden rounded-panel border border-line bg-line">
        {TELEMETRY.map((t) => (
          <div
            key={t.label}
            className={cn("bg-abyss/90 px-2 py-2.5 text-center backdrop-blur")}
          >
            <div className="font-mono text-[8px] uppercase tracking-[0.2em] text-ink-faint">
              {t.label}
            </div>
            <div
              className={cn(
                "mt-0.5 font-mono text-[10px] font-semibold",
                t.accent ? "text-accent" : "text-ink"
              )}
            >
              {t.value}
            </div>
          </div>
        ))}
      </div>

      {/* Agent Inspector Dialog */}
      <Dialog open={!!selectedAgent} onOpenChange={(open) => !open && setSelectedId(null)}>
        <DialogContent className="border-line bg-raised">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-3 font-display text-xl text-ink">
              {selectedAgent && (
                <>
                  <span
                    className="flex h-10 w-10 items-center justify-center rounded-full border"
                    style={{
                      borderColor: selectedAgent.color,
                      color: selectedAgent.color,
                    }}
                  >
                    {selectedAgent.id === "technical" ? (
                      <TechnicalIcon size={20} />
                    ) : selectedAgent.id === "macro" ? (
                      <MacroIcon size={20} />
                    ) : selectedAgent.id === "news" ? (
                      <NewsIcon size={20} />
                    ) : (
                      <StructureIcon size={20} />
                    )}
                  </span>
                  <span>
                    {selectedAgent.name}
                    <span className="ml-2 font-mono text-[10px] uppercase tracking-[0.2em] text-ink-faint">
                      Intelligence
                    </span>
                  </span>
                </>
              )}
            </DialogTitle>
          </DialogHeader>

          {selectedAgent && (
            <div className="space-y-4">
              <div>
                <h4 className="font-mono text-[10px] font-semibold uppercase tracking-[0.22em] text-ink-faint">
                  Role
                </h4>
                <p className="mt-1 text-sm text-ink">{selectedAgent.role}</p>
              </div>
              <div>
                <h4 className="font-mono text-[10px] font-semibold uppercase tracking-[0.22em] text-ink-faint">
                  Mandate
                </h4>
                <p className="mt-1 text-sm leading-relaxed text-ink-dim">
                  {selectedAgent.description}
                </p>
              </div>
              <div>
                <h4 className="font-mono text-[10px] font-semibold uppercase tracking-[0.22em] text-ink-faint">
                  Status
                </h4>
                <div
                  className="mt-2 inline-flex items-center gap-2 rounded-chip border px-3 py-1.5"
                  style={{
                    borderColor: `${selectedAgent.color}55`,
                    backgroundColor: `${selectedAgent.color}14`,
                  }}
                >
                  <span
                    className="h-1.5 w-1.5 animate-pulse rounded-full"
                    style={{ backgroundColor: selectedAgent.color }}
                  />
                  <span
                    className="font-mono text-[10px] font-semibold uppercase tracking-[0.2em]"
                    style={{ color: selectedAgent.color }}
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
