import { NumericText } from '@/components/ui/numeric-text';

interface Gauge {
  label: string;
  value: number;
  cap: number;
  tone: 'ok' | 'warn' | 'danger';
  suffix: string;
}

const GAUGES: Gauge[] = [
  { label: 'Exposure', value: 8.2, cap: 15, tone: 'ok', suffix: '%' },
  { label: 'Leverage', value: 2.1, cap: 5, tone: 'ok', suffix: 'x' },
  { label: 'Drawdown', value: 4.1, cap: 6, tone: 'warn', suffix: '%' },
  { label: 'Margin used', value: 63, cap: 100, tone: 'warn', suffix: '%' },
];

const TONE_HEX: Record<Gauge['tone'], string> = {
  ok: 'bg-up',
  warn: 'bg-warn',
  danger: 'bg-danger',
};

/**
 * Risk gauges (W1 right-panel + risk workspace): fixed fixture values in
 * demo mode; swap for the risk store once Phase 9 pushes risk telemetry.
 */
export function RiskGauges() {
  return (
    <div className="grid grid-cols-2 gap-x-4 gap-y-3" data-testid="risk-gauges">
      {GAUGES.map(({ label, value, cap, tone, suffix }) => {
        const pct = Math.min(100, (value / cap) * 100);
        return (
          <div key={label}>
            <div className="mb-1 flex items-baseline justify-between">
              <span className="text-[11px] uppercase tracking-wider text-text-secondary">
                {label}
              </span>
              <span className="font-mono text-sm tabular-nums text-text-primary">
                {value}
                {suffix}
                <span className="text-text-tertiary">
                  {' '}
                  / {cap}
                  {suffix}
                </span>
              </span>
            </div>
            <div className="h-1.5 w-full overflow-hidden rounded-full bg-bg-raised" aria-hidden>
              <div
                className={`h-full rounded-full ${TONE_HEX[tone]}`}
                style={{ width: `${pct}%` }}
              />
            </div>
          </div>
        );
      })}
      <div className="col-span-2 flex items-baseline justify-between border-t border-border-subtle pt-2">
        <span className="text-[11px] uppercase tracking-wider text-text-secondary">
          Net P&L (session)
        </span>
        <NumericText value={1_284.5} decimals={2} showSign tone="up" />
      </div>
    </div>
  );
}
