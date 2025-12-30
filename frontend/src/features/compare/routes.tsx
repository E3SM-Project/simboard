import type { RouteObject } from 'react-router-dom';

import { ComparePage } from '@/features/compare/ComparePage';
import type { SimulationOut } from '@/types';

interface CompareRoutesProps {
  simulations: SimulationOut[];
  selectedSimulationIds: string[];
  setSelectedSimulationIds: (ids: string[]) => void;
  selectedSimulations: SimulationOut[];
}

export const compareRoutes = ({
  simulations,
  selectedSimulationIds,
  setSelectedSimulationIds,
  selectedSimulations,
}: CompareRoutesProps): RouteObject[] => [
  {
    path: '/compare',
    element: (
      <ComparePage
        simulations={simulations}
        selectedSimulationIds={selectedSimulationIds}
        setSelectedSimulationIds={setSelectedSimulationIds}
        selectedSimulations={selectedSimulations}
      />
    ),
  },
];
