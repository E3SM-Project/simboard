import { useQueries } from '@tanstack/react-query';
import { AlertTriangle } from 'lucide-react';
import { useEffect, useMemo } from 'react';
import { Link } from 'react-router-dom';

import { getExecutionById } from '@/api/catalog';
import { normalizeSelectedExecutionIds } from '@/components/shared/normalizeSelectedExecutionIds';
import { Alert } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { LoadingState } from '@/components/ui/loading-state';
import { CompareWorkspace } from '@/features/compare/ComparePage';
import { useCase } from '@/lib/catalog/hooks/useCase';
import { catalogQueryKeys } from '@/lib/catalog/queryKeys';
import { caseDetailsPath } from '@/lib/catalog/urls';
import type { ExecutionOut } from '@/types';

interface CaseCompareRouteProps {
  caseId: string;
  onClose?: () => void;
  selectedCaseExecutionIdsByCase: Record<string, string[]>;
  setSelectedCaseExecutionIdsForCase: (caseId: string, ids: string[]) => void;
}

const EMPTY_SELECTED_EXECUTION_IDS: string[] = [];

export const CaseCompareRoute = ({
  caseId,
  onClose,
  selectedCaseExecutionIdsByCase,
  setSelectedCaseExecutionIdsForCase,
}: CaseCompareRouteProps) => {
  const { data: caseRecord, error, loading } = useCase(caseId);

  const caseExecutionIdSet = useMemo(
    () => new Set(caseRecord?.executions.map((execution) => execution.id) ?? []),
    [caseRecord],
  );

  const rawCaseSelectedExecutionIds = caseId
    ? normalizeSelectedExecutionIds(selectedCaseExecutionIdsByCase[caseId] ?? [])
    : EMPTY_SELECTED_EXECUTION_IDS;
  const caseSelectedExecutionIds = useMemo(
    () => rawCaseSelectedExecutionIds.filter((executionId) => caseExecutionIdSet.has(executionId)),
    [caseExecutionIdSet, rawCaseSelectedExecutionIds],
  );
  const detailQueries = useQueries({
    queries: caseSelectedExecutionIds.map((executionId) => ({
      queryKey: catalogQueryKeys.executions.detail(executionId),
      queryFn: () => getExecutionById(executionId),
    })),
  });
  const executionById = useMemo(
    () =>
      new Map(
        detailQueries
          .map((query) => query.data)
          .filter((execution): execution is ExecutionOut => execution != null)
          .map((execution) => [execution.id, execution]),
      ),
    [detailQueries],
  );
  const excludedExecutionCount =
    rawCaseSelectedExecutionIds.length - caseSelectedExecutionIds.length;

  useEffect(() => {
    if (!caseId || loading || !caseRecord) {
      return;
    }

    const hasSelectionDrift =
      rawCaseSelectedExecutionIds.length !== caseSelectedExecutionIds.length ||
      rawCaseSelectedExecutionIds.some(
        (executionId, index) => executionId !== caseSelectedExecutionIds[index],
      );

    if (hasSelectionDrift) {
      setSelectedCaseExecutionIdsForCase(caseId, caseSelectedExecutionIds);
    }
  }, [
    caseRecord,
    caseId,
    caseSelectedExecutionIds,
    loading,
    rawCaseSelectedExecutionIds,
    setSelectedCaseExecutionIdsForCase,
  ]);

  const renderableSelectedExecutions = caseSelectedExecutionIds
    .map((executionId) => executionById.get(executionId))
    .filter((execution): execution is ExecutionOut => execution != null);
  const renderableSelectedExecutionIds = renderableSelectedExecutions.map(
    (execution) => execution.id,
  );
  const missingExecutionCount =
    caseSelectedExecutionIds.length - renderableSelectedExecutionIds.length;
  const loadingExecutionCount = detailQueries.filter((query) => query.isPending).length;
  const failedDetailQueries = detailQueries.filter((query) => query.isError);
  const handleCaseSelectionChange = (ids: string[]) => {
    if (caseId) {
      setSelectedCaseExecutionIdsForCase(caseId, ids);
    }
  };

  if (!caseId) {
    return (
      <div className="rounded-xl border border-slate-200 bg-slate-50 px-6 py-8 text-center text-slate-500">
        Case compare route is missing case id.
      </div>
    );
  }

  if (loading) {
    return <LoadingState label="Loading case compare" />;
  }

  if (error) {
    return (
      <Alert variant="error" className="rounded-xl px-6 py-8 text-center">
        Error: {error}
      </Alert>
    );
  }

  if (!caseRecord) {
    return (
      <div className="rounded-xl border border-slate-200 bg-slate-50 px-6 py-8 text-center text-slate-500">
        Case not found
      </div>
    );
  }

  const caseDetailsHref =
    caseRecord.machineNames[0] && caseRecord.hpcUsernames[0]
      ? caseDetailsPath({
          machineName: caseRecord.machineNames[0],
          hpcUsername: caseRecord.hpcUsernames[0],
          caseName: caseRecord.name,
        })
      : '/cases';
  if (renderableSelectedExecutionIds.length < 2 && !onClose) {
    let message = 'Select at least two executions from this case to compare.';

    if (excludedExecutionCount > 0) {
      message = `Ignored ${excludedExecutionCount} stored execution${excludedExecutionCount === 1 ? '' : 's'} that no longer belong to this case.`;
    } else if (missingExecutionCount > 0) {
      message = 'Selected case executions are not available in the current compare dataset.';
    }

    return (
      <Alert variant="warning" className="rounded-2xl p-6 shadow-sm">
        <div className="flex items-start gap-3">
          <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0" />
          <div className="min-w-0">
            <h1 className="text-2xl font-semibold">Case Compare Needs More Executions</h1>
            <p className="mt-2">{message}</p>
            <div className="mt-4 flex flex-wrap gap-2">
              {onClose ? (
                <Button type="button" variant="outline" onClick={onClose}>
                  Hide Compare
                </Button>
              ) : (
                <Button asChild variant="outline">
                  <Link to={caseDetailsHref}>Back to Case</Link>
                </Button>
              )}
            </div>
          </div>
        </div>
      </Alert>
    );
  }

  const contextNotice =
    excludedExecutionCount > 0 || missingExecutionCount > 0 ? (
      <Alert variant="warning" role="group" className="mb-4 rounded-2xl p-4 shadow-sm">
        <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
          <div className="space-y-1">
            {excludedExecutionCount > 0 ? (
              <p>
                Ignored {excludedExecutionCount} selected execution
                {excludedExecutionCount === 1 ? '' : 's'} from outside this case.
              </p>
            ) : null}
            {loadingExecutionCount > 0 ? (
              <p role="status">
                Loading details for {loadingExecutionCount} selected execution
                {loadingExecutionCount === 1 ? '' : 's'}…
              </p>
            ) : null}
            {failedDetailQueries.length > 0 ? (
              <div role="alert" className="flex flex-wrap items-center gap-2">
                <p>
                  Could not load {failedDetailQueries.length} selected execution
                  {failedDetailQueries.length === 1 ? '' : 's'}.
                </p>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => failedDetailQueries.forEach((query) => void query.refetch())}
                >
                  Retry execution details
                </Button>
              </div>
            ) : null}
          </div>
        </div>
      </Alert>
    ) : undefined;

  return (
    <CompareWorkspace
      key={`case-compare:${caseId}`}
      caseComparison
      contextNotice={contextNotice}
      description="Review selected executions from this case side by side."
      embedded
      emptyStateActionHref={caseDetailsHref}
      emptyStateActionLabel="Hide Compare"
      emptyStateMessage="No case executions selected for comparison."
      hiddenStorageKey={`case_compare_hidden_cols:${caseId}`}
      labelColumnWidth={320}
      selectedExecutionIds={caseSelectedExecutionIds}
      selectedExecutions={renderableSelectedExecutions}
      setSelectedExecutionIds={handleCaseSelectionChange}
      showHeader={false}
      title={`Compare Case Executions: ${caseRecord.name}`}
    />
  );
};
