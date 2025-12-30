import type { RouteObject } from 'react-router-dom';

import { DocsPage } from '@/features/docs/DocsPage';

export const docsRoutes = (): RouteObject[] => [
  {
    path: '/docs',
    element: <DocsPage />,
  },
];
