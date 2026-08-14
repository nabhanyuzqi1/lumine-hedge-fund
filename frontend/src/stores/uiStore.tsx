import { create } from "zustand";
import type { ReactNode } from "react";

export type Workspace = "trading" | "research" | "risk" | "ops" | "superadmin";

type WorkspaceConfig = {
  id: Workspace;
  icon: ReactNode;
  tooltip: string;
};

const TradingIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" className="w-5 h-5">
    <path d="M3 3v18h18" strokeLinecap="round" strokeLinejoin="round"/>
    <path d="M7 14l4-4 4 4 5-6" strokeLinecap="round" strokeLinejoin="round"/>
  </svg>
);

const ResearchIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" className="w-5 h-5">
    <circle cx="11" cy="11" r="8" strokeLinecap="round" strokeLinejoin="round"/>
    <path d="M21 21l-4.3-4.3" strokeLinecap="round" strokeLinejoin="round"/>
    <path d="M11 8v6" strokeLinecap="round" strokeLinejoin="round"/>
    <path d="M8 11h6" strokeLinecap="round" strokeLinejoin="round"/>
  </svg>
);

const RiskIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" className="w-5 h-5">
    <path d="M12 3l9 4v6c0 5-4 8-9 10-5-2-9-5-9-10V7l9-4z" strokeLinecap="round" strokeLinejoin="round"/>
    <path d="M12 9v6" strokeLinecap="round" strokeLinejoin="round"/>
    <path d="M12 16h.01" strokeLinecap="round" strokeLinejoin="round"/>
  </svg>
);

const OpsIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" className="w-5 h-5">
    <rect x="3" y="4" width="18" height="16" rx="2" strokeLinecap="round" strokeLinejoin="round"/>
    <path d="M16 2v4M8 2v4M3 10h18" strokeLinecap="round" strokeLinejoin="round"/>
  </svg>
);

const SuperadminIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" className="w-5 h-5">
    <path d="M12 2L2 7l10 5 10-5-10-5z" strokeLinecap="round" strokeLinejoin="round"/>
    <path d="M2 17l10 5 10-5" strokeLinecap="round" strokeLinejoin="round"/>
    <path d="M2 12l10 5 10-5" strokeLinecap="round" strokeLinejoin="round"/>
  </svg>
);

export const WORKSPACES: WorkspaceConfig[] = [
  { id: "trading", icon: <TradingIcon />, tooltip: "Trading Terminal" },
  { id: "research", icon: <ResearchIcon />, tooltip: "Research & Analytics" },
  { id: "risk", icon: <RiskIcon />, tooltip: "Risk Management" },
  { id: "ops", icon: <OpsIcon />, tooltip: "Operations" },
  { id: "superadmin", icon: <SuperadminIcon />, tooltip: "Superadmin Control Center" },
];

interface UiState {
  workspace: Workspace;
  setWorkspace: (workspace: Workspace) => void;
  killSwitchActive: boolean;
  setKillSwitch: (active: boolean) => void;
  selectedSymbol: string;
  setSelectedSymbol: (symbol: string) => void;
  commandPaletteOpen: boolean;
  setCommandPaletteOpen: (open: boolean) => void;
  toggleCommandPalette: () => void;
}

/**
 * Transient UI state (F-Sprint 5). Workspace switching rearranges terminal
 * panes only — it never unmounts streams or resets the data stores, so live
 * data survives rail changes. Kill switch mirrors the SSE `control` stream
 * event once the backend is live; demo mode toggles it locally.
 */
export const useUiStore = create<UiState>((set, get) => ({
  workspace: "trading",
  setWorkspace: (workspace) => set({ workspace }),
  killSwitchActive: false,
  setKillSwitch: (killSwitchActive) => set({ killSwitchActive }),
  selectedSymbol: "XAUUSD",
  setSelectedSymbol: (selectedSymbol) => set({ selectedSymbol }),
  commandPaletteOpen: false,
  setCommandPaletteOpen: (commandPaletteOpen) => set({ commandPaletteOpen }),
  toggleCommandPalette: () => set({ commandPaletteOpen: !get().commandPaletteOpen }),
}));
