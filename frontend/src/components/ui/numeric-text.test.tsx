import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';

import { NumericText } from './numeric-text';

describe('NumericText', () => {
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
  });

  it('renders with tabular numerals', () => {
    render(<NumericText value={1234.56} />);
    const el = screen.getByLabelText('1234.56');
    expect(el.className).toContain('tabular-nums');
    expect(el.className).toContain('font-mono');
  });

  it('flashes up when value increases', () => {
    const { rerender } = render(<NumericText value={100} />);
    rerender(<NumericText value={110} />);
    const el = screen.getByLabelText('110');
    expect(el.className).toContain('animate-flash-up');
  });

  it('flashes down when value decreases', () => {
    const { rerender } = render(<NumericText value={100} />);
    rerender(<NumericText value={90} />);
    const el = screen.getByLabelText('90');
    expect(el.className).toContain('animate-flash-down');
  });

  it('renders sign and suffix when requested', () => {
    render(<NumericText value={5.4} showSign suffix="%" />);
    expect(screen.getByText('+5.40%')).toBeInTheDocument();
  });
});
