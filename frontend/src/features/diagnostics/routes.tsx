import type { RouteObject } from 'react-router-dom';

import { ComparePage } from '@/features/diagnostics/ComparePage';
import { COMPARE_PATH } from '@/features/diagnostics/compareState';

export const diagnosticsRoutes = (): RouteObject[] => [
  { path: '/diagnostics', element: <ComparePage /> },
  { path: COMPARE_PATH, element: <ComparePage /> },
];
