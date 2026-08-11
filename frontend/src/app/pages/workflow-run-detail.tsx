import { useParams } from 'react-router-dom';

import { useRun } from '@/api/hooks';
import { CommitteeFeed } from '@/components/terminal/committee-feed';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { NumericText } from '@/components/ui/numeric-text';
import { RunStepper } from '@/components/workflows/run-stepper';
import { RUN_TERMINAL_STATES } from '@/data/fixtures';

const TERMINAL_TONE = {
  completed: 'ok',
  failed: 'danger',
  cancelled: 'warn',
  killed: 'danger',
} as const;

export function WorkflowRunDetailPage() {
  const { workflowId, runId } = useParams<{ workflowId: string; runId: string }>();
  const run = useRun(runId ?? '');
  const data = run.data;

  const isTerminal = data
    ? (RUN_TERMINAL_STATES as readonly string[]).includes(data.status)
    : false;

  if (!runId) {
    return (
      <div className="p-4">
        <p className="text-sm text-text-secondary">No run id provided.</p>
      </div>
    );
  }

  if (run.isLoading) {
    return (
      <div className="p-4">
        <p className="text-sm text-text-secondary">Loading run…</p>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="p-4">
        <p className="text-sm text-text-secondary">Run not found.</p>
      </div>
    );
  }

  return (
    <div className="mx-auto w-full max-w-[1200px] space-y-4 p-4">
      <header className="flex items-baseline justify-between">
        <div>
          <h1 className="text-lg font-semibold text-text-primary">Run {runId}</h1>
          <p className="text-sm text-text-secondary">
            {data.workflow_name} · {workflowId}
          </p>
        </div>
      </header>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>Run summary</CardTitle>
            <CardDescription>
              <Badge
                tone={
                  isTerminal ? TERMINAL_TONE[data.status as keyof typeof TERMINAL_TONE] : 'info'
                }
                label={data.status}
              />{' '}
              <span className="text-text-secondary">{data.model}</span>
            </CardDescription>
          </CardHeader>
          <CardContent>
            <dl className="grid grid-cols-2 gap-4 sm:grid-cols-4">
              <div>
                <dt className="text-[11px] uppercase tracking-wider text-text-secondary">Cost</dt>
                <dd className="font-mono text-sm tabular-nums text-text-primary">
                  $<NumericText value={data.cost_usd} decimals={2} tone="neutral" />
                </dd>
              </div>
              <div>
                <dt className="text-[11px] uppercase tracking-wider text-text-secondary">
                  Started
                </dt>
                <dd className="font-mono text-sm tabular-nums text-text-primary">
                  {new Date(data.started_at).toISOString()}
                </dd>
              </div>
              {data.completed_at && (
                <div>
                  <dt className="text-[11px] uppercase tracking-wider text-text-secondary">
                    Completed
                  </dt>
                  <dd className="font-mono text-sm tabular-nums text-text-primary">
                    {new Date(data.completed_at).toISOString()}
                  </dd>
                </div>
              )}
              {data.error && (
                <div className="col-span-2">
                  <dt className="text-[11px] uppercase tracking-wider text-text-secondary">
                    Error
                  </dt>
                  <dd className="text-sm text-danger">{data.error}</dd>
                </div>
              )}
            </dl>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Progress</CardTitle>
          </CardHeader>
          <CardContent>
            <RunStepper status={data.status} stages={data.stages} />
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Committee activity</CardTitle>
          <CardDescription>Filtered run: {runId}</CardDescription>
        </CardHeader>
        <CardContent>
          <CommitteeFeed workflowRunId={runId} limit={20} />
        </CardContent>
      </Card>
    </div>
  );
}
