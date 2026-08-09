import * as React from 'react';
import { cva, type VariantProps } from 'class-variance-authority';

import { cn } from '@/lib/utils';

const badgeVariants = cva(
  'inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-xs font-medium',
  {
    variants: {
      tone: {
        ok: 'bg-up/10 text-up',
        warn: 'bg-warn/10 text-warn',
        danger: 'bg-danger/10 text-danger',
        info: 'bg-info/10 text-info',
        neutral: 'border border-border-subtle bg-bg-overlay text-text-secondary',
      },
    },
    defaultVariants: {
      tone: 'neutral',
    },
  },
);

export interface BadgeProps extends VariantProps<typeof badgeVariants> {
  label: string;
  className?: string;
}

export function Badge({ tone, label, className }: BadgeProps) {
  return (
    <span className={cn(badgeVariants({ tone }), className)} aria-label={label}>
      <span aria-hidden="true" className="h-1.5 w-1.5 rounded-full bg-current" />
      <span>{label}</span>
    </span>
  );
}
