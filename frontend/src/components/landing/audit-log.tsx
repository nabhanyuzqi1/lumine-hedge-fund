import { motion } from "framer-motion";
import { useEffect, useRef, useState } from "react";
import { cn } from "@/lib/utils";
import { useTranslation } from "react-i18next";
import { SAMPLE_TRADE_AUDIT } from "@/data/landing/trades";

/**
 * AuditLog — Section 25 of UI/UX Rebuild V2.
 * Terminal-style audit stream. Entries appear live; the user can
 * pause/resume. Every decision leaves a trace.
 * SIMULATED data.
 */

interface StreamEntry {
  ts: string;
  source: string;
  signal: string;
  kind: "agent" | "master" | "risk" | "exec";
}

const STREAM: StreamEntry[] = [
  { ts: "14:32:08", source: "TECHNICAL", signal: "BULLISH", kind: "agent" },
  { ts: "14:32:08", source: "MACRO", signal: "BULLISH", kind: "agent" },
  { ts: "14:32:09", source: "NEWS", signal: "NEUTRAL", kind: "agent" },
  { ts: "14:32:09", source: "STRUCTURE", signal: "BULLISH", kind: "agent" },
  { ts: "14:32:10", source: "MASTER", signal: "LONG", kind: "master" },
  { ts: "14:32:10", source: "RISK", signal: "APPROVED", kind: "risk" },
  { ts: "14:32:11", source: "EXECUTION", signal: "READY", kind: "exec" },
  { ts: "14:32:12", source: "POSITION", signal: "OPEN @ 3350.20", kind: "exec" },
  { ts: "14:32:14", source: "TECHNICAL", signal: "MOMENTUM: STRONG", kind: "agent" },
  { ts: "14:32:15", source: "RISK", signal: "EXPOSURE: 1.2%", kind: "risk" },
  { ts: "14:32:18", source: "STRUCTURE", signal: "HOLD SL", kind: "agent" },
  { ts: "14:32:22", source: "MASTER", signal: "THESIS: BULLISH", kind: "master" },
];

const KIND_COLORS: Record<StreamEntry["kind"], string> = {
  agent: "#A7B3C5",
  master: "#4D8DFF",
  risk: "#FFB020",
  exec: "#34D399",
};

interface AuditLogProps {
  className?: string;
  showHeader?: boolean;
}

