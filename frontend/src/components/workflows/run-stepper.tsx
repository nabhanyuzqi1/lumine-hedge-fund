import { Badge } from "@/components/ui/badge";
import {
  RUN_STAGES,
  RUN_TERMINAL_STATES,
  type RunStage,
  type RunStageEvent,
  type RunStatus,
  type RunTerminalState,
} from "@/data/fixtures";

const STAGE_LABEL: Record<RunStage, string> = {
  init: "Init",
  data_gathering: "Data gathering",
  analyst_outputs: "Analyst outputs",
  debate: "Debate",
  ic_decision: "IC decision",
  cio_proposal: "CIO proposal",
  risk_assessment: "Risk assessment",
  sizing: "Sizing",
  order_draft: "Order draft",
  execution: "Execution",
  journal: "Journal",
};

const TERMINAL_TONE: Record<RunTerminalState, "ok" | "danger" | "warn" | "danger"> = {
  completed: "ok",
  failed: "danger",
  cancelled: "warn",
  killed: "danger",
};

interface Props {
  status: RunStatus;
  stages: RunStageEvent[];
}

export function RunStepper({ status, stages }: Props) {
  const isTerminal = (RUN_TERMINAL_STATES as readonly string[]).includes(status);
  const terminalState = isTerminal ? (status as RunTerminalState) : null;
  const finalStage = stages.at(-1)?.stage;
  const finalStageIndex = finalStage ? RUN_STAGES.indexOf(finalStage) : -1;
  const activeStageIndex = isTerminal ? finalStageIndex : RUN_STAGES.indexOf(status as RunStage);

  const tsFor = (stage: RunStage) => stages.find((s) => s.stage === stage)?.timestamp;

  return (
    <div className="relative pl-3" data-testid="run-stepper">
      <div className="absolute bottom-2 left-[11px] top-2 w-px bg-border-subtle" aria-hidden />
      <ol className="space-y-3">
        {RUN_STAGES.map((stage, i) => {
          const done = i <= activeStageIndex;
          const isActive = i === activeStageIndex && !isTerminal;
          const ts = tsFor(stage);
          return (
            <li key={stage} className="relative flex items-start gap-3">
              <span
                className={`z-10 mt-1.5 h-2 w-2 rounded-full border border-bg-raised ${
                  done ? "bg-accent" : "bg-border-subtle"
                } ${isActive ? "ring-2 ring-accent/40" : ""}`}
                aria-hidden
              />
              <div className="flex flex-1 items-baseline justify-between gap-2">
                <span
                  className={`text-xs font-medium ${
                    isActive
                      ? "text-text-primary"
                      : done
                        ? "text-text-secondary"
                        : "text-text-tertiary"
                  }`}
                >
                  {STAGE_LABEL[stage]}
                </span>
                {ts && (
                  <span className="font-mono text-[10px] tabular-nums text-text-tertiary">
                    {new Date(ts).toISOString().slice(11, 19)}Z
                  </span>
                )}
              </div>
            </li>
          );
        })}
        {terminalState && (
          <li className="relative flex items-start gap-3">
            <span
              className="z-10 mt-1.5 h-2 w-2 rounded-full border border-bg-raised bg-danger ring-2 ring-danger/40"
              aria-hidden
            />
            <div className="flex flex-1 items-center justify-between gap-2">
              <span className="text-xs font-medium text-text-primary">{terminalState}</span>
              <Badge tone={TERMINAL_TONE[terminalState]} label={terminalState} />
            </div>
          </li>
        )}
      </ol>
    </div>
  );
}
