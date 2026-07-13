import type { RouteObject } from 'react-router-dom';

import { ComparePage } from '@/features/compare/ComparePage';
import type { SimulationOut } from '@/types';

interface CompareRoutesProps {
  simulations: SimulationOut[];
  selectedCaseSimulationIdsByCase: Record<string, string[]>;
  selectedSimulationIds: string[];
  setSelectedSimulationIds: (ids: string[]) => void;
  selectedSimulations: SimulationOut[];
}

export const compareRoutes = ({
  simulations,
  selectedCaseSimulationIdsByCase,
  selectedSimulationIds,
  setSelectedSimulationIds,
  selectedSimulations,
}: CompareRoutesProps): RouteObject[] => [
  {
    path: '/compare',
    element: (
      <ComparePage
        selectedCaseSimulationIdsByCase={selectedCaseSimulationIdsByCase}
        selectedSimulationIds={selectedSimulationIds}
        simulations={simulations}
        setSelectedSimulationIds={setSelectedSimulationIds}
        selectedSimulations={selectedSimulations}
      />
    ),
  },
];
