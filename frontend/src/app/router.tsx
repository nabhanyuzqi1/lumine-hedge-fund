import * as React from "react";
import { createBrowserRouter, Navigate } from "react-router-dom";

import { AuthProvider, RequireRole } from "@/lib/auth/role-context";
import { PageShell } from "./components/page-shell";
import { SuspenseOutlet } from "./components/suspense-outlet";
import { LoadingScreenSkeleton } from "@/components/ui/skeleton";
import { RouteErrorBoundary } from "@/components/ui/route-error-boundary";

/**
 * Lumine route table.
 *
 * Route hierarchy:
 *   /               → Public landing page (Lumine Hedge Fund marketing)
 *   /login          → Login page
 *   /app/*          → Protected (user+) — trading workspace
 *   /admin/*        → Protected (admin+) — admin panel
 *   /superadmin     → Protected (superadmin) — control center
 *
 * PageShell (TopBar + Rail + layout) hanya muncul di /app/* dan /admin/*.
 */

// ── Lazy routes ────────────────────────────────────────────────────────────
// Public pages
const LazyLandingPublic = React.lazy(() =>
  import("./pages/landing-public").then((m) => ({ default: m.LandingPublicPage }))
);
const LazyLogin = React.lazy(() =>
  import("./pages/login").then((m) => ({ default: m.LoginPage }))
);

// Protected pages
const LazyTerminal = React.lazy(() =>
  import("./pages/terminal").then((m) => ({ default: m.TerminalPage }))
);
const LazyOrderDetail = React.lazy(() =>
  import("./pages/order-detail").then((m) => ({ default: m.OrderDetailPage }))
);
const LazyDashboard = React.lazy(() =>
  import("./pages/dashboard").then((m) => ({ default: m.DashboardPage }))
);
const LazyHealth = React.lazy(() =>
  import("./pages/health").then((m) => ({ default: m.HealthPage }))
);
const LazyStreams = React.lazy(() =>
  import("./pages/streams").then((m) => ({ default: m.StreamsPage }))
);
const LazyWorkflowRunDetail = React.lazy(() =>
  import("./pages/workflow-run-detail").then((m) => ({ default: m.WorkflowRunDetailPage }))
);
const LazyLineageDetail = React.lazy(() =>
  import("./pages/lineage-detail").then((m) => ({ default: m.LineageDetailPage }))
);
const LazyJournal = React.lazy(() =>
  import("./pages/journal").then((m) => ({ default: m.JournalPage }))
);
const LazyAdminKeys = React.lazy(() =>
  import("./pages/admin-keys").then((m) => ({ default: m.AdminKeysPage }))
);
const LazyWorkflowRunList = React.lazy(() =>
  import("./pages/workflow-run-list").then((m) => ({ default: m.WorkflowRunListPage }))
);
const LazySuperadmin = React.lazy(() =>
  import("./pages/superadmin").then((m) => ({ default: m.SuperadminPage }))
);

// ── Route guards ───────────────────────────────────────────────────────────
function UserRoute({ children }: { children: React.ReactNode }) {
  return (
    <RequireRole role="user" redirectTo="/login">
      {children}
    </RequireRole>
  );
}

function AdminRoute({ children }: { children: React.ReactNode }) {
  return (
    <RequireRole role="admin" redirectTo="/login">
      {children}
    </RequireRole>
  );
}

function SuperadminRoute({ children }: { children: React.ReactNode }) {
  return (
    <RequireRole role="superadmin" redirectTo="/login">
      {children}
    </RequireRole>
  );
}

// ── Router ─────────────────────────────────────────────────────────────────
export const router = createBrowserRouter([
  // Public routes — no PageShell, no auth
  {
    path: "/",
    element: (
      <AuthProvider>
        <React.Suspense fallback={<LoadingScreenSkeleton />}>
          <LazyLandingPublic />
        </React.Suspense>
      </AuthProvider>
    ),
  },
  {
    path: "/login",
    element: (
      <AuthProvider>
        <React.Suspense fallback={<LoadingScreenSkeleton />}>
          <LazyLogin />
        </React.Suspense>
      </AuthProvider>
    ),
  },

  // App routes — PageShell + user role required
    {
      element: (
        <AuthProvider>
          <UserRoute>
            <RouteErrorBoundary>
              <PageShell />
            </RouteErrorBoundary>
          </UserRoute>
        </AuthProvider>
      ),
      children: [
      // /app/* prefix routes
      { path: "/app/terminal", element: <LazyTerminal /> },
      { path: "/app/dashboard", element: <LazyDashboard /> },
      { path: "/app/health", element: <LazyHealth /> },
      { path: "/app/streams", element: <LazyStreams /> },
      { path: "/app/journal", element: <LazyJournal /> },
      { path: "/app/workflows", element: <LazyWorkflowRunList /> },

      // Legacy routes — redirect untuk backward compat
      { path: "/terminal", element: <Navigate to="/app/terminal" replace /> },
      { path: "/dashboard", element: <Navigate to="/app/dashboard" replace /> },
      { path: "/health", element: <Navigate to="/app/health" replace /> },
      { path: "/streams", element: <Navigate to="/app/streams" replace /> },
      { path: "/journal", element: <Navigate to="/app/journal" replace /> },
      { path: "/workflows", element: <Navigate to="/app/workflows" replace /> },

      {
        element: <SuspenseOutlet />,
        children: [
          { path: "/app/orders/:orderId", element: <LazyOrderDetail /> },
          { path: "/orders/:orderId", element: <LazyOrderDetail /> },
          {
            path: "/app/workflows/:workflowId/runs/:runId",
            element: <LazyWorkflowRunDetail />,
          },
          {
            path: "/workflows/:workflowId/runs/:runId",
            element: <LazyWorkflowRunDetail />,
          },
          { path: "/app/lineage/:lineageId", element: <LazyLineageDetail /> },
          { path: "/lineage/:lineageId", element: <LazyLineageDetail /> },
        ],
      },

      // Admin routes — admin role required
      {
        path: "/admin/keys",
        element: (
          <AdminRoute>
            <LazyAdminKeys />
          </AdminRoute>
        ),
      },
      { path: "/admin", element: <Navigate to="/admin/keys" replace /> },

      // Superadmin route — superadmin role required (Caddy forward_auth +
      // SPA RequireRole, session cookie dari backend /api/auth/*)
      {
        path: "/superadmin",
        element: (
          <SuperadminRoute>
            <LazySuperadmin />
          </SuperadminRoute>
        ),
      },
    ],
  },

  // 404 fallback
  {
    path: "*",
    element: (
      <AuthProvider>
        <div className="flex min-h-screen items-center justify-center bg-abyss font-mono text-sm text-text-muted">
          <div className="space-y-2 text-center">
            <div className="text-2xl font-semibold text-ink">404</div>
            <div>Page not found</div>
            <a href="/" className="block text-accent hover:underline">
              → Return to Lumine
            </a>
          </div>
        </div>
      </AuthProvider>
    ),
  },
]);
