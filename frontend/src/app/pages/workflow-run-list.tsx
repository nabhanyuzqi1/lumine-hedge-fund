import { useState } from "react";
import { Link } from "react-router-dom";

import { useWorkflowRuns } from "@/api/hooks";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

const PAGE_SIZE = 20;

const STATUS_TONE: Record<string, "ok" | "warn" | "danger" | "neutral"> = {
  completed: "ok",
  running: "warn",
  init: "neutral",
  data_gathering: "warn",
  failed: "danger",
  rejected: "danger",
};

function formatTs(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toISOString().slice(0, 19).replace("T", " ");
}

/**
 * Paginated workflow run list (F-01). Data: useWorkflowRuns (REST-first,
 * fixture fallback). Navigates to the run detail route.
 */
export function WorkflowRunListPage() {
  const [offset, setOffset] = useState(0);
  const { data, isPending, isError } = useWorkflowRuns(PAGE_SIZE, offset);

  return (
    <div className="space-y-4 p-4" data-testid="workflow-run-list-page">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold text-text-primary">Workflow Runs</h1>
          <p className="text-xs text-text-tertiary">
            Decision-cycle executions across books and symbols
          </p>
        </div>
        <span className="font-mono text-xs text-text-secondary" data-testid="run-total">
          {data ? `${data.total} total` : "…"}
        </span>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Runs</CardTitle>
          <CardDescription>Latest first — {PAGE_SIZE} per page</CardDescription>
        </CardHeader>
        <CardContent>
          {isPending && <p className="py-6 text-center text-sm text-text-tertiary">Loading runs…</p>}
          {isError && (
            <p className="py-6 text-center text-sm text-danger" role="alert">
              Failed to load workflow runs.
            </p>
          )}
          {data && (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm" data-testid="runs-table">
              <thead className="border-b border-border-subtle text-xs text-text-tertiary">
                <tr>
                  <th className="py-2 pr-3 font-medium">Run</th>
                  <th className="py-2 pr-3 font-medium">Workflow</th>
                  <th className="py-2 pr-3 font-medium">Status</th>
                  <th className="py-2 pr-3 font-medium">Started</th>
                  <th className="py-2 pr-3 font-medium">Finished</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((run) => (
                  <tr
                    key={run.id}
                    className="border-b border-border-subtle/60 hover:bg-bg-overlay"
                  >
                    <td className="py-2 pr-3">
                      <Link
                        to={`/workflows/${encodeURIComponent(run.workflow_id)}/runs/${encodeURIComponent(run.id)}`}
                        className="font-mono text-accent hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
                      >
                        {run.id.slice(0, 12)}
                      </Link>
                    </td>
                    <td className="py-2 pr-3 text-text-secondary">{run.workflow_name}</td>
                    <td className="py-2 pr-3">
                      <Badge tone={STATUS_TONE[run.status] ?? "neutral"} label={run.status} />
                    </td>
                    <td className="py-2 pr-3 font-mono text-xs text-text-secondary">
                      {formatTs(run.started_at)}
                    </td>
                    <td className="py-2 pr-3 font-mono text-xs text-text-secondary">
                      {formatTs(run.completed_at ?? null)}
                    </td>
                  </tr>
                ))}
              </tbody>
              </table>
            </div>
          )}

          <div className="flex items-center justify-end gap-2 pt-3">
            <button
              type="button"
              disabled={offset === 0}
              onClick={() => setOffset((o) => Math.max(0, o - PAGE_SIZE))}
              className="rounded-chip border border-border-subtle px-3 py-1 text-xs text-text-secondary hover:bg-bg-overlay disabled:opacity-40"
            >
              Prev
            </button>
            <span className="font-mono text-xs text-text-secondary">
              {offset / PAGE_SIZE + 1}
            </span>
            <button
              type="button"
              disabled={!data || offset + PAGE_SIZE >= data.total}
              onClick={() => setOffset((o) => o + PAGE_SIZE)}
              className="rounded-chip border border-border-subtle px-3 py-1 text-xs text-text-secondary hover:bg-bg-overlay disabled:opacity-40"
            >
              Next
            </button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
