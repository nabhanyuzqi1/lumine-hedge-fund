import * as React from 'react';

import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { cn } from '@/lib/utils';

export type ChartStatus = 'live' | 'stale' | 'offline';

const STATUS_TO_BADGE: Record<ChartStatus, { tone: 'ok' | 'warn' | 'danger'; label: string }> = {
  live: { tone: 'ok', label: 'LIVE' },
  stale: { tone: 'warn', label: 'STALE' },
  offline: { tone: 'danger', label: 'OFFLINE' },
};

export interface ChartCardProps {
  title: string;
  description?: string;
  status?: ChartStatus;
  /** Right-aligned controls (timeframe selector, legend, ...). */
  toolbar?: React.ReactNode;
  /** Fixed pane height in px — prevents layout shift when data streams in. */
  height?: number;
  children: React.ReactNode;
  className?: string;
}

/**
 * Chart pane wrapper: fixed-height content box (no layout shift on data
 * updates), title row, live/stale/offline status badge, optional toolbar.
 * The chart library instance is created by the child; resize handling lives
 * in `useChartResize` and observes the child's own container.
 */
export function ChartCard({
  title,
  description,
  status,
  toolbar,
  height = 320,
  children,
  className,
}: ChartCardProps) {
  const badge = status ? STATUS_TO_BADGE[status] : null;

  return (
    <Card className={cn('min-w-0', className)}>
      <CardHeader className="flex-row items-center justify-between space-y-0">
        <div className="min-w-0">
          <CardTitle>{title}</CardTitle>
          {description ? <CardDescription>{description}</CardDescription> : null}
        </div>
        <div className="flex shrink-0 items-center gap-2">
          {toolbar}
          {badge ? <Badge tone={badge.tone} label={badge.label} /> : null}
        </div>
      </CardHeader>
      <CardContent className="pt-0">
        <div className="relative w-full overflow-hidden" style={{ height }}>
          {children}
        </div>
      </CardContent>
    </Card>
  );
}
