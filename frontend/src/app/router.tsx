import { createBrowserRouter } from 'react-router-dom';
import App from '../App.jsx';
import { HealthPage } from './pages/health';

/**
 * Lumine portal route table (F-Sprint 1 scaffold).
 *
 * `/` stays the marketing landing page (legacy `App.jsx`) until F-Sprint 5
 * surfaces replace it; `/health` is the first portal route and the
 * deployment liveness check.
 */
export const router = createBrowserRouter([
  {
    path: '/',
    element: <App />,
  },
  {
    path: '/health',
    element: <HealthPage />,
  },
]);
