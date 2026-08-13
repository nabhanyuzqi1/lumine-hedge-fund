import { cn } from "@/lib/utils";
import { useVirtualizer } from "@tanstack/react-virtual";
import * as React from "react";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "./table";

export interface DataTableColumn<T> {
  key: string;
  header: React.ReactNode;
  width?: number;
  cell: (row: T) => React.ReactNode;
}

export interface DataTableProps<T> {
  columns: DataTableColumn<T>[];
  data: T[];
  getRowId: (row: T, index: number) => string;
  rowHeight?: number;
  className?: string;
  emptyMessage?: string;
}

/**
 * Virtualized data table built on @tanstack/react-virtual.
 *
 * Renders only the rows visible in the viewport plus a small overscan,
 * keeping scroll performant at >10k rows. The parent owns the data
 * reference; delta updates rely on stable row IDs.
 */
export function DataTable<T>({
  columns,
  data,
  getRowId,
  rowHeight = 40,
  className,
  emptyMessage = "No data",
}: DataTableProps<T>) {
  const parentRef = React.useRef<HTMLDivElement>(null);

  const virtualizer = useVirtualizer({
    count: data.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => rowHeight,
    overscan: 8,
    getItemKey: (index) => getRowId(data[index]!, index),
    // Virtualizer reads the data array for keys; keep it in sync.
    // Row content is rendered by parent; this does not need to be a dep.
  });

  const virtualRows = virtualizer.getVirtualItems();
  const totalSize = virtualizer.getTotalSize();

  return (
    <div
      ref={parentRef}
      className={cn(
        "h-[400px] w-full overflow-auto rounded-panel border border-border-subtle",
        className
      )}
      data-testid="data-table-scroll"
    >
      <Table>
        <TableHeader className="sticky top-0 z-10 bg-bg-raised">
          <TableRow className="hover:bg-transparent">
            {columns.map((column) => (
              <TableHead
                key={column.key}
                style={column.width ? { width: column.width, minWidth: column.width } : undefined}
              >
                {column.header}
              </TableHead>
            ))}
          </TableRow>
        </TableHeader>
        <TableBody>
          {data.length === 0 ? (
            <TableRow>
              <TableCell colSpan={columns.length} className="h-32 text-center text-text-muted">
                {emptyMessage}
              </TableCell>
            </TableRow>
          ) : (
            <tr>
              <td
                colSpan={columns.length}
                style={{ height: `${totalSize}px`, position: "relative" }}
              >
                <div
                  style={{
                    position: "absolute",
                    top: 0,
                    left: 0,
                    width: "100%",
                    transform: `translateY(${virtualRows[0]?.start ?? 0}px)`,
                  }}
                >
                  {virtualRows.map((virtualRow) => {
                    const row = data[virtualRow.index]!;
                    return (
                      <div
                        key={virtualRow.key}
                        data-index={virtualRow.index}
                        ref={virtualizer.measureElement}
                        className="flex w-full items-center border-b border-border-subtle transition-colors hover:bg-table-row-hover"
                        style={{ height: `${virtualRow.size}px` }}
                      >
                        {columns.map((column) => (
                          <div
                            key={column.key}
                            className="flex items-center px-2 py-2 text-sm"
                            style={
                              column.width
                                ? { width: column.width, minWidth: column.width, flexShrink: 0 }
                                : { flex: 1, minWidth: 0 }
                            }
                          >
                            {column.cell(row)}
                          </div>
                        ))}
                      </div>
                    );
                  })}
                </div>
              </td>
            </tr>
          )}
        </TableBody>
      </Table>
    </div>
  );
}
