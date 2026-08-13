import { create } from "zustand";

export type Workspace = "trading" | "research" | "risk" | "ops";

export const WORKSPACES: Array<{ id: Workspace; label: string }> = [
  { id: "trading", label: "Trading" },
  { id: "research", label: "Research" },
  { id: "risk", label: "Risk" },
  { id: "ops", label: "Ops" },
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
