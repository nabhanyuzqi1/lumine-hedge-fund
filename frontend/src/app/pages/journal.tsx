import { useEffect, useMemo, useState } from "react";

import { type JournalFilters, useJournal, useJournalPage } from "@/api/hooks";
import { downloadCsv, toCsv } from "@/lib/csv";
import { JournalTable } from "@/components/journal/journal-table";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { JournalEntry, JournalPage } from "@/data/fixtures";

const ALL = "all";

type LocalFilters = Required<Omit<JournalFilters, "portfolioId">> & {
  portfolioId: string;
  start?: string;
  end?: string;
};

function filterEntries(entries: JournalEntry[], filters: LocalFilters): JournalEntry[] {
  return entries.filter((e) => {
    if (filters.symbol !== ALL && e.symbol !== filters.symbol) return false;
    if (filters.portfolioId !== ALL && e.portfolio_id !== filters.portfolioId) return false;
    if (filters.kind !== ALL && e.kind !== filters.kind) return false;
    if (filters.start && new Date(e.timestamp) < new Date(filters.start)) return false;
    if (filters.end && new Date(e.timestamp) > new Date(`${filters.end}T23:59:59.999Z`))
      return false;
    return true;
  });
}

/**
 * `/journal` — Filterable audit journal (W5). Loads 50-row pages via cursor and
 * applies local symbol/kind/portfolio/date filters until the backend is live.
 */
