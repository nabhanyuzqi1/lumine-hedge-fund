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
  /** Max height in pixels (e.g., 400). Enables scroll overflow. */
  maxHeight?: number;
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
  emptyMessage = "No data",
  className,
  maxHeight,
}: DataTableProps<T>) {
  const parentRef = React.useRef<HTMLDivElement>(null);

  // Forward wheel events to the page scroller when the table has reached
  // its scroll limit (or has no overflow). Prevents table from trapping
  // wheel events that should scroll the page.
  React.useEffect(() => {
    const el = parentRef.current;
    if (!el) return;
    const onWheel = (e: WheelEvent) => {
      const canScrollDown = e.deltaY > 0 && el.scrollTop < el.scrollHeight - el.clientHeight - 1;
      const canScrollUp = e.deltaY < 0 && el.scrollTop > 0;
      if (canScrollDown || canScrollUp) return; // let table scroll
      // Find main scroller and forward
      let parent: HTMLElement | null = el.parentElement;
      while (parent) {
        const style = window.getComputedStyle(parent);
        const oy = style.overflowY;
        if ((oy === "auto" || oy === "scroll") && parent.scrollHeight > parent.clientHeight) {
          parent.scrollBy({ top: e.deltaY, behavior: "auto" });
          break;
        }
        parent = parent.parentElement;
      }
    };
    el.addEventListener("wheel", onWheel, { passive: true });
    return () => el.removeEventListener("wheel", onWheel);
  }, []);

  const virtualizer = useVirtualizer({
    count: data.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => rowHeight,
    overscan: 8,
    getItemKey: (index) => getRowId(data[index]!, index),
  });

  const virtualRows = virtualizer.getVirtualItems();
  const totalSize = virtualizer.getTotalSize();

  return (
    <div
      ref={parentRef}
      className={`w-full overflow-auto overscroll-none rounded-panel border border-border-subtle ${className ?? ""}`.trim()}
      data-testid="data-table-scroll"
      style={maxHeight ? { maxHeight } : undefined}
    >
      <Table disableOverflow>
              <TableHeader className="sticky top-0 z-10 bg-bg-raised">
          <TableRow className="hover:bg-transparent">
            {columns.map((column) => (
              <TableHead
                key={column.key}
                style={column.width ? { width: column.width, minWidth: column.width, maxWidth: column.width } : undefined}
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
                        className="flex items-center px-3 py-2 text-sm transition-colors hover:bg-table-row-hover"
                        style={{ height: `${virtualRow.size}px` }}
                      >
                        {columns.map((column) => (
                          <div
                            key={column.key}
                            className={cn(
                              "px-3 py-2 text-sm",
                              /qty|avg|current|pnl|price/.test(column.key as string) ? "text-right font-mono tabular-nums" : "text-left"
                            )}
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