import { Outlet } from 'react-router-dom';

import { KillSwitchBanner } from './kill-switch-banner';
import { Rail } from './rail';
import { TopBar } from './top-bar';

/**
 * App shell (F-Sprint 5). Wraps every portal route with the live top bar,
 * workspace rail, kill-switch banner, and the main content area.
 */
export function PageShell() {
  return (
    <div className="flex h-screen flex-col bg-bg-base" data-testid="page-shell">
      <TopBar />
      <KillSwitchBanner />
      <div className="flex flex-1 overflow-hidden">
        <Rail />
        <main className="flex-1 overflow-auto">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
