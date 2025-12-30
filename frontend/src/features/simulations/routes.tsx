import type { RouteObject } from 'react-router-dom';

import { SimulationDetailsPage } from '@/features/simulations/SimulationDetailsPage';
import { SimulationsPage } from '@/features/simulations/SimulationsPage';
import type { SimulationOut } from '@/types';

interface SimulationRoutesProps {
  simulations: SimulationOut[];
}

export const simulationsRoutes = ({ simulations }: SimulationRoutesProps): RouteObject[] => [
  {
    path: '/simulations',
    element: <SimulationsPage simulations={simulations} />,
  },
  {
    path: '/simulations/:id',
    element: <SimulationDetailsPage />,
  },
];
