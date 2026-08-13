/**
 * CSV export helper (F-08) — client-side export of table-like data.
 * Handles RFC-4180 quoting, tabular numbers as plain decimals, and BOM for
 * Excel compatibility.
 */

export function toCsv(rows: Record<string, unknown>[]): string {
  if (rows.length === 0) return "";
  const headers = Object.keys(rows[0]!);
  const escape = (value: unknown): string => {
    const text =
      typeof value === "number" ? String(value) : value == null ? "" : String(value);
    return /[",\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
  };
  const lines = [headers.map(escape).join(",")];
  for (const row of rows) {
    lines.push(headers.map((header) => escape(row[header])).join(","));
  }
  return lines.join("\n");
}

export function downloadCsv(filename: string, csv: string): void {
  // BOM makes Excel detect UTF-8; \r\n is the spreadsheet-safe line ending.
  const blob = new Blob(["\uFEFF" + csv.replace(/\n/g, "\r\n")], {
    type: "text/csv;charset=utf-8",
  });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}
