import { ArrowLeft, ChevronDown, Pin, Search, Share2 } from 'lucide-react';
import { Fragment, useEffect, useMemo, useState } from 'react';
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Checkbox } from '@/components/ui/checkbox';
import { Input } from '@/components/ui/input';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { TableCellText } from '@/components/ui/table-cell-text';
import {
  formatCaseDate,
  formatCaseHashLabel,
  formatSimulationDateRange,
  getDefaultExpandedGroupKeys,
  getSimulationSummaryDateWindow,
  groupSimulationSummaries,
  matchesSimulationGroupFilter,
  MISSING_CASE_HASH_LABEL,
  type SimulationSummaryGroupFilter,
} from '@/features/simulations/caseUtils';
import { useCase } from '@/features/simulations/hooks/useCase';
import { toast } from '@/hooks/use-toast';
import type { SimulationOut, SimulationSummaryOut } from '@/types';

const DetailField = ({
  label,
  value,
  mono = false,
  title,
}: {
  label: string;
  value: React.ReactNode;
  mono?: boolean;
  title?: string;
}) => (
  <div className="min-w-0 space-y-1" title={title}>
    <div className="text-[11px] font-medium uppercase tracking-[0.18em] text-slate-500">
      {label}
    </div>
    <div
      className={`truncate font-semibold text-slate-950 ${mono ? 'font-mono text-xs' : 'text-sm'}`}
    >
      {value}
    </div>
  </div>
);

const summarizeValues = (values: string[]) => {
  if (values.length === 0) return '—';
  if (values.length === 1) return values[0];

  return `${values[0]} +${values.length - 1}`;
};

const summarizeDistinctValues = (values: Array<string | null | undefined>) => {
  const uniqueValues = [...new Set(values.filter((value): value is string => Boolean(value)))];

  if (uniqueValues.length === 0) return '—';
  if (uniqueValues.length === 1) return uniqueValues[0];

  return `${uniqueValues[0]} +${uniqueValues.length - 1}`;
};

const formatRunDateRange = (startDate?: string | null, endDate?: string | null) => {
  if (!startDate && !endDate) return '—';

  return `${startDate?.slice(0, 10) ?? '—'} → ${endDate?.slice(0, 10) ?? '—'}`;
};

const formatGroupSimulationWindow = (simulations: SimulationSummaryOut[]) => {
  const { startDate, endDate } = getSimulationSummaryDateWindow(simulations);

  return `${formatCaseDate(startDate)} → ${formatCaseDate(endDate)}`;
};

const pluralize = (count: number, singular: string, plural = `${singular}s`) =>
  `${count} ${count === 1 ? singular : plural}`;

interface CaseDetailsPageProps {
  simulations: SimulationOut[];
  selectedSimulationIds: string[];
  setSelectedSimulationIds: (ids: string[]) => void;
}

interface GroupSimulation {
  summary: SimulationSummaryOut;
  details?: SimulationOut;
}

type SimulationViewMode = 'grouped' | 'flat';

const MAX_SELECTION = 5;
const SCROLLABLE_GROUPS_THRESHOLD = 5;
const SCROLLABLE_FLAT_ROWS_THRESHOLD = 10;
const GROUP_FILTER_OPTIONS: Array<{ value: SimulationSummaryGroupFilter; label: string }> = [
  { value: 'all', label: 'All' },
  { value: 'multiRun', label: 'Multi-run' },
  { value: 'missing', label: 'Missing hash' },
];

const getGroupRunDateWindow = (simulations: GroupSimulation[]) => {
  const datedRuns = simulations.filter(
    ({ details }) => details?.runStartDate != null || details?.runEndDate != null,
  );

  if (datedRuns.length === 0) {
    return '—';
  }

  let earliestStart: string | null = null;
  let latestEnd: string | null = null;

  for (const { details } of datedRuns) {
    const runStartDate = details?.runStartDate ?? details?.runEndDate ?? null;
    const runEndDate = details?.runEndDate ?? details?.runStartDate ?? null;

    if (runStartDate && (earliestStart == null || runStartDate < earliestStart)) {
      earliestStart = runStartDate;
    }

    if (runEndDate && (latestEnd == null || runEndDate > latestEnd)) {
      latestEnd = runEndDate;
    }
  }

  return formatRunDateRange(earliestStart, latestEnd);
};

const countDistinctValues = (values: string[]) => new Set(values).size;

