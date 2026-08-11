import { Badge } from '@/components/ui/badge';
import type { OrderLifecycleEvent, OrderStatus } from '@/data/fixtures';

const ORDER_STATUS_SEQUENCE: OrderStatus[] = [
  'RECEIVED',
  'VALIDATED',
  'RISK_CHECK',
  'ACTIVE',
  'FILLED',
];
const TERMINAL_STATUSES: OrderStatus[] = ['CANCELLED', 'REJECTED'];

interface Props {
  status: OrderStatus;
  lifecycle: OrderLifecycleEvent[];
}

export function OrderLifecycleTimeline({ status, lifecycle }: Props) {
  const isTerminal = TERMINAL_STATUSES.includes(status);

  const states: OrderStatus[] = isTerminal
    ? [...ORDER_STATUS_SEQUENCE.filter((s) => s !== 'FILLED'), status]
    : ORDER_STATUS_SEQUENCE;

  const timestampFor = (state: OrderStatus) =>
    lifecycle.find((ev) => ev.status === state)?.timestamp;

  const activeIndex = states.findIndex((s) => s === status);

  return (
    <div className="relative pl-3" data-testid="order-lifecycle-timeline">
      <div className="absolute bottom-2 left-[11px] top-2 w-px bg-border-subtle" aria-hidden />
      <ol className="space-y-4">
        {states.map((state, i) => {
          const done = i <= activeIndex;
          const isActive = state === status;
          const ts = timestampFor(state);
          return (
            <li key={state} className="relative flex items-start gap-3">
              <span
                className={`z-10 mt-1.5 h-2 w-2 rounded-full border border-bg-raised ${
                  done ? 'bg-accent' : 'bg-border-subtle'
                } ${isActive ? 'ring-2 ring-accent/40' : ''}`}
                aria-hidden
              />
              <div className="flex flex-1 items-baseline justify-between gap-2">
                <div className="flex items-center gap-2">
                  <span
                    className={`text-xs font-medium ${isActive ? 'text-text-primary' : 'text-text-secondary'}`}
                  >
                    {state.replace('_', ' ')}
                  </span>
                  {isActive && (
                    <Badge
                      tone={isTerminal ? 'danger' : 'ok'}
                      label={isTerminal ? 'terminal' : 'active'}
                    />
                  )}
                </div>
                {ts && (
                  <span className="font-mono text-[10px] tabular-nums text-text-tertiary">
                    {new Date(ts).toISOString().slice(11, 19)}Z
                  </span>
                )}
              </div>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
