import { useQueries } from '@tanstack/react-query';
import { useEffect, useMemo } from 'react';

import { getExecutionById } from '@/api/catalog';
import { normalizeSelectedExecutionIds } from '@/components/shared/normalizeSelectedExecutionIds';
import { Alert } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { LoadingState } from '@/components/ui/loading-state';
import { CompareWorkspace } from '@/features/compare/ComparePage';
import { useCase } from '@/lib/catalog/hooks/useCase';
import { catalogQueryKeys } from '@/lib/catalog/queryKeys';
import type { ExecutionOut } from '@/types';

interface CaseCompareRouteProps {
  caseId: string;
  selectedCaseExecutionIdsByCase: Record<string, string[]>;
  setSelectedCaseExecutionIdsForCase: (caseId: string, ids: string[]) => void;
}

const EMPTY_SELECTED_EXECUTION_IDS: string[] = [];

export const CaseCompareRoute = ({
  caseId,
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
      <div className="rounded-xl border border-border bg-muted-subtle px-6 py-8 text-center text-muted-foreground">
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
      <div className="rounded-xl border border-border bg-muted-subtle px-6 py-8 text-center text-muted-foreground">
        Case not found
      </div>
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
      contextNotice={contextNotice}
      hiddenStorageKey={`case_compare_hidden_cols:${caseId}`}
      selectedExecutionIds={caseSelectedExecutionIds}
      selectedExecutions={renderableSelectedExecutions}
      setSelectedExecutionIds={handleCaseSelectionChange}
    />
  );
};
