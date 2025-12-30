import type { RouteObject } from 'react-router-dom';

import { HomePage } from '@/features/home/HomePage';
import type { Machine, SimulationOut } from '@/types';

interface HomeRoutesProps {
  simulations: SimulationOut[];
  machines: Machine[];
}

export const homeRoutes = ({ simulations, machines }: HomeRoutesProps): RouteObject[] => [
  {
    path: '/',
    element: <HomePage simulations={simulations} machines={machines} />,
  },
];
