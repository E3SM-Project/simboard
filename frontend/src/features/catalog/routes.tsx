import type { ReactNode } from 'react';
import type { RouteObject } from 'react-router-dom';

import { CaseDetailsPage } from '@/features/catalog/CaseDetailsPage';
import { CasesPage } from '@/features/catalog/CasesPage';
import { ExecutionDetailsPage } from '@/features/catalog/ExecutionDetailsPage';

interface CatalogRoutesProps {
  renderCaseCompareSection?: (options: { caseId: string; onClose: () => void }) => ReactNode;
  renderCaseDiagnostics?: (options: { caseId: string; caseName: string }) => ReactNode;
  selectedCaseExecutionIdsByCase: Record<string, string[]>;
  setSelectedCaseExecutionIdsForCase: (caseId: string, ids: string[]) => void;
}

export const catalogRoutes = ({
  renderCaseCompareSection,
  renderCaseDiagnostics,
  selectedCaseExecutionIdsByCase,
  setSelectedCaseExecutionIdsForCase,
}: CatalogRoutesProps): RouteObject[] => [
  {
    path: '/cases',
    element: <CasesPage />,
  },
  {
    path: '/cases/:machine/:hpcUsername/:caseName',
    element: (
      <CaseDetailsPage
        renderCompareSection={renderCaseCompareSection}
        renderDiagnostics={renderCaseDiagnostics}
        selectedCaseExecutionIdsByCase={selectedCaseExecutionIdsByCase}
        setSelectedCaseExecutionIdsForCase={setSelectedCaseExecutionIdsForCase}
      />
    ),
  },
  {
    path: '/cases/:machine/:hpcUsername/:caseName/:executionId',
    element: <ExecutionDetailsPage />,
  },
];
