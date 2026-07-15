import { useQueries } from '@tanstack/react-query';
import { AlertTriangle } from 'lucide-react';
import { useEffect, useMemo } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';

import { normalizeSelectedSimulationIds } from '@/components/shared/normalizeSelectedSimulationIds';
import { Button } from '@/components/ui/button';
import { CompareWorkspace } from '@/features/compare/ComparePage';
import { getSimulationById } from '@/features/simulations/api/api';
import { useCase } from '@/features/simulations/hooks/useCase';
import { catalogQueryKeys } from '@/features/simulations/queryKeys';
import type { SimulationOut } from '@/types';

interface CaseCompareRouteProps {
  onClose?: () => void;
  selectedCaseSimulationIdsByCase: Record<string, string[]>;
  setSelectedCaseSimulationIdsForCase: (caseId: string, ids: string[]) => void;
  setSelectedSimulationIds: (ids: string[]) => void;
}

const EMPTY_SELECTED_SIMULATION_IDS: string[] = [];

export const CaseCompareRoute = ({
  onClose,
  selectedCaseSimulationIdsByCase,
  setSelectedCaseSimulationIdsForCase,
  setSelectedSimulationIds,
}: CaseCompareRouteProps) => {
  const navigate = useNavigate();
  const { id: caseId } = useParams<{ id: string }>();

  const { data: caseRecord, error, loading } = useCase(caseId ?? '');

  const caseSimulationIdSet = useMemo(
    () => new Set(caseRecord?.simulations.map((simulation) => simulation.id) ?? []),
    [caseRecord],
  );

  const rawCaseSelectedSimulationIds = caseId
    ? normalizeSelectedSimulationIds(selectedCaseSimulationIdsByCase[caseId] ?? [])
    : EMPTY_SELECTED_SIMULATION_IDS;
  const caseSelectedSimulationIds = useMemo(
    () =>
      rawCaseSelectedSimulationIds.filter((simulationId) => caseSimulationIdSet.has(simulationId)),
    [caseSimulationIdSet, rawCaseSelectedSimulationIds],
  );
  const detailQueries = useQueries({
    queries: caseSelectedSimulationIds.map((simulationId) => ({
      queryKey: catalogQueryKeys.simulations.detail(simulationId),
      queryFn: () => getSimulationById(simulationId),
    })),
  });
  const simulationById = useMemo(
    () =>
      new Map(
        detailQueries
          .map((query) => query.data)
          .filter((simulation): simulation is SimulationOut => simulation != null)
          .map((simulation) => [simulation.id, simulation]),
      ),
    [detailQueries],
  );
  const excludedSimulationCount =
    rawCaseSelectedSimulationIds.length - caseSelectedSimulationIds.length;

  useEffect(() => {
    if (!caseId || loading || !caseRecord) {
      return;
    }

    const hasSelectionDrift =
      rawCaseSelectedSimulationIds.length !== caseSelectedSimulationIds.length ||
      rawCaseSelectedSimulationIds.some(
        (simulationId, index) => simulationId !== caseSelectedSimulationIds[index],
      );

    if (hasSelectionDrift) {
      setSelectedCaseSimulationIdsForCase(caseId, caseSelectedSimulationIds);
    }
  }, [
    caseRecord,
    caseId,
    caseSelectedSimulationIds,
    loading,
    rawCaseSelectedSimulationIds,
    setSelectedCaseSimulationIdsForCase,
  ]);

  const renderableSelectedSimulations = caseSelectedSimulationIds
    .map((simulationId) => simulationById.get(simulationId))
    .filter((simulation): simulation is SimulationOut => simulation != null);
  const renderableSelectedSimulationIds = renderableSelectedSimulations.map(
    (simulation) => simulation.id,
  );
  const missingSimulationCount =
    caseSelectedSimulationIds.length - renderableSelectedSimulationIds.length;
  const globalCompareCandidateIds = caseSelectedSimulationIds;

  const openGlobalCompare = (ids: string[]) => {
    const nextIds = normalizeSelectedSimulationIds(ids);
    setSelectedSimulationIds(nextIds);
    navigate('/compare', {
      state: {
        selectedSimulationIds: nextIds,
        selectedSimulations: renderableSelectedSimulations.filter((simulation) =>
          nextIds.includes(simulation.id),
        ),
      },
    });
  };

  const handleCaseSelectionChange = (ids: string[]) => {
    if (caseId) {
      setSelectedCaseSimulationIdsForCase(caseId, ids);
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
    return (
      <div className="rounded-xl border border-slate-200 bg-slate-50 px-6 py-8 text-center text-slate-500">
        Loading case compare…
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded-xl border border-red-200 bg-red-50 px-6 py-8 text-center text-red-700">
        Error: {error}
      </div>
    );
  }

  if (!caseRecord) {
    return (
      <div className="rounded-xl border border-slate-200 bg-slate-50 px-6 py-8 text-center text-slate-500">
        Case not found
      </div>
    );
  }

  const caseDetailsHref = `/cases/${caseId}`;
  const canOpenGlobalCompare = globalCompareCandidateIds.length >= 2;

  if (renderableSelectedSimulationIds.length < 2) {
    let message = 'Select at least two runs from this case to compare.';

    if (excludedSimulationCount > 0) {
      message = `Ignored ${excludedSimulationCount} stored run${excludedSimulationCount === 1 ? '' : 's'} that no longer belong to this case.`;
    } else if (missingSimulationCount > 0) {
      message = 'Selected case runs are not available in the current compare dataset.';
    }

    return (
      <div className="rounded-2xl border border-amber-200 bg-amber-50/80 p-6 shadow-sm">
        <div className="flex items-start gap-3">
          <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-amber-700" />
          <div className="min-w-0">
            <h1 className="text-2xl font-semibold text-slate-950">Case Compare Needs More Runs</h1>
            <p className="mt-2 text-sm text-slate-700">{message}</p>
            <div className="mt-4 flex flex-wrap gap-2">
              {onClose ? (
                <Button type="button" variant="outline" onClick={onClose}>
                  Hide Compare
                </Button>
              ) : (
                <Button asChild variant="outline">
                  <Link to={caseDetailsHref}>Back to Simulations</Link>
                </Button>
              )}
              {canOpenGlobalCompare ? (
                <Button type="button" onClick={() => openGlobalCompare(globalCompareCandidateIds)}>
                  Open in Cross-Case Compare
                </Button>
              ) : null}
            </div>
          </div>
        </div>
      </div>
    );
  }

  const contextNotice =
    excludedSimulationCount > 0 || missingSimulationCount > 0 ? (
      <section className="mb-4 rounded-2xl border border-amber-200 bg-amber-50/80 p-4 text-sm text-slate-700 shadow-sm">
        <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
          <div className="space-y-1">
            {excludedSimulationCount > 0 ? (
              <p>
                Ignored {excludedSimulationCount} selected run
                {excludedSimulationCount === 1 ? '' : 's'} from outside this case.
              </p>
            ) : null}
            {missingSimulationCount > 0 ? (
              <p>
                Skipped {missingSimulationCount} case run
                {missingSimulationCount === 1 ? '' : 's'} missing from loaded simulation details.
              </p>
            ) : null}
          </div>
          {excludedSimulationCount > 0 ? (
            <Button
              type="button"
              variant="outline"
              onClick={() => openGlobalCompare(globalCompareCandidateIds)}
            >
              Open in Cross-Case Compare
            </Button>
          ) : null}
        </div>
      </section>
    ) : undefined;

  return (
    <CompareWorkspace
      key={`case-compare:${caseId}`}
      contextNotice={contextNotice}
      description="Review selected executions from this case side by side."
      embedded
      emptyStateActionHref={caseDetailsHref}
      emptyStateActionLabel="Hide Compare"
      emptyStateMessage="No case executions selected for comparison."
      hiddenStorageKey={`case_compare_hidden_cols:${caseId}`}
      labelColumnWidth={320}
      selectedSimulationIds={renderableSelectedSimulationIds}
      selectedSimulations={renderableSelectedSimulations}
      setSelectedSimulationIds={handleCaseSelectionChange}
      showHeader={false}
      title={`Compare Case Executions: ${caseRecord.name}`}
    />
  );
};
