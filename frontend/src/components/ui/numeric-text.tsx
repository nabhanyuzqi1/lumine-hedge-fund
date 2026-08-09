import * as React from 'react';

import { cn } from '@/lib/utils';

export interface NumericTextProps {
  value: number;
  decimals?: number;
  showSign?: boolean;
  tone?: 'up' | 'down' | 'neutral';
  suffix?: string;
  className?: string;
}

export function NumericText({
  value,
  decimals = 2,
  showSign = false,
  tone = 'neutral',
  suffix,
  className,
}: NumericTextProps) {
  const previous = React.useRef(value);
  const [flash, setFlash] = React.useState<'up' | 'down' | null>(null);

  React.useEffect(() => {
    if (value > previous.current) {
      setFlash('up');
    } else if (value < previous.current) {
      setFlash('down');
    }
    previous.current = value;

    const timer = setTimeout(() => setFlash(null), 150);
    return () => clearTimeout(timer);
  }, [value]);

  const sign = value > 0 ? '+' : value < 0 ? '−' : '';
  const absolute = Math.abs(value).toFixed(decimals);

  const toneClass = tone === 'up' ? 'text-up' : tone === 'down' ? 'text-down' : 'text-text-primary';

  return (
    <span
      className={cn(
        'font-mono tabular-nums',
        flash === 'up' && 'animate-flash-up',
        flash === 'down' && 'animate-flash-down',
        toneClass,
        className,
      )}
      aria-label={`${value}`}
    >
      {showSign && sign}
      {absolute}
      {suffix}
    </span>
  );
}
