import { useMemo, useState } from 'react';
import { useParams } from 'react-router-dom';

import { useLineage } from '@/api/hooks';
import { LineageViewer } from '@/components/lineage/lineage-viewer';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import type { LineageNode } from '@/data/fixtures';

function hasOverride(node: LineageNode): boolean {
  if (node.overridden) return true;
  return node.children?.some(hasOverride) ?? false;
}

/**
 * `/lineage/:lineageId` — Decision audit trail (W4). Renders the lineage tree
 * with search, expand/collapse, copy-path, and override badges.
 */
export function LineageDetailPage() {
  const { lineageId } = useParams<{ lineageId: string }>();
  const lineage = useLineage(lineageId ?? '');
  const [search, setSearch] = useState('');

  const data = lineage.data;
  const overridden = useMemo(() => (data ? hasOverride(data.root) : false), [data]);

  if (!lineageId) {
    return (
      <div className="p-4">
        <p className="text-sm text-text-secondary">No lineage id provided.</p>
      </div>
    );
  }

  if (lineage.isLoading) {
    return (
      <div className="p-4">
        <p className="text-sm text-text-secondary">Loading lineage…</p>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="p-4">
        <p className="text-sm text-text-secondary">Lineage not found.</p>
      </div>
    );
  }

  return (
    <div className="mx-auto w-full max-w-[1200px] space-y-4 p-4">
      <header className="flex items-baseline justify-between">
        <div>
          <h1 className="text-lg font-semibold text-text-primary">Lineage {lineageId}</h1>
          <p className="text-sm text-text-secondary">
            {data.run_id} · {data.workflow_id} · {data.model}
          </p>
        </div>
      </header>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>Decision tree</CardTitle>
            <CardDescription>
              Audit trail for the proposal that produced this lineage.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <LineageViewer root={data.root} search={search} />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Summary</CardTitle>
          </CardHeader>
          <CardContent>
            <dl className="grid grid-cols-1 gap-4">
              <div>
                <dt className="text-[11px] uppercase tracking-wider text-text-secondary">Run</dt>
                <dd className="font-mono text-sm text-text-primary">{data.run_id}</dd>
              </div>
              <div>
                <dt className="text-[11px] uppercase tracking-wider text-text-secondary">
                  Workflow
                </dt>
                <dd className="font-mono text-sm text-text-primary">{data.workflow_id}</dd>
              </div>
              <div>
                <dt className="text-[11px] uppercase tracking-wider text-text-secondary">Model</dt>
                <dd className="font-mono text-sm text-text-primary">{data.model}</dd>
              </div>
              <div>
                <dt className="text-[11px] uppercase tracking-wider text-text-secondary">Cost</dt>
                <dd className="font-mono text-sm tabular-nums text-text-primary">
                  ${data.cost_usd.toFixed(2)}
                </dd>
              </div>
              <div>
                <dt className="text-[11px] uppercase tracking-wider text-text-secondary">
                  Created
                </dt>
                <dd className="font-mono text-sm text-text-primary">
                  {new Date(data.created_at).toISOString()}
                </dd>
              </div>
              {overridden && (
                <div>
                  <dt className="text-[11px] uppercase tracking-wider text-text-secondary">
                    Override
                  </dt>
                  <dd>
                    <Badge tone="danger" label="override present" />
                  </dd>
                </div>
              )}
            </dl>

            <div className="mt-4">
              <label
                htmlFor="lineage-search"
                className="text-[11px] uppercase tracking-wider text-text-secondary"
              >
                Filter tree
              </label>
              <input
                id="lineage-search"
                type="text"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search label, detail, or path"
                className="mt-1 w-full rounded-chip border border-border-subtle bg-bg-base px-2 py-1.5 text-xs text-text-primary placeholder:text-text-tertiary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
                data-testid="lineage-search"
              />
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
