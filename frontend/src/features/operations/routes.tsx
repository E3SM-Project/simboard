import type { RouteObject } from 'react-router-dom';

import { OperationsDashboardPage } from '@/features/operations/OperationsDashboardPage';
import type { Site } from '@/types';

export const operationsRoutes = ({ sites }: { sites: Site[] }): RouteObject[] => [
  { path: '/admin/operations', element: <OperationsDashboardPage sites={sites} /> },
];
