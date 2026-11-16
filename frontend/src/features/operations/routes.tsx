import type { RouteObject } from 'react-router-dom';

import { OperationsDashboardPage } from '@/features/operations/OperationsDashboardPage';
import type { Site } from '@/types';
import type { Machine } from '@/types/machine';

export const operationsRoutes = ({
  machines,
  sites,
}: {
  machines: Machine[];
  sites: Site[];
}): RouteObject[] => [
  {
    path: '/admin/operations',
    element: <OperationsDashboardPage machines={machines} sites={sites} />,
  },
];
