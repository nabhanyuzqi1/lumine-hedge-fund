import { Outlet } from "react-router-dom";

import { CommandPalette } from "./command-palette";
import { KeyboardProvider } from "./keyboard-provider";
import { KillSwitchBanner } from "./kill-switch-banner";
import { Rail } from "./rail";
import { TopBar } from "./top-bar";
import { GapBanner } from "@/components/streams/gap-banner";

/**
 * App shell (F-Sprint 6). Wraps every portal route with the live top bar,
 * workspace rail, kill-switch banner, keyboard shortcuts, command palette,
 * skip-link, and the main content area.
 */
export function PageShell() {
  return (
    <KeyboardProvider>
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:absolute focus:z-[100] focus:m-2 focus:rounded-chip focus:bg-accent focus:px-3 focus:py-2 focus:text-white"
      >
        Skip to main content
      </a>
      <div className="flex h-dvh flex-col bg-bg-base" data-testid="page-shell">
              <TopBar />
              <GapBanner />
              <KillSwitchBanner />
              <div className="flex min-h-0 flex-1 flex-col-reverse overflow-hidden md:flex-row">
                <Rail />
                <main id="main-content" className="min-h-0 flex-1 overflow-y-auto" tabIndex={-1}>
                  <Outlet />
                </main>
              </div>
            </div>
      <CommandPalette />
    </KeyboardProvider>
  );
}
