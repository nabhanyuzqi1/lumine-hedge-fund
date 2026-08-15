import * as React from "react";
import { Outlet } from "react-router-dom";

export function SuspenseOutlet() {
  return (
    <React.Suspense fallback={<div className="p-4 text-sm text-text-secondary">Loading…</div>}>
      <Outlet />
    </React.Suspense>
  );
}