export function JournalPage() {
  const [filters, setFilters] = useState<LocalFilters>({
    symbol: ALL,
    portfolioId: ALL,
    kind: ALL,
  });
  const [loadedPages, setLoadedPages] = useState<JournalPage[]>([]);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [nextCursor, setNextCursor] = useState<string | null>(null);

  const backendFilters: JournalFilters = useMemo(
    () => ({
      symbol: filters.symbol === ALL ? undefined : filters.symbol,
      portfolioId: filters.portfolioId === ALL ? undefined : filters.portfolioId,
      kind: filters.kind === ALL ? undefined : filters.kind,
    }),
    [filters]
  );

  const first = useJournal(backendFilters);
  const nextPage = useJournalPage(nextCursor, backendFilters);

  // Reset loaded state when filters change.
  useEffect(() => {
    setLoadedPages([]);
    setNextCursor(null);
    setExpandedId(null);
  }, [backendFilters.symbol, backendFilters.portfolioId, backendFilters.kind]);

  // Seed loaded pages from the first page.
  useEffect(() => {
    if (first.data && loadedPages.length === 0) {
      setLoadedPages([first.data]);
    }
  }, [first.data, loadedPages.length]);

  // Append subsequent pages once they resolve.
  useEffect(() => {
    if (nextPage.data && nextPage.data.entries.length > 0) {
      setLoadedPages((prev) => {
        if (
          prev.some(
            (p) =>
              p.cursor === nextPage.data.cursor && p.entries.length === nextPage.data.entries.length
          )
        ) {
          return prev;
        }
        return [...prev, nextPage.data];
      });
      setNextCursor(null);
    }
  }, [nextPage.data]);

  const allEntries = useMemo(() => loadedPages.flatMap((p) => p.entries), [loadedPages]);
  const filteredEntries = useMemo(() => filterEntries(allEntries, filters), [allEntries, filters]);
  const hasMore = loadedPages.at(-1)?.has_more ?? false;

  const symbols = useMemo(
    () => Array.from(new Set(allEntries.map((e) => e.symbol).filter(Boolean))),
    [allEntries]
  );
  const portfolios = useMemo(
    () => Array.from(new Set(allEntries.map((e) => e.portfolio_id))),
    [allEntries]
  );

  const handleLoadMore = () => {
    const cursor = loadedPages.at(-1)?.cursor ?? null;
    if (cursor) setNextCursor(cursor);
  };

  const handleReset = () => {
    setFilters({ symbol: ALL, portfolioId: ALL, kind: ALL });
  };

  const handleExportCsv = () => {
    const entries = loadedPages.flatMap((page) => page.entries);
    downloadCsv(
      `lumine-journal-${new Date().toISOString().slice(0, 10)}.csv`,
      toCsv(
        entries.map((entry) => ({
          id: entry.id,
          timestamp: entry.timestamp,
          portfolio_id: entry.portfolio_id,
          kind: entry.kind,
          actor: entry.actor,
          summary: entry.summary,
          linked_lineage_id: entry.linked_lineage_id ?? "",
        }))
      )
    );
  };

  return (
    <div className="mx-auto w-full max-w-[1400px] space-y-4 p-4">
      <header className="flex items-baseline justify-between">
        <div>
          <h1 className="text-lg font-semibold text-text-primary">Journal</h1>
          <p className="text-sm text-text-secondary">
            Audit trail of decisions, trades, risk checks, and notes.
          </p>
        </div>
        <button
          type="button"
          onClick={handleExportCsv}
          disabled={loadedPages.every((page) => page.entries.length === 0)}
          className="rounded-chip border border-border-subtle bg-bg-base px-3 py-1 text-xs text-text-secondary hover:bg-bg-overlay focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent disabled:opacity-40"
          data-testid="journal-export-csv"
        >
          Export CSV
        </button>
      </header>

      <Card>
        <CardHeader>
          <CardTitle>Filters</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex flex-wrap items-end gap-3">
            <div>
              <label
                htmlFor="symbol"
                className="text-[11px] uppercase tracking-wider text-text-secondary"
              >
                Symbol
              </label>
              <select
                id="symbol"
                value={filters.symbol}
                onChange={(e) => setFilters((f) => ({ ...f, symbol: e.target.value }))}
                className="mt-1 block rounded-chip border border-border-subtle bg-bg-base px-2 py-1.5 text-xs text-text-primary"
                data-testid="journal-symbol-filter"
              >
                <option value={ALL}>All symbols</option>
                {symbols.map((s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label
                htmlFor="portfolio"
                className="text-[11px] uppercase tracking-wider text-text-secondary"
              >
                Portfolio
              </label>
              <select
                id="portfolio"
                value={filters.portfolioId}
                onChange={(e) => setFilters((f) => ({ ...f, portfolioId: e.target.value }))}
                className="mt-1 block rounded-chip border border-border-subtle bg-bg-base px-2 py-1.5 text-xs text-text-primary"
                data-testid="journal-portfolio-filter"
              >
                <option value={ALL}>All portfolios</option>
                {portfolios.map((p) => (
                  <option key={p} value={p}>
                    {p}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label
                htmlFor="kind"
                className="text-[11px] uppercase tracking-wider text-text-secondary"
              >
                Kind
              </label>
              <select
                id="kind"
                value={filters.kind}
                onChange={(e) => setFilters((f) => ({ ...f, kind: e.target.value }))}
                className="mt-1 block rounded-chip border border-border-subtle bg-bg-base px-2 py-1.5 text-xs text-text-primary"
                data-testid="journal-kind-filter"
              >
                <option value={ALL}>All kinds</option>
                <option value="decision">Decision</option>
                <option value="trade">Trade</option>
                <option value="risk">Risk</option>
                <option value="note">Note</option>
              </select>
            </div>

            <div>
              <label
                htmlFor="start"
                className="text-[11px] uppercase tracking-wider text-text-secondary"
              >
                From
              </label>
              <input
                id="start"
                type="date"
                value={filters.start ?? ""}
                onChange={(e) => setFilters((f) => ({ ...f, start: e.target.value || undefined }))}
                className="mt-1 block rounded-chip border border-border-subtle bg-bg-base px-2 py-1.5 text-xs text-text-primary"
                data-testid="journal-start-date"
              />
            </div>

            <div>
              <label
                htmlFor="end"
                className="text-[11px] uppercase tracking-wider text-text-secondary"
              >
                To
              </label>
              <input
                id="end"
                type="date"
                value={filters.end ?? ""}
                onChange={(e) => setFilters((f) => ({ ...f, end: e.target.value || undefined }))}
                className="mt-1 block rounded-chip border border-border-subtle bg-bg-base px-2 py-1.5 text-xs text-text-primary"
                data-testid="journal-end-date"
              />
            </div>

            <Button
              variant="secondary"
              size="sm"
              onClick={handleReset}
              data-testid="journal-reset-filters"
            >
              Reset
            </Button>
          </div>
        </CardContent>
      </Card>

      <JournalTable
        entries={filteredEntries}
        expandedId={expandedId}
        onRowClick={(entry) => setExpandedId((id) => (id === entry.id ? null : entry.id))}
      />

      {hasMore && (
        <div className="flex justify-center">
          <Button
            variant="secondary"
            size="md"
            onClick={handleLoadMore}
            disabled={nextCursor !== null && nextPage.isLoading}
            data-testid="journal-load-more"
          >
            Load more
          </Button>
        </div>
      )}
    </div>
  );
}
