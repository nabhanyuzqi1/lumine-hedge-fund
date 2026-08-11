import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';

import { Rail } from './rail';
import { useUiStore } from '@/stores/uiStore';

describe('Rail', () => {
  it('renders workspace buttons and marks the active one', () => {
    render(<Rail />);

    for (const ws of ['trading', 'research', 'risk', 'ops']) {
      expect(screen.getByTestId(`rail-${ws}`)).toBeDefined();
    }

    expect(screen.getByTestId('rail-trading')).toHaveAttribute('aria-current', 'page');
    expect(screen.getByTestId('rail-research')).not.toHaveAttribute('aria-current');
  });

  it('updates the workspace store when a button is clicked', async () => {
    const user = userEvent.setup();
    render(<Rail />);

    await user.click(screen.getByTestId('rail-risk'));
    expect(useUiStore.getState().workspace).toBe('risk');

    await user.click(screen.getByTestId('rail-ops'));
    expect(useUiStore.getState().workspace).toBe('ops');
  });

  it('is keyboard navigable between workspace buttons', async () => {
    const user = userEvent.setup();
    render(<Rail />);

    const first = screen.getByTestId('rail-trading');
    first.focus();
    expect(document.activeElement).toBe(first);

    await user.tab();
    expect(document.activeElement).toBe(screen.getByTestId('rail-research'));
  });
});
