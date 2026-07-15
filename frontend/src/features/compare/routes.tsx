import type { RouteObject } from 'react-router-dom';

import { ComparePage } from '@/features/compare/ComparePage';

interface CompareRoutesProps {
  selectedCaseSimulationIdsByCase: Record<string, string[]>;
  selectedSimulationIds: string[];
  setSelectedSimulationIds: (ids: string[]) => void;
}

export const compareRoutes = ({
  selectedCaseSimulationIdsByCase,
  selectedSimulationIds,
  setSelectedSimulationIds,
}: CompareRoutesProps): RouteObject[] => [
  {
    path: '/compare',
    element: (
      <ComparePage
        selectedCaseSimulationIdsByCase={selectedCaseSimulationIdsByCase}
        selectedSimulationIds={selectedSimulationIds}
        setSelectedSimulationIds={setSelectedSimulationIds}
      />
    ),
  },
];
