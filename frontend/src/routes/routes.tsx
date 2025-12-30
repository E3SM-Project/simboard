import { useRoutes } from 'react-router-dom';

import { AuthCallback } from '@/auth/AuthCallback';
import { ProtectedRoute } from '@/auth/ProtectedRoute';
import { browseRoutes } from '@/features/browse/routes';
import { compareRoutes } from '@/features/compare/routes';
import { docsRoutes } from '@/features/docs/routes';
import { homeRoutes } from '@/features/home/routes';
import { simulationsRoutes } from '@/features/simulations/routes';
import { uploadRoutes } from '@/features/upload/routes';
import type { Machine, SimulationOut } from '@/types/index';

interface RoutesProps {
  simulations: SimulationOut[];
  machines: Machine[];
  selectedSimulationIds: string[];
  setSelectedSimulationIds: (ids: string[]) => void;
  selectedSimulations: SimulationOut[];
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
