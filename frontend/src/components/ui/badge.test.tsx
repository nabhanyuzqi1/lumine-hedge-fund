import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';

import { Badge } from './badge';

describe('Badge', () => {
  it('renders label text', () => {
    render(<Badge tone="ok" label="Live" />);
    expect(screen.getByText('Live')).toBeInTheDocument();
  });

  it('keeps the status dot decorative', () => {
    const { container } = render(<Badge tone="warn" label="Stale" />);
    const dot = container.querySelector('[aria-hidden="true"]');
    expect(dot).toBeInTheDocument();
  });

  it('applies the danger tone class', () => {
    const { container } = render(<Badge tone="danger" label="Error" />);
    expect((container.firstChild as HTMLElement).className).toContain('text-danger');
  });
});
