import type { RouteObject } from 'react-router-dom';

import { ComparePage } from '@/features/diagnostics/ComparePage';
import { COMPARE_PATH } from '@/features/diagnostics/compareState';
import { StartPage } from '@/features/diagnostics/StartPage';

export const diagnosticsRoutes = (): RouteObject[] => [
  { path: '/diagnostics', element: <StartPage /> },
  { path: COMPARE_PATH, element: <ComparePage /> },
];
