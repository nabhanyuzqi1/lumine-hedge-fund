import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';

import { Card, CardHeader, CardTitle, CardDescription, CardContent, CardFooter } from './card';

describe('Card', () => {
  it('composes all subcomponents with semantic roles', () => {
    render(
      <Card>
        <CardHeader>
          <CardTitle>Position</CardTitle>
          <CardDescription>XAUUSD</CardDescription>
        </CardHeader>
        <CardContent>P&L content</CardContent>
        <CardFooter>footer</CardFooter>
      </Card>,
    );

    expect(screen.getByRole('heading', { name: 'Position' })).toBeInTheDocument();
    expect(screen.getByText('XAUUSD')).toBeInTheDocument();
    expect(screen.getByText('P&L content')).toBeInTheDocument();
  });
});
