import { useMemo } from 'react';

interface HealthStatus {
  status: 'ok' | 'degraded';
  apiVersion: string;
  checkedAt: string;
}

/** Portal liveness check (F-Sprint 1 placeholder; API probe lands in F-Sprint 3). */
export function HealthPage() {
  const health = useMemo<HealthStatus>(
    () => ({
      status: 'ok',
      apiVersion: 'v1',
      checkedAt: new Date().toISOString(),
    }),
    [],
  );

  return (
    <main className="flex min-h-screen flex-col items-center justify-center bg-abyss text-ink">
      <div className="flex flex-col items-center gap-6">
        <p className="font-mono text-sm text-ink-faint">LUMINE PORTAL</p>
        <h1 className="font-display text-3xl font-semibold tracking-tight">System health</h1>
        <dl className="flex flex-col items-center gap-2 font-mono text-sm">
          <div className="flex items-center gap-3">
            <span
              data-testid="health-status"
              className={`h-2.5 w-2.5 rounded-full ${health.status === 'ok' ? 'bg-up' : 'bg-warn'}`}
            />
            <dt className="text-ink-dim">status</dt>
            <dd className="text-ink">{health.status}</dd>
          </div>
          <div className="flex items-center gap-3">
            <dt className="text-ink-dim">api</dt>
            <dd className="text-ink">{health.apiVersion}</dd>
          </div>
          <div className="flex items-center gap-3">
            <dt className="text-ink-dim">checked</dt>
            <dd className="text-ink">{health.checkedAt}</dd>
          </div>
        </dl>
      </div>
    </main>
  );
}
