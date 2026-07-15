import type { ReactNode } from 'react';
import type { RouteObject } from 'react-router-dom';

import { CaseDetailsPage } from '@/features/simulations/CaseDetailsPage';
import { CasesPage } from '@/features/simulations/CasesPage';
import { SimulationDetailsPage } from '@/features/simulations/SimulationDetailsPage';
import { SimulationsPage } from '@/features/simulations/SimulationsPage';

interface SimulationRoutesProps {
  renderCaseCompareSection?: (options: { onClose: () => void }) => ReactNode;
  selectedCaseSimulationIdsByCase: Record<string, string[]>;
  setSelectedCaseSimulationIdsForCase: (caseId: string, ids: string[]) => void;
  selectedSimulationIds: string[];
  setSelectedSimulationIds: (ids: string[]) => void;
}

export const simulationsRoutes = ({
  renderCaseCompareSection,
  selectedCaseSimulationIdsByCase,
  setSelectedCaseSimulationIdsForCase,
  selectedSimulationIds,
  setSelectedSimulationIds,
}: SimulationRoutesProps): RouteObject[] => [
  {
    path: '/cases',
    element: <CasesPage />,
  },
  {
    path: '/cases/:id',
    element: (
      <CaseDetailsPage
        renderCompareSection={renderCaseCompareSection}
        selectedCaseSimulationIdsByCase={selectedCaseSimulationIdsByCase}
        setSelectedCaseSimulationIdsForCase={setSelectedCaseSimulationIdsForCase}
      />
    ),
  },
  {
    path: '/simulations',
    element: <SimulationsPage />,
  },
  {
    path: '/simulations/:id',
    element: (
      <SimulationDetailsPage
        selectedSimulationIds={selectedSimulationIds}
        setSelectedSimulationIds={setSelectedSimulationIds}
      />
    ),
  },
];