export const CaseDetailsPage = ({
  simulations: allSimulations,
  selectedSimulationIds,
  setSelectedSimulationIds,
}: CaseDetailsPageProps) => {
  const { id } = useParams<{ id: string }>();
  const location = useLocation();
  const navigate = useNavigate();
  const [viewMode, setViewMode] = useState<SimulationViewMode>('flat');
  const [groupFilterMode, setGroupFilterMode] = useState<SimulationSummaryGroupFilter>('all');
  const [caseHashQuery, setCaseHashQuery] = useState('');
  const [expandedGroupKeys, setExpandedGroupKeys] = useState<string[]>([]);
  const { data: caseRecord, loading, error } = useCase(id ?? '');
  const currentPath = `${location.pathname}${location.search}`;
  const state = location.state as { from?: string } | null;
  const backHref = typeof state?.from === 'string' ? state.from : '/cases';
  const caseSimulations = useMemo(() => caseRecord?.simulations ?? [], [caseRecord?.simulations]);
  const simulationDetailsById = useMemo(
    () => new Map(allSimulations.map((simulation) => [simulation.id, simulation])),
    [allSimulations],
  );
  const rawSimulationGroups = useMemo(
    () => groupSimulationSummaries(caseSimulations),
    [caseSimulations],
  );
  const simulationGroups = useMemo(
    () =>
      rawSimulationGroups.map((group) => ({
        ...group,
        simulations: group.simulations.map((simulation) => ({
          summary: simulation,
          details: simulationDetailsById.get(simulation.id),
        })),
      })),
    [rawSimulationGroups, simulationDetailsById],
  );
  const sortedSimulationGroups = useMemo(() => {
    const getLatestRunTime = (simulations: GroupSimulation[]) => {
      const timestamps = simulations
        .map(
          ({ details, summary }) =>
            details?.runEndDate ??
            details?.runStartDate ??
            summary.simulationEndDate ??
            summary.simulationStartDate,
        )
        .map((value) => new Date(value).getTime())
        .filter((value) => !Number.isNaN(value));

      return timestamps.length > 0 ? Math.max(...timestamps) : 0;
    };

    return [...simulationGroups].sort((left, right) => {
      if (left.isFallback !== right.isFallback) {
        return left.isFallback ? 1 : -1;
      }

      const leftIsMultiRun = left.simulations.length > 1;
      const rightIsMultiRun = right.simulations.length > 1;
      if (leftIsMultiRun !== rightIsMultiRun) {
        return leftIsMultiRun ? -1 : 1;
      }

      const runDateDifference =
        getLatestRunTime(right.simulations) - getLatestRunTime(left.simulations);
      if (runDateDifference !== 0) {
        return runDateDifference;
      }

      return left.label.localeCompare(right.label);
    });
  }, [simulationGroups]);
  const caseHashGroupCount = rawSimulationGroups.filter((group) => !group.isFallback).length;
  const missingCaseHashCount =
    rawSimulationGroups.find((group) => group.isFallback)?.simulations.length ?? 0;
  const allRunsMissingCaseHash =
    caseRecord != null &&
    caseRecord.simulations.length > 0 &&
    caseHashGroupCount === 0 &&
    missingCaseHashCount > 0;
  const normalizedCaseHashQuery = caseHashQuery.trim().toLowerCase();
  const filteredSimulationGroups = useMemo(
    () =>
      sortedSimulationGroups.filter((group) => {
        if (!matchesSimulationGroupFilter(group, groupFilterMode)) {
          return false;
        }

        if (normalizedCaseHashQuery.length === 0) {
          return true;
        }

        if (group.isFallback) {
          return MISSING_CASE_HASH_LABEL.toLowerCase().includes(normalizedCaseHashQuery);
        }

        return (group.caseHash ?? '').toLowerCase().startsWith(normalizedCaseHashQuery);
      }),
    [groupFilterMode, normalizedCaseHashQuery, sortedSimulationGroups],
  );
  const filteredFlatSimulations = useMemo(
    () => filteredSimulationGroups.flatMap((group) => group.simulations),
    [filteredSimulationGroups],
  );
  const visibleSimulationIds = useMemo(
    () => new Set(filteredFlatSimulations.map(({ summary }) => summary.id)),
    [filteredFlatSimulations],
  );
  const selectedCurrentCaseSimulationIds = caseSimulations
    .map((simulation) => simulation.id)
    .filter((simulationId) => selectedSimulationIds.includes(simulationId));
  const hiddenSelectedCount = selectedCurrentCaseSimulationIds.filter(
    (simulationId) => !visibleSimulationIds.has(simulationId),
  ).length;
  const hasActiveGroupFilters = groupFilterMode !== 'all' || normalizedCaseHashQuery.length > 0;
  const showGroupActions = filteredSimulationGroups.length > 1;
  const useScrollableGroupsPanel =
    viewMode === 'grouped'
      ? filteredSimulationGroups.length > SCROLLABLE_GROUPS_THRESHOLD
      : filteredFlatSimulations.length > SCROLLABLE_FLAT_ROWS_THRESHOLD;

  useEffect(() => {
    setExpandedGroupKeys(getDefaultExpandedGroupKeys(sortedSimulationGroups));
  }, [sortedSimulationGroups]);

  useEffect(() => {
    const visibleGroupKeys = new Set(filteredSimulationGroups.map((group) => group.key));
    setExpandedGroupKeys((currentKeys) => currentKeys.filter((key) => visibleGroupKeys.has(key)));
  }, [filteredSimulationGroups]);

  const handleShareCase = async () => {
    if (!id) return;

    const shareUrl = new URL(`/cases/${id}`, window.location.origin).toString();
    const canUseWebShare = typeof navigator.share === 'function';

    try {
      if (canUseWebShare) {
        await navigator.share({
          title: caseRecord?.name ?? 'SimBoard Case',
          text: caseRecord?.name ?? 'SimBoard Case',
          url: shareUrl,
        });
      } else {
        await navigator.clipboard.writeText(shareUrl);
      }

      toast({
        title: 'Case link ready',
        description: canUseWebShare ? 'Share dialog opened.' : 'Case URL copied to clipboard.',
      });
    } catch (error) {
      if (error instanceof DOMException && error.name === 'AbortError') {
        return;
      }

      toast({
        title: 'Unable to share case',
        description: 'Try copying the page URL directly from your browser.',
        variant: 'destructive',
      });
    }
  };

  if (!id) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center">
        <div className="text-center text-gray-500">Invalid case ID</div>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center">
        <div className="text-center text-gray-500">Loading case details…</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center">
        <div className="text-center text-red-600">Error: {error}</div>
      </div>
    );
  }

  if (!caseRecord) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center">
        <div className="text-center text-gray-500">Case not found</div>
      </div>
    );
  }
  const machineSummary = summarizeValues(caseRecord.machineNames);
  const hpcUsernameSummary = summarizeValues(caseRecord.hpcUsernames);
  const isCompareButtonDisabled = selectedSimulationIds.length < 2;
  const filteredExecutionCount = filteredFlatSimulations.length;
  const activeSimulationCount =
    viewMode === 'grouped' ? filteredSimulationGroups.length : filteredExecutionCount;
  const totalSimulationCount =
    viewMode === 'grouped' ? simulationGroups.length : caseRecord.simulations.length;
  const summaryHeadline =
    caseRecord.simulations.length === 0
      ? '0 runs'
      : allRunsMissingCaseHash
        ? `${caseRecord.simulations.length} runs, all without Case Hash`
        : `${caseRecord.simulations.length} runs in ${caseHashGroupCount} Case Hash ${
            caseHashGroupCount === 1 ? 'group' : 'groups'
          }`;
  const simulationsIntro = allRunsMissingCaseHash
    ? 'Every run in this case is missing a Case Hash, so grouped view shows one fallback group.'
    : 'Grouped view clusters runs by Case Hash and keeps missing-hash runs in a fallback group.';
  const showingFallbackOnlyGroup =
    viewMode === 'grouped' &&
    filteredSimulationGroups.length === 1 &&
    filteredSimulationGroups[0]?.isFallback === true;
  const statusSummary =
    viewMode === 'grouped'
      ? showingFallbackOnlyGroup
        ? `1 fallback group containing ${pluralize(filteredExecutionCount, 'execution')}`
        : `Showing ${activeSimulationCount} of ${totalSimulationCount} groups containing ${pluralize(
            filteredExecutionCount,
            'execution',
          )}`
      : `Showing ${activeSimulationCount} of ${totalSimulationCount} executions from ${pluralize(
          filteredSimulationGroups.filter((group) => !group.isFallback).length,
          'Case Hash group',
        )}`;

  const toggleSimulationSelection = (simulationId: string) => {
    if (selectedSimulationIds.includes(simulationId)) {
      setSelectedSimulationIds(selectedSimulationIds.filter((id) => id !== simulationId));
      return;
    }

    if (selectedSimulationIds.length >= MAX_SELECTION) {
      return;
    }

    setSelectedSimulationIds([...selectedSimulationIds, simulationId]);
  };

  const toggleGroupExpansion = (groupKey: string, open: boolean) => {
    setExpandedGroupKeys((currentKeys) => {
      if (!open) {
        return currentKeys.filter((key) => key !== groupKey);
      }

      if (currentKeys.length > 1) {
        return [groupKey];
      }

      return currentKeys[0] === groupKey ? currentKeys : [groupKey];
    });
  };

  const handleExpandAllGroups = () => {
    setExpandedGroupKeys(filteredSimulationGroups.map((group) => group.key));
  };

  const handleCollapseAllGroups = () => {
    setExpandedGroupKeys([]);
  };

  const resetGroupFilters = () => {
    setGroupFilterMode('all');
    setCaseHashQuery('');
  };

  return (
    <div className="mx-auto w-full max-w-[1200px] space-y-6 px-6 py-8">
      <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
        <div>
          <Button variant="outline" size="sm" asChild className="mb-3">
            <Link to={backHref}>
              <ArrowLeft className="h-4 w-4" />
              Back
            </Link>
          </Button>
          <h1 className="text-2xl font-bold">{caseRecord.name}</h1>
        </div>
        <div className="flex items-center gap-2 self-start">
          <Button variant="outline" size="sm" type="button" onClick={handleShareCase}>
            <Share2 className="h-4 w-4" />
            Share Case
          </Button>
        </div>
      </div>

      <div>
        <Card className="border-slate-200 bg-slate-50/40 shadow-sm">
          <CardContent className="space-y-4 p-4">
            <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
              <div className="space-y-1">
                <p className="text-xs font-medium uppercase tracking-[0.18em] text-slate-500">
                  Case summary
                </p>
                <h2 className="text-lg font-semibold text-slate-950">{summaryHeadline}</h2>
              </div>
              <div className="flex flex-wrap gap-2">
                {caseRecord.caseGroup ? (
                  <Badge variant="outline">{caseRecord.caseGroup}</Badge>
                ) : null}
              </div>
            </div>

            <div className="grid gap-x-6 gap-y-3 border-t border-slate-200 pt-3 sm:grid-cols-2 xl:grid-cols-5">
              <DetailField label="Runs" value={caseRecord.simulations.length} />
              <DetailField label="Case Hash groups" value={caseHashGroupCount} />
              <DetailField
                label="Machines"
                value={machineSummary}
                title={
                  caseRecord.machineNames.length > 1
                    ? caseRecord.machineNames.join(', ')
                    : undefined
                }
              />
              <DetailField
                label="HPC users"
                value={hpcUsernameSummary}
                title={
                  caseRecord.hpcUsernames.length > 1
                    ? caseRecord.hpcUsernames.join(', ')
                    : undefined
                }
              />
              <DetailField label="Last updated" value={formatCaseDate(caseRecord.updatedAt)} />
            </div>
          </CardContent>
        </Card>
      </div>

      <section className="space-y-4">
        <div className="rounded-2xl border border-slate-200 bg-white shadow-sm">
          <div className="flex flex-col gap-4 border-b border-slate-200 px-5 py-4 xl:flex-row xl:items-start xl:justify-between">
            <div className="space-y-2">
              <h2 className="text-xl font-semibold">Simulations</h2>
              <p className="max-w-3xl text-sm text-muted-foreground">{simulationsIntro}</p>
            </div>
          </div>

          <div className="space-y-4 px-5 py-4">
            <div className="rounded-xl border border-slate-200 bg-slate-50/70 p-4">
              <div className="grid gap-4 xl:grid-cols-[minmax(0,1.4fr)_minmax(22rem,1fr)]">
                <div className="space-y-4">
                  <div className="space-y-2">
                    <div className="text-xs font-medium uppercase tracking-[0.18em] text-slate-500">
                      View
                    </div>
                    <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 xl:max-w-md">
                      <Button
                        type="button"
                        size="sm"
                        variant={viewMode === 'flat' ? 'default' : 'outline'}
                        onClick={() => setViewMode('flat')}
                        className="justify-center whitespace-nowrap"
                      >
                        All executions
                      </Button>
                      <Button
                        type="button"
                        size="sm"
                        variant={viewMode === 'grouped' ? 'default' : 'outline'}
                        onClick={() => setViewMode('grouped')}
                        className="justify-center whitespace-nowrap"
                      >
                        Grouped by Case Hash
                      </Button>
                    </div>
                  </div>

                  <div className="space-y-2">
                    <div className="text-xs font-medium uppercase tracking-[0.18em] text-slate-500">
                      Filters
                    </div>
                    <div className="flex flex-wrap gap-2">
                      {GROUP_FILTER_OPTIONS.map((option) => (
                        <Button
                          key={option.value}
                          type="button"
                          size="sm"
                          variant={groupFilterMode === option.value ? 'default' : 'outline'}
                          onClick={() => setGroupFilterMode(option.value)}
                        >
                          {option.label}
                        </Button>
                      ))}
                      {hasActiveGroupFilters ? (
                        <Button type="button" variant="ghost" size="sm" onClick={resetGroupFilters}>
                          Reset filters
                        </Button>
                      ) : null}
                    </div>
                  </div>
                </div>

                <div className="space-y-4">
                  <div className="space-y-2">
                    <div className="text-xs font-medium uppercase tracking-[0.18em] text-slate-500">
                      Search
                    </div>
                    <div className="relative">
                      <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
                      <Input
                        value={caseHashQuery}
                        onChange={(event) => setCaseHashQuery(event.target.value)}
                        placeholder="Filter Case Hash prefix"
                        className="bg-white pl-9"
                        aria-label="Filter Case Hash prefix"
                      />
                    </div>
                  </div>

                  <div className="space-y-2">
                    <div className="text-xs font-medium uppercase tracking-[0.18em] text-slate-500">
                      Actions
                    </div>
                    <div className="flex flex-col gap-2">
                      <div className="flex flex-wrap items-center gap-2">
                        <div className="rounded-md border border-slate-200 bg-white px-3 py-1.5 text-sm text-slate-600">
                          Selected{' '}
                          <span className="font-semibold text-slate-950">
                            {selectedSimulationIds.length}
                          </span>{' '}
                          / {MAX_SELECTION}
                        </div>
                        <Button
                          type="button"
                          size="sm"
                          onClick={() => navigate('/compare')}
                          disabled={isCompareButtonDisabled}
                        >
                          Compare Selected
                        </Button>
                        {selectedSimulationIds.length > 0 ? (
                          <Button
                            type="button"
                            variant="ghost"
                            size="sm"
                            className="text-slate-600 hover:text-slate-900"
                            onClick={() => setSelectedSimulationIds([])}
                          >
                            Deselect all
                          </Button>
                        ) : null}
                      </div>

                      <div className="flex flex-wrap items-center gap-2">
                        <div
                          aria-hidden={viewMode !== 'grouped' || !showGroupActions}
                          className={`inline-flex items-center gap-1 rounded-md border border-slate-200 bg-white p-1 ${
                            viewMode === 'grouped' && showGroupActions
                              ? ''
                              : 'invisible pointer-events-none'
                          }`}
                        >
                          <Button
                            type="button"
                            variant="ghost"
                            size="sm"
                            disabled={viewMode !== 'grouped' || !showGroupActions}
                            className="h-7 whitespace-nowrap px-2 text-slate-600 hover:text-slate-900"
                            onClick={handleExpandAllGroups}
                          >
                            Expand all
                          </Button>
                          <Button
                            type="button"
                            variant="ghost"
                            size="sm"
                            disabled={viewMode !== 'grouped' || !showGroupActions}
                            className="h-7 whitespace-nowrap px-2 text-slate-600 hover:text-slate-900"
                            onClick={handleCollapseAllGroups}
                          >
                            Collapse all
                          </Button>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              </div>

              {hiddenSelectedCount > 0 ? (
                <div className="mt-3 text-xs text-slate-500">
                  {hiddenSelectedCount} selected {hiddenSelectedCount === 1 ? 'run is' : 'runs are'}{' '}
                  in filtered-out groups.
                </div>
              ) : null}
            </div>

            <div className="border-t border-slate-200 pt-3 text-sm text-slate-600">
              {statusSummary}
            </div>
          </div>

          <div className="border-t border-slate-200 px-5 py-4">
            <div
              className={
                useScrollableGroupsPanel
                  ? 'rounded-xl bg-slate-50/30 p-3 lg:max-h-[70vh] lg:overflow-y-auto'
                  : ''
              }
            >
              <div className="space-y-4">
                {(viewMode === 'grouped'
                  ? filteredSimulationGroups.length
                  : filteredFlatSimulations.length) === 0 ? (
                  <div className="rounded-xl border border-dashed border-slate-300 bg-slate-50/40 px-6 py-10 text-center">
                    <p className="text-sm font-medium text-slate-900">
                      {viewMode === 'grouped'
                        ? 'No Case Hash groups match these filters.'
                        : 'No executions match these filters.'}
                    </p>
                    <p className="mt-2 text-sm text-muted-foreground">
                      Try a different filter or reset current filters.
                    </p>
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      className="mt-4"
                      onClick={resetGroupFilters}
                    >
                      Reset filters
                    </Button>
                  </div>
                ) : viewMode === 'flat' ? (
                  <div className="overflow-hidden rounded-xl border border-slate-200 bg-background">
                    <div className="max-h-[28rem] overflow-auto">
                      <Table>
                        <TableHeader>
                          <TableRow>
                            <TableHead className="w-12">Select</TableHead>
                            <TableHead>Execution ID</TableHead>
                            <TableHead>Case Hash</TableHead>
                            <TableHead>Role / changes</TableHead>
                            <TableHead>Initialization</TableHead>
                            <TableHead>Simulation dates</TableHead>
                            <TableHead>Run dates</TableHead>
                          </TableRow>
                        </TableHeader>
                        <TableBody>
                          {filteredFlatSimulations.map(({ summary, details }) => (
                            <TableRow key={summary.id}>
                              <TableCell className="align-top">
                                <Checkbox
                                  checked={selectedSimulationIds.includes(summary.id)}
                                  disabled={
                                    !selectedSimulationIds.includes(summary.id) &&
                                    selectedSimulationIds.length >= MAX_SELECTION
                                  }
                                  onCheckedChange={() => toggleSimulationSelection(summary.id)}
                                  aria-label={`Select ${summary.executionId} for compare`}
                                />
                              </TableCell>
                              <TableCell className="align-top">
                                <Link
                                  to={`/simulations/${summary.id}`}
                                  state={{ from: currentPath }}
                                  className="inline-flex items-center gap-1 font-mono text-xs text-blue-600 hover:underline"
                                >
                                  {summary.executionId}
                                  {summary.isReference ? (
                                    <span
                                      className="inline-flex items-center"
                                      title="Reference simulation"
                                      aria-label="Reference simulation"
                                    >
                                      <Pin className="h-3.5 w-3.5 text-amber-600" />
                                    </span>
                                  ) : null}
                                </Link>
                              </TableCell>
                              <TableCell className="align-top">
                                <span
                                  className="font-mono text-xs text-slate-700"
                                  title={summary.caseHash ?? MISSING_CASE_HASH_LABEL}
                                >
                                  {summary.caseHash
                                    ? formatCaseHashLabel(summary.caseHash)
                                    : MISSING_CASE_HASH_LABEL}
                                </span>
                              </TableCell>
                              <TableCell className="align-top text-sm text-slate-700">
                                {summary.isReference
                                  ? 'Reference baseline'
                                  : `${summary.changeCount} changes`}
                              </TableCell>
                              <TableCell className="align-top">
                                <TableCellText
                                  value={details?.initializationType ?? '—'}
                                  lines={1}
                                />
                              </TableCell>
                              <TableCell className="align-top">
                                {formatSimulationDateRange(summary)}
                              </TableCell>
                              <TableCell className="align-top">
                                {details?.runStartDate || details?.runEndDate ? (
                                  <span
                                    title={`${details?.runStartDate ?? '—'} → ${details?.runEndDate ?? '—'}`}
                                  >
                                    {formatRunDateRange(details?.runStartDate, details?.runEndDate)}
                                  </span>
                                ) : (
                                  <span className="text-muted-foreground">—</span>
                                )}
                              </TableCell>
                            </TableRow>
                          ))}
                        </TableBody>
                      </Table>
                    </div>
                  </div>
                ) : (
                  <div className="overflow-hidden rounded-xl border border-slate-200 bg-background">
                    <div className="max-h-[42rem] overflow-auto">
                      <Table className="min-w-[980px]">
                        <TableHeader className="sticky top-0 z-10 bg-slate-50">
                          <TableRow className="hover:bg-slate-50">
                            <TableHead className="w-[22rem] bg-slate-50">Case Hash</TableHead>
                            <TableHead className="w-24 bg-slate-50">Runs</TableHead>
                            <TableHead className="bg-slate-50">Simulation window</TableHead>
                            <TableHead className="bg-slate-50">Initialization</TableHead>
                            <TableHead className="bg-slate-50">Config changes</TableHead>
                            <TableHead className="bg-slate-50">Run dates</TableHead>
                          </TableRow>
                        </TableHeader>
                        <TableBody>
                          {filteredSimulationGroups.map((group) => {
                            const isOpen = expandedGroupKeys.includes(group.key);
                            const groupSimulationWindow = formatGroupSimulationWindow(
                              group.simulations.map(({ summary }) => summary),
                            );
                            const groupRunWindow = getGroupRunDateWindow(group.simulations);
                            const groupInitializationSummary = summarizeDistinctValues(
                              group.simulations.map(({ details }) => details?.initializationType),
                            );
                            const maxChangeCount = Math.max(
                              ...group.simulations.map(({ summary }) => summary.changeCount),
                            );
                            const showInitializationColumn =
                              countDistinctValues(
                                group.simulations.map(
                                  ({ details }) => details?.initializationType ?? '—',
                                ),
                              ) > 1;
                            const showSimulationDatesColumn =
                              countDistinctValues(
                                group.simulations.map(({ summary }) =>
                                  formatSimulationDateRange(summary),
                                ),
                              ) > 1;
                            const showRunDatesColumn =
                              countDistinctValues(
                                group.simulations.map(({ details }) =>
                                  formatRunDateRange(details?.runStartDate, details?.runEndDate),
                                ),
                              ) > 1;

                            return (
                              <Fragment key={group.key}>
                                <TableRow
                                  className="cursor-pointer bg-white hover:bg-slate-50/80"
                                  onClick={() => toggleGroupExpansion(group.key, !isOpen)}
                                >
                                  <TableCell className="align-top">
                                    <div className="flex items-start gap-3">
                                      <ChevronDown
                                        className={`mt-0.5 h-4 w-4 shrink-0 text-slate-500 transition-transform ${
                                          isOpen ? 'rotate-180' : ''
                                        }`}
                                      />
                                      <div className="min-w-0 space-y-1">
                                        <div className="flex flex-wrap items-center gap-2">
                                          <span
                                            className="truncate font-mono text-xs font-semibold text-slate-950 sm:text-sm"
                                            title={group.caseHash ?? MISSING_CASE_HASH_LABEL}
                                          >
                                            {group.isFallback
                                              ? MISSING_CASE_HASH_LABEL
                                              : formatCaseHashLabel(group.caseHash, 22)}
                                          </span>
                                          {group.isFallback ? (
                                            <Badge variant="secondary">Fallback</Badge>
                                          ) : null}
                                        </div>
                                        {group.isFallback ? (
                                          <p className="text-xs text-slate-500">
                                            Older ingests without Case Hash stay in fallback group.
                                          </p>
                                        ) : null}
                                      </div>
                                    </div>
                                  </TableCell>
                                  <TableCell className="align-top">
                                    <Badge variant="outline">
                                      {pluralize(group.simulations.length, 'run')}
                                    </Badge>
                                  </TableCell>
                                  <TableCell className="align-top text-sm text-slate-700">
                                    {groupSimulationWindow}
                                  </TableCell>
                                  <TableCell className="align-top text-sm text-slate-700">
                                    <TableCellText value={groupInitializationSummary} lines={1} />
                                  </TableCell>
                                  <TableCell className="align-top text-sm font-medium text-slate-700">
                                    Up to {maxChangeCount} changes
                                  </TableCell>
                                  <TableCell className="align-top text-sm text-slate-700">
                                    {groupRunWindow}
                                  </TableCell>
                                </TableRow>
                                {isOpen ? (
                                  <TableRow className="bg-slate-50/50 hover:bg-slate-50/50">
                                    <TableCell colSpan={6} className="p-0">
                                      <div className="border-t border-slate-200 px-4 py-3">
                                        <div className="mb-3 flex items-center justify-between gap-3">
                                          <p className="text-[11px] font-medium uppercase tracking-[0.18em] text-slate-500">
                                            Executions in group
                                          </p>
                                          <p className="text-xs text-slate-500">
                                            {group.simulations.length} visible
                                          </p>
                                        </div>
                                        <div className="overflow-hidden rounded-lg border border-slate-200 bg-white">
                                          <div className="max-h-[20rem] overflow-auto">
                                            <Table>
                                              <TableHeader className="sticky top-0 z-10 bg-white">
                                                <TableRow className="hover:bg-white">
                                                  <TableHead className="w-12 bg-white">
                                                    Select
                                                  </TableHead>
                                                  <TableHead className="bg-white">
                                                    Execution ID
                                                  </TableHead>
                                                  <TableHead className="bg-white">
                                                    Role / changes
                                                  </TableHead>
                                                  {showInitializationColumn ? (
                                                    <TableHead className="bg-white">
                                                      Initialization
                                                    </TableHead>
                                                  ) : null}
                                                  {showSimulationDatesColumn ? (
                                                    <TableHead className="bg-white">
                                                      Simulation dates
                                                    </TableHead>
                                                  ) : null}
                                                  {showRunDatesColumn ? (
                                                    <TableHead className="bg-white">
                                                      Run dates
                                                    </TableHead>
                                                  ) : null}
                                                </TableRow>
                                              </TableHeader>
                                              <TableBody>
                                                {group.simulations.map(({ summary, details }) => (
                                                  <TableRow key={summary.id}>
                                                    <TableCell className="align-top">
                                                      <Checkbox
                                                        checked={selectedSimulationIds.includes(
                                                          summary.id,
                                                        )}
                                                        disabled={
                                                          !selectedSimulationIds.includes(
                                                            summary.id,
                                                          ) &&
                                                          selectedSimulationIds.length >=
                                                            MAX_SELECTION
                                                        }
                                                        onCheckedChange={() =>
                                                          toggleSimulationSelection(summary.id)
                                                        }
                                                        aria-label={`Select ${summary.executionId} for compare`}
                                                      />
                                                    </TableCell>
                                                    <TableCell className="align-top">
                                                      <Link
                                                        to={`/simulations/${summary.id}`}
                                                        state={{ from: currentPath }}
                                                        className="inline-flex items-center gap-1 font-mono text-xs text-blue-600 hover:underline"
                                                      >
                                                        {summary.executionId}
                                                        {summary.isReference ? (
                                                          <span
                                                            className="inline-flex items-center"
                                                            title="Reference simulation"
                                                            aria-label="Reference simulation"
                                                          >
                                                            <Pin className="h-3.5 w-3.5 text-amber-600" />
                                                          </span>
                                                        ) : null}
                                                      </Link>
                                                    </TableCell>
                                                    <TableCell className="align-top text-sm text-slate-700">
                                                      {summary.isReference
                                                        ? 'Reference baseline'
                                                        : `${summary.changeCount} changes`}
                                                    </TableCell>
                                                    {showInitializationColumn ? (
                                                      <TableCell className="align-top">
                                                        <TableCellText
                                                          value={details?.initializationType ?? '—'}
                                                          lines={1}
                                                        />
                                                      </TableCell>
                                                    ) : null}
                                                    {showSimulationDatesColumn ? (
                                                      <TableCell className="align-top">
                                                        {formatSimulationDateRange(summary)}
                                                      </TableCell>
                                                    ) : null}
                                                    {showRunDatesColumn ? (
                                                      <TableCell className="align-top">
                                                        {details?.runStartDate ||
                                                        details?.runEndDate ? (
                                                          <span
                                                            title={`${details?.runStartDate ?? '—'} → ${details?.runEndDate ?? '—'}`}
                                                          >
                                                            {formatRunDateRange(
                                                              details?.runStartDate,
                                                              details?.runEndDate,
                                                            )}
                                                          </span>
                                                        ) : (
                                                          <span className="text-muted-foreground">
                                                            —
                                                          </span>
                                                        )}
                                                      </TableCell>
                                                    ) : null}
                                                  </TableRow>
                                                ))}
                                              </TableBody>
                                            </Table>
                                          </div>
                                        </div>
                                      </div>
                                    </TableCell>
                                  </TableRow>
                                ) : null}
                              </Fragment>
                            );
                          })}
                        </TableBody>
                      </Table>
                    </div>
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      </section>
    </div>
  );
};
