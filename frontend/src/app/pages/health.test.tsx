import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { HealthPage } from './health';

describe('HealthPage', () => {
  it('renders an ok status with the api version', () => {
    render(<HealthPage />);

    expect(screen.getByText('System health')).toBeInTheDocument();
    expect(screen.getByTestId('health-status')).toHaveClass('bg-up');
    expect(screen.getByText('ok')).toBeInTheDocument();
    expect(screen.getByText('v1')).toBeInTheDocument();
  });
});
