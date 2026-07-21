import type { RouteObject } from 'react-router-dom';

import { HomePage } from '@/features/home/HomePage';
import type { Machine, Site } from '@/types';

interface HomeRoutesProps {
  machines: Machine[];
  sites: Site[];
}

export const homeRoutes = ({ machines, sites }: HomeRoutesProps): RouteObject[] => [
  {
    path: '/',
    element: <HomePage machines={machines} sites={sites} />,
  },
];
