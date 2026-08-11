import * as React from 'react';
import { createBrowserRouter } from 'react-router-dom';

import { PageShell } from './components/page-shell';
import { SuspenseOutlet } from './components/suspense-outlet';
import { DashboardPage } from './pages/dashboard';
import { HealthPage } from './pages/health';
import { OrderDetailPage } from './pages/order-detail';
import { StreamsPage } from './pages/streams';
import { TerminalPage } from './pages/terminal';

/**
 * Lumine portal route table (F-Sprint 5 surfaces).
 *
 * `/` is now the Terminal workspace. Detail pages are lazy-loaded to keep the
 * critical bundle under budget; the layout route persists the TopBar/Rail
 * and data stores across navigation.
 */

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
      { path: '/health', element: <HealthPage /> },
      { path: '/streams', element: <StreamsPage /> },
      { path: '/dashboard', element: <DashboardPage /> },
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
