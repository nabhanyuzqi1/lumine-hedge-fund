import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { DataTable } from "./data-table";

interface Row {
  id: string;
  symbol: string;
  quantity: number;
}

function makeRows(count: number): Row[] {
  return Array.from({ length: count }, (_, i) => ({
    id: `row-${i}`,
    symbol: "XAUUSD",
    quantity: i,
  }));
}

describe("DataTable", () => {
  it("renders empty message when no data", () => {
    render(
      <DataTable<Row>
        columns={[
          { key: "symbol", header: "Symbol", cell: (row: Row) => row.symbol },
          { key: "quantity", header: "Qty", cell: (row: Row) => row.quantity },
        ]}
        data={[]}
        getRowId={(row: Row) => row.id}
      />
    );

    expect(screen.getByText("No data")).toBeInTheDocument();
  });

  it("renders a large dataset without mounting every row", () => {
    render(
      <DataTable
        columns={[
          { key: "symbol", header: "Symbol", cell: (row) => row.symbol },
          { key: "quantity", header: "Qty", cell: (row) => row.quantity },
        ]}
        data={makeRows(1_000)}
        getRowId={(row) => row.id}
        rowHeight={40}
      />
    );

    const rows = screen.queryAllByText("XAUUSD");
    expect(rows.length).toBeLessThan(1_000);
  });

  it("uses getRowId for stable keys", () => {
    const data = makeRows(5);
    render(
      <DataTable<Row>
        columns={[{ key: "id", header: "ID", cell: (row: Row) => row.id }]}
        data={data}
        getRowId={(row: Row) => row.id}
      />
    );

    expect(screen.getByText("row-0")).toBeInTheDocument();
    expect(screen.getByText("row-4")).toBeInTheDocument();
  });
});
