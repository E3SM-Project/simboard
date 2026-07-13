import type { ReactNode } from 'react';
import type { RouteObject } from 'react-router-dom';

import { CaseDetailsPage } from '@/features/simulations/CaseDetailsPage';
import { CasesPage } from '@/features/simulations/CasesPage';
import { SimulationDetailsPage } from '@/features/simulations/SimulationDetailsPage';
import { SimulationsPage } from '@/features/simulations/SimulationsPage';
import type { SimulationOut } from '@/types';

interface SimulationRoutesProps {
  renderCaseCompareSection?: (options: { onClose: () => void }) => ReactNode;
  simulations: SimulationOut[];
  selectedCaseSimulationIdsByCase: Record<string, string[]>;
  setSelectedCaseSimulationIdsForCase: (caseId: string, ids: string[]) => void;
  selectedSimulationIds: string[];
  setSelectedSimulationIds: (ids: string[]) => void;
}

export const simulationsRoutes = ({
  renderCaseCompareSection,
  simulations,
  selectedCaseSimulationIdsByCase,
  setSelectedCaseSimulationIdsForCase,
  selectedSimulationIds,
  setSelectedSimulationIds,
}: SimulationRoutesProps): RouteObject[] => [
  {
    path: '/cases',
    element: <CasesPage simulations={simulations} />,
  },
  {
    path: '/cases/:id',
    element: (
      <CaseDetailsPage
        renderCompareSection={renderCaseCompareSection}
        simulations={simulations}
        selectedCaseSimulationIdsByCase={selectedCaseSimulationIdsByCase}
        setSelectedCaseSimulationIdsForCase={setSelectedCaseSimulationIdsForCase}
      />
    ),
  },
  {
    path: '/simulations',
    element: <SimulationsPage simulations={simulations} />,
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
