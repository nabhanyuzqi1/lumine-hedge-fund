import React from "react";
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
  // Forward wheel events to the main scroller from ANY element on the page.
  // Nested overflow-auto containers (DataTable, ActivityLog, etc.) consume
  // wheel events and never bubble them to <main>. This handler attaches to
  // the window in capture phase and scrolls <main> directly.
  const mainRef = React.useRef<HTMLElement | null>(null);
  React.useEffect(() => {
    const handler = (e: WheelEvent) => {
      const main = mainRef.current;
      if (!main) return;
      // Only forward if the event target is NOT inside a scrollable child
      // that can still scroll in the wheel direction.
      let el = e.target as HTMLElement | null;
      while (el && el !== main) {
        const style = window.getComputedStyle(el);
        const oy = style.overflowY;
        if (oy === "auto" || oy === "scroll") {
          const canScrollDown = e.deltaY > 0 && el.scrollTop < el.scrollHeight - el.clientHeight;
          const canScrollUp = e.deltaY < 0 && el.scrollTop > 0;
          if (canScrollDown || canScrollUp) return; // let the child handle it
          // Child is at its limit — fall through and scroll main
          break;
        }
        el = el.parentElement;
      }
      main.scrollBy({ top: e.deltaY, behavior: "auto" });
    };
    window.addEventListener("wheel", handler, { passive: true, capture: true });
    return () => window.removeEventListener("wheel", handler, { capture: true });
  }, []);

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
              <div className="flex min-h-0 flex-1 flex-col-reverse overflow-clip md:flex-row">
                <Rail />
                <main id="main-content" ref={(el) => { mainRef.current = el; }} className="min-h-0 flex-1 overflow-y-auto" tabIndex={-1}>
                  <Outlet />
                </main>
              </div>
            </div>
      <CommandPalette />
    </KeyboardProvider>
  );
}
