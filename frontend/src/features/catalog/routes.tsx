import type { ReactNode } from 'react';
import type { RouteObject } from 'react-router-dom';

import { CaseDetailsPage } from '@/features/catalog/CaseDetailsPage';
import { CasesPage } from '@/features/catalog/CasesPage';
import { ExecutionDetailsPage } from '@/features/catalog/ExecutionDetailsPage';
import { ExecutionsPage } from '@/features/catalog/ExecutionsPage';
import { LegacyExecutionRedirect } from '@/features/catalog/LegacyExecutionRedirect';

interface CatalogRoutesProps {
  renderCaseCompareSection?: (options: { onClose: () => void }) => ReactNode;
  selectedCaseExecutionIdsByCase: Record<string, string[]>;
  setSelectedCaseExecutionIdsForCase: (caseId: string, ids: string[]) => void;
  selectedExecutionIds: string[];
  setSelectedExecutionIds: (ids: string[]) => void;
}

export const catalogRoutes = ({
  renderCaseCompareSection,
  selectedCaseExecutionIdsByCase,
  setSelectedCaseExecutionIdsForCase,
  selectedExecutionIds,
  setSelectedExecutionIds,
}: CatalogRoutesProps): RouteObject[] => [
  {
    path: '/cases',
    element: <CasesPage />,
  },
  {
    path: '/cases/:id',
    element: (
      <CaseDetailsPage
        renderCompareSection={renderCaseCompareSection}
        selectedCaseExecutionIdsByCase={selectedCaseExecutionIdsByCase}
        setSelectedCaseExecutionIdsForCase={setSelectedCaseExecutionIdsForCase}
      />
    ),
  },
  {
    path: '/executions',
    element: <ExecutionsPage />,
  },
  {
    path: '/executions/:id',
    element: (
      <ExecutionDetailsPage
        selectedExecutionIds={selectedExecutionIds}
        setSelectedExecutionIds={setSelectedExecutionIds}
      />
    ),
  },
  {
    path: '/simulations',
    element: <LegacyExecutionRedirect />,
  },
  {
    path: '/simulations/:id',
    element: <LegacyExecutionRedirect />,
  },
];
