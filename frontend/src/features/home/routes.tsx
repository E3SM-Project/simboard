import type { RouteObject } from 'react-router-dom';

import { HomePage } from '@/features/home/HomePage';
import type { Machine } from '@/types';

interface HomeRoutesProps {
  machines: Machine[];
}

export const homeRoutes = ({ machines }: HomeRoutesProps): RouteObject[] => [
  {
    path: '/',
    element: <HomePage machines={machines} />,
  },
];
