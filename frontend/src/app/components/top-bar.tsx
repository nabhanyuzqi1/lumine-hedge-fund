import * as React from "react";
import { useNavigate } from "react-router-dom";
import { useShallow } from "zustand/react/shallow";

import { Badge } from "@/components/ui/badge";
import { useStreamStore } from "@/stores/streamStore";
import { useUiStore } from "@/stores/uiStore";
import { StreamStatusList } from "@/components/streams/stream-status-list";
import { useAuth } from "@/lib/auth/role-context";

// 5 stream aktif: market-data/XAUUSD + analyst-outputs + ic-decisions +
// cio-proposals + risk-assessments (committee, diregister useCommitteeStreams).
const TOTAL_STREAMS = 5;

function formatUTC(date: Date): string {
  return date.toISOString().replace("T", " ").slice(0, 19);
}

function ShortcutLabel() {
  const isMac =
    typeof navigator !== "undefined" && navigator.platform.toLowerCase().includes("mac");
  return <span aria-hidden="true">{isMac ? "⌘K" : "Ctrl+K"}</span>;
}

export function TopBar() {
  const navigate = useNavigate();
  const { logout, username, isAuthenticated } = useAuth();
  const killSwitchActive = useUiStore((s) => s.killSwitchActive);
  const toggleCommandPalette = useUiStore((s) => s.toggleCommandPalette);
  const streams = useStreamStore(useShallow((s) => s.getAllStreams()));
  const [utc, setUtc] = React.useState(() => formatUTC(new Date()));

  const handleLogout = () => {
    logout();
    navigate("/login");
  };

  React.useEffect(() => {
    const id = setInterval(() => setUtc(formatUTC(new Date())), 1000);
    return () => clearInterval(id);
  }, []);

  const healthyCount = streams.filter((s) => s.status === "open" && !s.stale).length;

  return (
    <header
      className="flex h-8 items-center justify-between border-b border-line bg-raised px-3 text-xs"
      data-testid="top-bar"
    >
      <div className="flex items-center gap-3">
        <div className="flex items-center gap-1.5">
          <span className="h-2 w-2 rounded-full bg-emerald-500" aria-hidden="true" />
          <span className="font-medium text-ink">LIVE</span>
        </div>
        {/* Quote pindah ke terminal (CommandBar/QuotePanel) — TopBar global
            tidak menduplikasi symbol/price per halaman. */}
      </div>

      <div className="flex items-center gap-3">
        {isAuthenticated && username && (
          <span className="text-text-secondary text-xs">
            {username}
          </span>
        )}
        {killSwitchActive ? (
          <Badge tone="danger" label="KILL SWITCH ACTIVE" />
        ) : (
          <Badge tone="ok" label="Kill standby" />
        )}
        <span className="font-mono text-text-secondary" data-testid="utc-clock">
          {utc} UTC
        </span>
        <button
          type="button"
          onClick={toggleCommandPalette}
          className="flex items-center gap-1 rounded-chip border border-border-subtle bg-bg-base px-2 py-0.5 text-text-secondary hover:bg-bg-overlay focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
          aria-label="Open command palette"
        >
          <ShortcutLabel />
        </button>
        <span
          className="font-mono text-text-secondary"
          data-testid="stream-health"
          title={`${healthyCount} of ${TOTAL_STREAMS} streams healthy`}
        >
          {healthyCount}/{TOTAL_STREAMS}
        </span>
        <span className="hidden lg:inline-flex" data-testid="stream-status-dots">
          <StreamStatusList />
        </span>
        {isAuthenticated && (
          <button
            type="button"
            onClick={handleLogout}
            className="text-text-secondary hover:text-text-primary text-xs underline"
            aria-label="Logout"
          >
            Logout
          </button>
        )}
      </div>
    </header>
  );
}
