import * as React from 'react';
import { createBrowserRouter } from 'react-router-dom';

import { PageShell } from './components/page-shell';
import { SuspenseOutlet } from './components/suspense-outlet';
import { OrderDetailPage } from './pages/order-detail';
import { TerminalPage } from './pages/terminal';

/**
 * Lumine portal route table (F-Sprint 5/6 surfaces).
 *
 * `/` is now the Terminal workspace. Heavy surfaces (dashboard chart grid,
 * streams, health) are lazy-loaded to keep the critical bundle under budget;
 * the layout route persists the TopBar/Rail and data stores across navigation.
 */

const LazyDashboard = React.lazy(() =>
  import('./pages/dashboard').then((m) => ({ default: m.DashboardPage })),
);
const LazyHealth = React.lazy(() =>
  import('./pages/health').then((m) => ({ default: m.HealthPage })),
);
const LazyStreams = React.lazy(() =>
  import('./pages/streams').then((m) => ({ default: m.StreamsPage })),
);
const LazyWorkflowRunDetail = React.lazy(() =>
  import('./pages/workflow-run-detail').then((m) => ({ default: m.WorkflowRunDetailPage })),
);
const LazyLineageDetail = React.lazy(() =>
  import('./pages/lineage-detail').then((m) => ({ default: m.LineageDetailPage })),
);
const LazyJournal = React.lazy(() =>
  import('./pages/journal').then((m) => ({ default: m.JournalPage })),
);
const LazyAdminKeys = React.lazy(() =>
  import('./pages/admin-keys').then((m) => ({ default: m.AdminKeysPage })),
);

export const router = createBrowserRouter([
  {
    element: <PageShell />,
    children: [
      { path: '/', element: <TerminalPage /> },
      { path: '/health', element: <LazyHealth /> },
      { path: '/streams', element: <LazyStreams /> },
      { path: '/dashboard', element: <LazyDashboard /> },
      {
        element: <SuspenseOutlet />,
        children: [
          { path: '/orders/:orderId', element: <OrderDetailPage /> },
          { path: '/workflows/:workflowId/runs/:runId', element: <LazyWorkflowRunDetail /> },
          { path: '/lineage/:lineageId', element: <LazyLineageDetail /> },
          { path: '/journal', element: <LazyJournal /> },
          { path: '/admin/keys', element: <LazyAdminKeys /> },
        ],
      },
    ],
  },
]);
