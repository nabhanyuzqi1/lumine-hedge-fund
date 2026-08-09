import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';

import { Table, TableHeader, TableBody, TableRow, TableHead, TableCell } from './table';

describe('Table', () => {
  it('renders a semantic table', () => {
    render(
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Symbol</TableHead>
            <TableHead className="text-right">Price</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          <TableRow>
            <TableCell>XAUUSD</TableCell>
            <TableCell className="text-right font-mono tabular-nums">2450.30</TableCell>
          </TableRow>
        </TableBody>
      </Table>,
    );

    expect(screen.getByRole('table')).toBeInTheDocument();
    expect(screen.getByRole('columnheader', { name: 'Symbol' })).toBeInTheDocument();
    expect(screen.getByRole('cell', { name: 'XAUUSD' })).toBeInTheDocument();
  });
});
