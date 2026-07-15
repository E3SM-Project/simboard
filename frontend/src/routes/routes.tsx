import type { ReactNode } from 'react';
import { useRoutes } from 'react-router-dom';

import { AuthCallback } from '@/auth/AuthCallback';
import { ProtectedRoute } from '@/auth/ProtectedRoute';
import { browseRoutes } from '@/features/browse/routes';
import { compareRoutes } from '@/features/compare/routes';
import { docsRoutes } from '@/features/docs/routes';
import { homeRoutes } from '@/features/home/routes';
import { simulationsRoutes } from '@/features/simulations/routes';
import { uploadRoutes } from '@/features/upload/routes';
import type { Machine } from '@/types/machine';

interface RoutesProps {
  machines: Machine[];
  renderCaseCompareSection?: (options: { onClose: () => void }) => ReactNode;
  selectedCaseSimulationIdsByCase: Record<string, string[]>;
  setSelectedCaseSimulationIdsForCase: (caseId: string, ids: string[]) => void;
  selectedSimulationIds: string[];
  setSelectedSimulationIds: (ids: string[]) => void;
}

export const AppRoutes = (props: RoutesProps) => {
  const routes = [
    ...homeRoutes(props),
    ...browseRoutes(props),
    ...simulationsRoutes(props),
    ...compareRoutes(props),
    ...docsRoutes(),

    {
      element: <ProtectedRoute />,
      children: uploadRoutes(props),
    },

    {
      path: '/auth/callback',
      element: <AuthCallback />,
    },

    {
      path: '*',
      element: <div className="p-8">404 - Page not found</div>,
    },
  ];

  return useRoutes(routes);
};
