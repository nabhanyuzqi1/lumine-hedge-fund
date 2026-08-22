import * as React from "react";

import { Badge } from "@/components/ui/badge";
import type { JournalEntry, JournalKind } from "@/data/fixtures";

const KIND_TONE: Record<JournalKind, "info" | "ok" | "warn" | "danger" | "neutral"> = {
  decision: "info",
  trade: "ok",
  risk: "warn",
  note: "neutral",
};

/** 22 Aug 2026: badge arah keputusan (BUY/SELL/HOLD) — user: "tiap record
 * ga ada alasan sell buy, hold". Color-coded agar mudah dipindai. */
const DECISION_TONE: Record<string, "ok" | "danger" | "neutral" | "info" | "warn"> = {
  BUY: "ok",
  LONG: "ok",
  SELL: "danger",
  SHORT: "danger",
  HOLD: "neutral",
  CANCEL: "warn",
  REJECT: "warn",
};

/** Book label: portfolio_id "default" → REAL (akun MT5 live), "paper" →
 * PAPER (simulasi/sandbox), lainnya tampil apa adanya. */
function bookLabel(portfolioId: string | undefined): string {
  if (!portfolioId) return "-";
  if (portfolioId === "default") return "REAL";
  if (portfolioId === "paper") return "PAPER";
  return portfolioId.toUpperCase();
}

function decisionLabel(entry: JournalEntry): string {
  if (entry.decision) return entry.decision.toUpperCase();
  if (entry.side) return entry.side.toUpperCase();
  return "-";
}

interface JournalTableProps {
  entries: JournalEntry[];
  expandedId?: string | null;
  onRowClick?: (entry: JournalEntry) => void;
}

export function JournalTable({ entries, expandedId, onRowClick }: JournalTableProps) {
  return (
    <div
      className="overflow-x-auto rounded-panel border border-border-subtle"
      data-testid="journal-table-wrapper"
    >
      <table className="w-full min-w-[640px] text-left text-xs" data-testid="journal-table">
        <thead className="bg-bg-overlay text-text-secondary">
          <tr>
            <th className="px-3 py-2 font-medium">Timestamp</th>
            <th className="px-3 py-2 font-medium">Book</th>
            <th className="px-3 py-2 font-medium">Decision</th>
            <th className="px-3 py-2 font-medium">Symbol</th>
            <th className="px-3 py-2 font-medium">Kind</th>
            <th className="px-3 py-2 font-medium">Actor</th>
            <th className="px-3 py-2 font-medium">Summary</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-border-subtle">
          {entries.map((entry) => {
            const expanded = expandedId === entry.id;
            const decision = decisionLabel(entry);
            return (
              <React.Fragment key={entry.id}>
                <tr
                  className="cursor-pointer hover:bg-bg-overlay/50"
                  onClick={() => onRowClick?.(entry)}
                  data-testid={`journal-row-${entry.id}`}
                >
                  <td className="whitespace-nowrap px-3 py-2 font-mono text-text-secondary">
                    {new Date(entry.timestamp).toISOString()}
                  </td>
                  <td className="px-3 py-2">
                    <Badge
                      tone={entry.portfolio_id === "paper" ? "warn" : "info"}
                      label={bookLabel(entry.portfolio_id)}
                    />
                  </td>
                  <td className="px-3 py-2">
                    <Badge tone={DECISION_TONE[decision] ?? "neutral"} label={decision} />
                  </td>
                  <td className="px-3 py-2 font-mono text-text-primary">{entry.symbol ?? "-"}</td>
                  <td className="px-3 py-2">
                    <Badge tone={KIND_TONE[entry.kind]} label={entry.kind} />
                  </td>
                  <td className="px-3 py-2 text-text-primary">{entry.actor}</td>
                  <td className="max-w-[260px] truncate px-3 py-2 text-text-primary" title={entry.summary}>
                    {entry.summary}
                  </td>
                </tr>
                {expanded && (
                  <tr key={`${entry.id}-detail`} className="bg-bg-overlay/30">
                    <td colSpan={7} className="px-3 py-2">
                      <dl className="grid grid-cols-2 gap-2 sm:grid-cols-4">
                        <div>
                          <dt className="text-[10px] uppercase tracking-wider text-text-secondary">
                            ID
                          </dt>
                          <dd className="font-mono text-text-primary">{entry.id}</dd>
                        </div>
                        <div>
                          <dt className="text-[10px] uppercase tracking-wider text-text-secondary">
                            Portfolio
                          </dt>
                          <dd className="font-mono text-text-primary">{bookLabel(entry.portfolio_id)}</dd>
                        </div>
                        {entry.linked_lineage_id && (
                          <div>
                            <dt className="text-[10px] uppercase tracking-wider text-text-secondary">
                              Lineage
                            </dt>
                            <dd className="font-mono text-text-primary">
                              {entry.linked_lineage_id}
                            </dd>
                          </div>
                        )}
                        <div>
                          <dt className="text-[10px] uppercase tracking-wider text-text-secondary">
                            Timestamp
                          </dt>
                          <dd className="font-mono text-xs text-text-primary">
                            {new Date(entry.timestamp).toISOString()}
                          </dd>
                        </div>
                      </dl>
                      {entry.reason ? (
                        <div className="mt-3 rounded-md border border-border-subtle bg-bg-base/60 p-3">
                          <dt className="mb-1 text-[10px] font-medium uppercase tracking-wider text-accent">
                            AI Reasoning — kenapa {decision}
                          </dt>
                          <dd className="text-sm leading-relaxed text-text-primary">
                            {entry.reason}
                          </dd>
                        </div>
                      ) : (
                        <div className="mt-3 rounded-md border border-dashed border-border-subtle bg-bg-base/40 p-3">
                          <dt className="mb-1 text-[10px] font-medium uppercase tracking-wider text-text-secondary">
                            AI Reasoning
                          </dt>
                          <dd className="text-xs italic text-text-secondary">
                            Tidak ada alasan tercatat untuk entri ini (workflow/order belum
                            menyimpan rationale).
                          </dd>
                        </div>
                      )}
                      {entry.lesson && (
                        <div className="mt-2 rounded-md border border-border-subtle bg-bg-base/60 p-3">
                          <dt className="mb-1 text-[10px] font-medium uppercase tracking-wider text-text-secondary">
                            Lesson / Follow-up
                          </dt>
                          <dd className="text-sm leading-relaxed text-text-primary">
                            {entry.lesson}
                          </dd>
                        </div>
                      )}
                    </td>
                  </tr>
                )}
              </React.Fragment>
            );
          })}
        </tbody>
      </table>
      {entries.length === 0 && (
        <div className="p-4 text-center text-sm text-text-secondary">
          No journal entries match the filters.
        </div>
      )}
    </div>
  );
}
