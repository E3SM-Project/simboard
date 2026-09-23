import type { ReactNode } from 'react';
import { useRoutes } from 'react-router-dom';

import { AuthCallback } from '@/auth/AuthCallback';
import { ProtectedRoute } from '@/auth/ProtectedRoute';
import { aboutRoutes } from '@/features/about/routes';
import { catalogRoutes } from '@/features/catalog/routes';
import { homeRoutes } from '@/features/home/routes';
import { uploadRoutes } from '@/features/upload/routes';
import type { Machine } from '@/types/machine';
import type { Site } from '@/types/site';

interface RoutesProps {
  machines: Machine[];
  sites: Site[];
  renderCaseCompareSection?: (options: { caseId: string; onClose: () => void }) => ReactNode;
  selectedCaseExecutionIdsByCase: Record<string, string[]>;
  setSelectedCaseExecutionIdsForCase: (caseId: string, ids: string[]) => void;
}

export const AppRoutes = (props: RoutesProps) => {
  const routes = [
    ...homeRoutes(props),
    ...aboutRoutes(),
    ...catalogRoutes(props),

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
