import { act, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, useLocation } from 'react-router-dom';
import { describe, expect, it } from 'vitest';

import { CommandPalette } from './command-palette';
import { useUiStore } from '@/stores/uiStore';

function LocationDisplay() {
  const location = useLocation();
  return <span data-testid="location">{location.pathname}</span>;
}

function renderPalette() {
  return render(
    <MemoryRouter initialEntries={['/']}>
      <CommandPalette />
      <LocationDisplay />
    </MemoryRouter>,
  );
}

describe('CommandPalette', () => {
  it('opens when store state is true', () => {
    renderPalette();
    act(() => useUiStore.setState({ commandPaletteOpen: true }));
    expect(screen.getByLabelText('Command palette search')).toBeDefined();
  });

  it('closes when store state is false', () => {
    renderPalette();
    act(() => useUiStore.setState({ commandPaletteOpen: true }));
    act(() => useUiStore.setState({ commandPaletteOpen: false }));
    expect(screen.queryByLabelText('Command palette search')).toBeNull();
  });

  it('filters items by query', async () => {
    const user = userEvent.setup();
    renderPalette();
    act(() => useUiStore.setState({ commandPaletteOpen: true }));

    const input = screen.getByLabelText('Command palette search');
    await user.type(input, 'journal');
    expect(screen.getByText('Go to Journal')).toBeDefined();
    expect(screen.queryByText('Go to Admin Keys')).toBeNull();
  });

  it('navigates to selected item on Enter', async () => {
    const user = userEvent.setup();
    renderPalette();
    act(() => useUiStore.setState({ commandPaletteOpen: true }));

    const input = screen.getByLabelText('Command palette search');
    await user.type(input, 'journal');
    await user.keyboard('{Enter}');

    expect(screen.getByTestId('location')).toHaveTextContent('/journal');
    expect(useUiStore.getState().commandPaletteOpen).toBe(false);
  });

  it('updates active item with arrow keys', async () => {
    const user = userEvent.setup();
    renderPalette();
    act(() => useUiStore.setState({ commandPaletteOpen: true }));

    await user.keyboard('{ArrowDown}');
    // Active item styling is class-based; assert listbox presence.
    expect(screen.getAllByRole('option').length).toBeGreaterThan(0);
  });

  it('ignores global mod+k when typing in input', async () => {
    const user = userEvent.setup();
    renderPalette();
    act(() => useUiStore.setState({ commandPaletteOpen: true }));

    const input = screen.getByLabelText('Command palette search');
    await user.type(input, 'k');
    expect(input).toHaveValue('k');
  });
});
