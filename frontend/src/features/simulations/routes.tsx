import type { RouteObject } from 'react-router-dom';

import { CaseComparePage } from '@/features/compare/CaseComparePage';
import { CaseDetailsPage } from '@/features/simulations/CaseDetailsPage';
import { CasesPage } from '@/features/simulations/CasesPage';
import { SimulationDetailsPage } from '@/features/simulations/SimulationDetailsPage';
import { SimulationsPage } from '@/features/simulations/SimulationsPage';
import type { SimulationOut } from '@/types';

interface SimulationRoutesProps {
  simulations: SimulationOut[];
  selectedCaseSimulationIdsByCase: Record<string, string[]>;
  setSelectedCaseSimulationIdsForCase: (caseId: string, ids: string[]) => void;
  selectedSimulationIds: string[];
  setSelectedSimulationIds: (ids: string[]) => void;
}

export const simulationsRoutes = ({
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
        simulations={simulations}
        selectedCaseSimulationIdsByCase={selectedCaseSimulationIdsByCase}
        setSelectedCaseSimulationIdsForCase={setSelectedCaseSimulationIdsForCase}
      />
    ),
  },
  {
    path: '/cases/:id/compare',
    element: (
      <CaseComparePage
        simulations={simulations}
        selectedCaseSimulationIdsByCase={selectedCaseSimulationIdsByCase}
        setSelectedCaseSimulationIdsForCase={setSelectedCaseSimulationIdsForCase}
        setSelectedSimulationIds={setSelectedSimulationIds}
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
