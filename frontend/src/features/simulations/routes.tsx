import type { RouteObject } from 'react-router-dom';

import { CaseDetailsPage } from '@/features/simulations/CaseDetailsPage';
import { CasesPage } from '@/features/simulations/CasesPage';
import { SimulationDetailsPage } from '@/features/simulations/SimulationDetailsPage';
import { SimulationsPage } from '@/features/simulations/SimulationsPage';
import type { SimulationOut } from '@/types';

interface SimulationRoutesProps {
  simulations: SimulationOut[];
}

export const simulationsRoutes = ({ simulations }: SimulationRoutesProps): RouteObject[] => [
  {
    path: '/cases',
    element: <CasesPage simulations={simulations} />,
  },
  {
    path: '/cases/:id',
    element: <CaseDetailsPage simulations={simulations} />,
  },
  {
    path: '/simulations',
    element: <SimulationsPage simulations={simulations} />,
  },
  {
    path: '/simulations/:id',
    element: <SimulationDetailsPage />,
  },
];
