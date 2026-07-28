import type { RouteObject } from 'react-router-dom';

import { ComparePage } from '@/features/compare/ComparePage';

interface CompareRoutesProps {
  selectedCaseExecutionIdsByCase: Record<string, string[]>;
  selectedExecutionIds: string[];
  setSelectedExecutionIds: (ids: string[]) => void;
}

export const compareRoutes = ({
  selectedCaseExecutionIdsByCase,
  selectedExecutionIds,
  setSelectedExecutionIds,
}: CompareRoutesProps): RouteObject[] => [
  {
    path: '/compare',
    element: (
      <ComparePage
        selectedCaseExecutionIdsByCase={selectedCaseExecutionIdsByCase}
        selectedExecutionIds={selectedExecutionIds}
        setSelectedExecutionIds={setSelectedExecutionIds}
      />
    ),
  },
];
