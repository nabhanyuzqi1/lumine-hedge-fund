import { useEffect, useRef, useState } from "react";

/*
 * The Console — signature element of the page.
 * It plays the actual critical path of the system (see ARCHITECTURE.md)
 * as a staged pipeline readout, so the "LLMs reason, deterministic code
 * executes" story is the first thing a visitor sees.
 *
 * Stage state: 'pending' | 'active' | 'done' | 'veto'
 */

const BASE = Date.UTC(2026, 7, 7, 9, 30, 0);

function stamp(cycle, offset) {
  const t = new Date(BASE + cycle * 90000 + offset * 3700);
  return t.toISOString().slice(11, 19);
}

const STAGES = [
  { id: "dispatch", label: "scheduler", detail: "dispatch trade-core" },
  {
    id: "committee",
    label: "llm.committee",
    detail: "4 analysts · debate · IC · CIO proposal",
  },
  { id: "risk", label: "risk.validator", detail: "deterministic veto — no LLM above this line" },
  { id: "sizing", label: "portfolio.sizer", detail: "position size · exposure bounds" },
  {
    id: "exec",
    label: "execution.router",
    detail: "BEGIN TX · insert lineage_records · COMMIT · publish mt5.commands",
  },
  {
    id: "bridge",
    label: "mt5.bridge",
    detail: "fill · listener · UPDATE positions / INSERT fills",
  },
];

export default function Console() {
  const [cycle, setCycle] = useState(1);
  const [stage, setStage] = useState(0);
  const [vetoed, setVetoed] = useState(false);
  const vetoRoll = useRef(0);

  useEffect(() => {
    const tick = window.setInterval(() => {
      const len = vetoed ? 1 : STAGES.length;
      setStage((s) => {
        if (s + 1 < len) return s + 1;
        const roll = (vetoRoll.current = (vetoRoll.current + 3) % 5);
        setVetoed(roll === 0);
        setCycle((c) => c + 1);
        return 0;
      });
    }, 1500);
    return () => window.clearInterval(tick);
  }, [vetoed]);

  const len = vetoed ? 1 : STAGES.length;
  const shown = STAGES.slice(0, len);

  const statusOf = (i) => {
    if (i < stage) return "done";
    if (i === stage) return vetoed ? "veto" : "active";
    return "pending";
  };

  return (
    <div className="overflow-hidden rounded-[var(--radius-panel)] bg-abyss shadow-[var(--shadow-panel)]">
      {/* header */}
      <div className="flex items-center gap-3 border-b border-line px-4 py-3">
        <span className="flex gap-1.5" aria-hidden="true">
          <span className="size-2.5 rounded-full bg-down/70" />
          <span className="size-2.5 rounded-full bg-warn/70" />
          <span className="size-2.5 rounded-full bg-up/70" />
        </span>
        <span className="font-mono text-[11px] text-ink-dim">
          lumine · trade-core — cycle{" "}
          <span className="text-ink">{String(cycle).padStart(3, "0")}</span>
        </span>
        <span className="ml-auto inline-flex items-center gap-1.5 font-mono text-[11px] text-up">
          <span className="size-1.5 animate-pulse rounded-full bg-up" aria-hidden="true" />
          live
        </span>
      </div>

      {/* body */}
      <div className="console-scroll max-h-[380px] overflow-y-auto px-4 py-4 font-mono text-[11.5px] leading-relaxed sm:max-h-[420px]">
        <p className="text-ink-faint">
          <span className="text-accent">$</span> cycle {String(cycle).padStart(3, "0")} · session
          opened <span className="text-ink-dim">09:30:00 UTC</span>
        </p>

        {shown.map((s, i) => {
          const st = statusOf(i);
          const when = stamp(cycle, i);
          const done = st === "done";
          const active = st === "active";
          const veto = st === "veto";
          const color = veto
            ? "var(--color-down)"
            : done
              ? "var(--color-up)"
              : active
                ? "var(--color-cyan)"
                : "var(--color-ink-faint)";
          const marker = veto ? "✗" : done ? "✓" : active ? "▸" : "·";
          return (
            <p
              key={`${cycle}-${s.id}`}
              className="console-line flex gap-2.5"
              style={{ animationDelay: `${i * 90}ms`, color }}
            >
              <span className="shrink-0 text-ink-faint">{when}</span>
              <span className="shrink-0 w-3 text-center">{marker}</span>
              <span className="truncate">
                <span className="text-accent">{s.label}</span>
                <span className="text-ink-faint"> — </span>
                {s.detail}
                {veto && <span className="text-down"> — safe state by default</span>}
                {active && <span className="console-cursor ml-1 text-ink-dim">▌</span>}
              </span>
            </p>
          );
        })}

        {!vetoed && (
          <p
            className="console-line mt-3 flex gap-2.5 text-ink-faint"
            style={{ animationDelay: `${shown.length * 90}ms` }}
          >
            <span className="shrink-0">{stamp(cycle, shown.length)}</span>
            <span className="shrink-0 w-3 text-center">·</span>
            <span>waiting for next market event…</span>
          </p>
        )}
      </div>

      {/* footer strip */}
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 border-t border-line px-4 py-2.5 font-mono text-[10.5px] text-ink-faint">
        <span>model gpt-5.6 · policy v14.2.1</span>
        <span>lineage {String(cycle * 3 + 2)} records</span>
        <span className="text-up">risk gate: enabled</span>
      </div>
    </div>
  );
}