export function AuditLog({ className, showHeader = true }: AuditLogProps) {
  const { t } = useTranslation();
  const audit = SAMPLE_TRADE_AUDIT;
  const [count, setCount] = useState(7);
  const [playing, setPlaying] = useState(true);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    if (playing) {
      timerRef.current = setInterval(() => {
        setCount((c) => (c >= STREAM.length ? 4 : c + 1));
      }, 900);
    }
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [playing]);

  const getBiasColor = (bias: string) => {
    if (bias === "BULLISH" || bias === "LONG" || bias === "APPROVED" || bias === "READY" || bias === "HOLD SL") return "text-up";
    if (bias === "BEARISH") return "text-down";
    return "text-ink-dim";
  };

  return (
    <div className={cn("mx-auto w-full max-w-4xl space-y-6", className)}>
      {showHeader && (
        <div className="space-y-3 text-center">
          <div className="flex items-center justify-center gap-2">
            <div className="h-px w-12 bg-gradient-to-r from-transparent to-accent" />
            <span className="font-mono text-[10px] uppercase tracking-widest text-accent">
                          {t("audit.auditability")}
                        </span>
                        <div className="h-px w-12 bg-gradient-to-l from-transparent to-accent" />
                      </div>
                      <h3 className="font-display text-2xl font-bold text-ink md:text-3xl">
                        {t("audit.traceTitle")}
                      </h3>
                      <p className="mx-auto max-w-2xl text-sm leading-relaxed text-ink-dim">
                        {t("audit.traceDescription")}
                      </p>
        </div>
      )}

      {/* Terminal window */}
      <motion.div
        className="overflow-hidden rounded-panel border shadow-lg backdrop-blur-xl"
        style={{
          backgroundColor: "var(--glass-bg)",
          borderColor: "var(--glass-border)",
          boxShadow: "var(--glass-shadow)",
        }}
        initial={{ opacity: 0, y: 28 }}
        whileInView={{ opacity: 1, y: 0 }}
        viewport={{ once: true, margin: "-60px" }}
        transition={{ duration: 0.7, ease: "easeOut" }}
      >
        {/* Terminal header */}
        <div className="flex items-center justify-between border-b border-line-soft bg-raised/40 px-4 py-2.5 backdrop-blur-sm">
          <div className="flex items-center gap-2">
            <span className="h-2.5 w-2.5 rounded-full bg-down/70" />
            <span className="h-2.5 w-2.5 rounded-full bg-warn/70" />
            <span className="h-2.5 w-2.5 rounded-full bg-up/70" />
            <span className="ml-3 font-mono text-[10px] uppercase tracking-widest text-ink-faint">
              lumine://audit-trail
            </span>
          </div>
          {/* Pause / Resume */}
          <button
            type="button"
            onClick={() => setPlaying((p) => !p)}
            className={cn(
              "flex items-center gap-1.5 rounded-chip border px-2.5 py-1 font-mono text-[9px] font-semibold uppercase tracking-widest transition-colors",
              playing
                ? "border-line-soft bg-abyss text-ink-dim hover:text-ink"
                : "border-accent/40 bg-accent/10 text-accent"
            )}
          >
            <span className="text-[10px] leading-none">{playing ? "❚❚" : "▶"}</span>
                        {playing ? t("audit.pause") : t("audit.resume")}
                      </button>
        </div>

        {/* Stream body */}
        <div className="h-[300px] overflow-hidden p-4 font-mono text-xs md:p-5">
          <div className="flex items-center gap-2 border-b border-line-soft/50 pb-2">
            <span
              className={cn(
                "h-1.5 w-1.5 rounded-full",
                playing ? "animate-pulse bg-up" : "bg-warn"
              )}
            />
            <span
              className={cn(
                "text-[9px] font-semibold uppercase tracking-[0.2em]",
                playing ? "text-up" : "text-warn"
              )}
            >
              {playing ? t("audit.live") : t("audit.paused")}
                          </span>
          </div>

          <div className="mt-3 space-y-1.5">
            {STREAM.slice(0, count).map((entry, i) => {
              const isNew = i >= STREAM.slice(0, count).length - 1;
              return (
                <motion.div
                  key={`${entry.ts}-${entry.source}-${i}`}
                  className="flex items-center gap-3 whitespace-nowrap"
                  initial={{ opacity: 0, x: -8 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ duration: 0.25 }}
                >
                  <span className="text-ink-faint">{entry.ts}</span>
                  <span style={{ color: KIND_COLORS[entry.kind] }} className="w-24 shrink-0">
                    {entry.source}
                  </span>
                  <span className={cn("font-semibold", getBiasColor(entry.signal))}>
                    {entry.signal}
                  </span>
                  {isNew && playing && (
                    <span className="ml-1 h-1 w-1 animate-ping rounded-full bg-accent" />
                  )}
                </motion.div>
              );
            })}
          </div>
        </div>

        {/* Footer: trade fingerprint */}
        <div className="border-t border-line-soft bg-raised/40 px-4 py-3 md:px-5">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="font-mono text-[10px] uppercase tracking-widest text-ink-faint">
                          {t("audit.trade")} <span className="text-accent">{audit.tradeId}</span>
                        </div>
                        <div className="flex gap-4 font-mono text-[10px] text-ink-dim">
                          <span>
                            {t("audit.entry")} <span className="text-ink">{audit.entry.toFixed(2)}</span>
                          </span>
                          <span>
                            {t("audit.stop")} <span className="text-ink">{audit.stop.toFixed(2)}</span>
                          </span>
                          <span>
                            {t("audit.target")} <span className="text-ink">{audit.target.toFixed(2)}</span>
                          </span>
                        </div>
          </div>
        </div>
      </motion.div>

      <div className="rounded-chip border border-accent/30 bg-accent/5 p-4 backdrop-blur">
              <p className="text-center text-xs leading-relaxed text-ink-dim">
                <span className="font-semibold text-accent">
                  {t("audit.auditNote")}
                </span>{" "}
                {t("audit.auditNoteText")}
              </p>
            </div>
    </div>
  );
}
