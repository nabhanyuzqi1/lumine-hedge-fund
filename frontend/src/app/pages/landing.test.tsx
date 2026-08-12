import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

import { LandingPage } from './landing';

describe('LandingPage', () => {
  it('renders the portal heading and entry cards', () => {
    render(
      <MemoryRouter>
        <LandingPage />
      </MemoryRouter>,
    );
    expect(screen.getByText('Institutional operating system for autonomous trading')).toBeDefined();
    expect(screen.getByTestId('portal-terminal')).toBeDefined();
    expect(screen.getByTestId('portal-dashboard')).toBeDefined();
  });

  it('links Terminal entry to /terminal', () => {
    render(
      <MemoryRouter>
        <LandingPage />
      </MemoryRouter>,
    );
    const terminal = screen.getByTestId('portal-terminal');
    expect(terminal.getAttribute('href')).toBe('/terminal');
  });
});
