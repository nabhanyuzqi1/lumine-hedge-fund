import * as React from 'react';

import { useQuote } from '@/api/hooks';
import { Badge } from '@/components/ui/badge';
import { NumericText } from '@/components/ui/numeric-text';
import { useStreamStore } from '@/stores/streamStore';
import { useUiStore } from '@/stores/uiStore';

const TOTAL_STREAMS = 6;

function formatUTC(date: Date): string {
  return date.toISOString().replace('T', ' ').slice(0, 19);
}

function ShortcutLabel() {
  const isMac =
    typeof navigator !== 'undefined' && navigator.platform.toLowerCase().includes('mac');
  return <span aria-hidden="true">{isMac ? '⌘K' : 'Ctrl+K'}</span>;
}

export function TopBar() {
  const killSwitchActive = useUiStore((s) => s.killSwitchActive);
  const selectedSymbol = useUiStore((s) => s.selectedSymbol);
  const toggleCommandPalette = useUiStore((s) => s.toggleCommandPalette);
  const quote = useQuote(selectedSymbol);
  const streams = useStreamStore((s) => s.getAllStreams());
  const [utc, setUtc] = React.useState(() => formatUTC(new Date()));

  React.useEffect(() => {
    const id = setInterval(() => setUtc(formatUTC(new Date())), 1000);
    return () => clearInterval(id);
  }, []);

  const healthyCount = streams.filter((s) => s.status === 'open' && !s.stale).length;

  return (
    <header
      className="flex h-8 items-center justify-between border-b border-border-subtle bg-bg-raised px-3 text-xs"
      data-testid="top-bar"
    >
      <div className="flex items-center gap-3">
        <div className="flex items-center gap-1.5">
          <span className="h-2 w-2 rounded-full bg-emerald-500" aria-hidden="true" />
          <span className="font-medium text-text-primary">LIVE</span>
        </div>
        {quote.data && (
          <div className="flex items-center gap-2 font-mono text-text-primary">
            <span className="text-text-secondary">{selectedSymbol}</span>
            <NumericText value={quote.data.last} decimals={2} />
            <span className="hidden text-text-secondary sm:inline">
              B <NumericText value={quote.data.bid} decimals={2} />
            </span>
            <span className="hidden text-text-secondary sm:inline">
              A <NumericText value={quote.data.ask} decimals={2} />
            </span>
          </div>
        )}
      </div>

      <div className="flex items-center gap-3">
        {killSwitchActive ? (
          <Badge tone="danger" label="KILL SWITCH ACTIVE" />
        ) : (
          <Badge tone="ok" label="Kill standby" />
        )}
        <span className="font-mono text-text-secondary" data-testid="utc-clock">
          {utc} UTC
        </span>
        <button
          type="button"
          onClick={toggleCommandPalette}
          className="flex items-center gap-1 rounded-chip border border-border-subtle bg-bg-base px-2 py-0.5 text-text-secondary hover:bg-bg-overlay focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
          aria-label="Open command palette"
        >
          <ShortcutLabel />
        </button>
        <span
          className="font-mono text-text-secondary"
          data-testid="stream-health"
          title={`${healthyCount} of ${TOTAL_STREAMS} streams healthy`}
        >
          {healthyCount}/{TOTAL_STREAMS}
        </span>
      </div>
    </header>
  );
}
