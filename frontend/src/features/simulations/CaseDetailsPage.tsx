import { ArrowLeft, ChevronDown, Pin, Share2 } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom';

import { SimulationStatusBadge } from '@/components/shared/SimulationStatusBadge';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Checkbox } from '@/components/ui/checkbox';
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
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
  getReferenceSimulation,
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
    <div className="text-[11px] font-medium uppercase tracking-[0.18em] text-slate-500">{label}</div>
    <div className={`truncate font-semibold text-slate-950 ${mono ? 'font-mono text-xs' : 'text-sm'}`}>
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

interface CaseDetailsPageProps {
  simulations: SimulationOut[];
  selectedSimulationIds: string[];
  setSelectedSimulationIds: (ids: string[]) => void;
}

type SimulationViewMode = 'grouped' | 'flat';

const MAX_SELECTION = 5;
const GROUP_ACTIONS_THRESHOLD = 4;
const ALL_CASE_HASHES_VALUE = '__all_case_hashes__';
const SCROLLABLE_GROUPS_THRESHOLD = 5;
const SCROLLABLE_FLAT_ROWS_THRESHOLD = 10;
const GROUP_FILTER_OPTIONS: Array<{ value: SimulationSummaryGroupFilter; label: string }> = [
  { value: 'all', label: 'All groups' },
  { value: 'multiRun', label: 'Multi-run groups' },
  { value: 'missing', label: 'Missing Case Hash' },
];

export const CaseDetailsPage = ({
  simulations: allSimulations,
  selectedSimulationIds,
  setSelectedSimulationIds,
}: CaseDetailsPageProps) => {
  const { id } = useParams<{ id: string }>();
  const location = useLocation();
  const navigate = useNavigate();
  const [viewMode, setViewMode] = useState<SimulationViewMode>('grouped');
  const [selectedCaseHashKey, setSelectedCaseHashKey] = useState(ALL_CASE_HASHES_VALUE);
  const [groupFilterMode, setGroupFilterMode] = useState<SimulationSummaryGroupFilter>('all');
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
  const caseHashOptions = useMemo(
    () =>
      rawSimulationGroups.map((group) => ({
        key: group.key,
        label: group.isFallback ? MISSING_CASE_HASH_LABEL : formatCaseHashLabel(group.caseHash),
        title: group.caseHash ?? MISSING_CASE_HASH_LABEL,
      })),
    [rawSimulationGroups],
  );
  const caseHashGroupCount = rawSimulationGroups.filter((group) => !group.isFallback).length;
  const missingCaseHashCount =
    rawSimulationGroups.find((group) => group.isFallback)?.simulations.length ?? 0;
  const filteredGroupKeys = useMemo(
    () =>
      rawSimulationGroups
        .filter(
          (group) =>
            matchesSimulationGroupFilter(group, groupFilterMode) &&
            (selectedCaseHashKey === ALL_CASE_HASHES_VALUE || group.key === selectedCaseHashKey),
        )
        .map((group) => group.key),
    [groupFilterMode, rawSimulationGroups, selectedCaseHashKey],
  );
  const filteredGroupKeySet = useMemo(() => new Set(filteredGroupKeys), [filteredGroupKeys]);
  const filteredSimulationGroups = useMemo(
    () => simulationGroups.filter((group) => filteredGroupKeySet.has(group.key)),
    [filteredGroupKeySet, simulationGroups],
  );
  const filteredFlatSimulations = useMemo(
    () => filteredSimulationGroups.flatMap((group) => group.simulations),
    [filteredSimulationGroups],
  );
  const visibleSimulationIds = useMemo(
    () =>
      new Set(
        filteredFlatSimulations.map(({ summary }) => summary.id),
      ),
    [filteredFlatSimulations],
  );
  const selectedCurrentCaseSimulationIds = caseSimulations
    .map((simulation) => simulation.id)
    .filter((simulationId) => selectedSimulationIds.includes(simulationId));
  const hiddenSelectedCount = selectedCurrentCaseSimulationIds.filter(
    (simulationId) => !visibleSimulationIds.has(simulationId),
  ).length;
  const hasActiveGroupFilters =
    groupFilterMode !== 'all' || selectedCaseHashKey !== ALL_CASE_HASHES_VALUE;
  const showGroupActions = rawSimulationGroups.length > GROUP_ACTIONS_THRESHOLD;
  const useScrollableGroupsPanel =
    viewMode === 'grouped'
      ? filteredSimulationGroups.length > SCROLLABLE_GROUPS_THRESHOLD
      : filteredFlatSimulations.length > SCROLLABLE_FLAT_ROWS_THRESHOLD;

  useEffect(() => {
    setExpandedGroupKeys(getDefaultExpandedGroupKeys(rawSimulationGroups));
  }, [rawSimulationGroups]);

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

  const referenceSimulation = getReferenceSimulation(caseRecord);
  const machineSummary = summarizeValues(caseRecord.machineNames);
  const hpcUsernameSummary = summarizeValues(caseRecord.hpcUsernames);
  const isCompareButtonDisabled = selectedSimulationIds.length < 2;
  const filteredExecutionCount = filteredFlatSimulations.length;
  const activeSimulationCount =
    viewMode === 'grouped' ? filteredSimulationGroups.length : filteredExecutionCount;
  const totalSimulationCount =
    viewMode === 'grouped' ? simulationGroups.length : caseRecord.simulations.length;

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
      if (open) {
        return currentKeys.includes(groupKey) ? currentKeys : [...currentKeys, groupKey];
      }

      return currentKeys.filter((key) => key !== groupKey);
    });
  };

  const handleExpandAllGroups = () => {
    setExpandedGroupKeys((currentKeys) => [
      ...new Set([...currentKeys, ...filteredSimulationGroups.map((group) => group.key)]),
    ]);
  };

  const handleCollapseAllGroups = () => {
    const filteredGroupKeys = new Set(filteredSimulationGroups.map((group) => group.key));
    setExpandedGroupKeys((currentKeys) =>
      currentKeys.filter((key) => !filteredGroupKeys.has(key)),
    );
  };

  const resetGroupFilters = () => {
    setGroupFilterMode('all');
    setSelectedCaseHashKey(ALL_CASE_HASHES_VALUE);
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

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1.35fr)_minmax(320px,0.95fr)]">
        <Card className="border-slate-200 bg-slate-50/40 shadow-sm">
          <CardContent className="space-y-5 p-5">
            <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
              <div className="space-y-1">
                <p className="text-sm font-medium text-slate-500">Case summary</p>
                <h2 className="text-lg font-semibold text-slate-950">
                  {caseRecord.simulations.length} runs across {caseHashGroupCount} Case Hash groups
                </h2>
              </div>
              <div className="flex flex-wrap gap-2">
                {caseRecord.caseGroup ? <Badge variant="outline">{caseRecord.caseGroup}</Badge> : null}
                {missingCaseHashCount > 0 ? (
                  <Badge variant="outline" className="border-amber-200 bg-amber-50 text-amber-800">
                    {missingCaseHashCount} missing Case Hash
                  </Badge>
                ) : null}
              </div>
            </div>

            <div className="grid gap-4 border-t border-slate-200 pt-4 sm:grid-cols-2 xl:grid-cols-5">
              <DetailField label="Runs" value={caseRecord.simulations.length} />
              <DetailField label="Case Hash groups" value={caseHashGroupCount} />
              <DetailField
                label="Machines"
                value={machineSummary}
                title={caseRecord.machineNames.length > 1 ? caseRecord.machineNames.join(', ') : undefined}
              />
              <DetailField
                label="HPC users"
                value={hpcUsernameSummary}
                title={caseRecord.hpcUsernames.length > 1 ? caseRecord.hpcUsernames.join(', ') : undefined}
              />
              <DetailField label="Last updated" value={formatCaseDate(caseRecord.updatedAt)} />
            </div>
          </CardContent>
        </Card>

        <Card className="border-slate-200 bg-white shadow-sm">
          <CardContent className="space-y-4 p-5">
            <div className="flex items-start justify-between gap-3">
              <p className="text-sm font-medium text-slate-500">Reference simulation</p>
              {referenceSimulation ? (
                <SimulationStatusBadge status={referenceSimulation.status} />
              ) : null}
            </div>

            {referenceSimulation ? (
              <div className="space-y-4">
                <Link
                  to={`/simulations/${referenceSimulation.id}`}
                  state={{ from: currentPath }}
                  className="inline-flex items-center gap-1 font-mono text-xs text-blue-600 hover:underline"
                >
                  {referenceSimulation.executionId}
                  <span
                    className="inline-flex items-center"
                    title="Reference simulation"
                    aria-label="Reference simulation"
                  >
                    <Pin className="h-3.5 w-3.5 text-amber-600" />
                  </span>
                </Link>
                <div className="grid gap-4 border-t border-slate-200 pt-4 sm:grid-cols-2">
                  <DetailField label="Simulation window" value={formatSimulationDateRange(referenceSimulation)} />
                  <DetailField label="Change role" value="Reference baseline" />
                </div>
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">
                No reference simulation is set for this case.
              </p>
            )}
          </CardContent>
        </Card>
      </div>

      <section className="space-y-4">
        <div className="rounded-2xl border border-slate-200 bg-white shadow-sm">
          <div className="flex flex-col gap-4 border-b border-slate-200 px-5 py-4 xl:flex-row xl:items-start xl:justify-between">
            <div className="space-y-2">
              <h2 className="text-xl font-semibold">Simulations</h2>
              <p className="max-w-3xl text-sm text-muted-foreground">
                Group by Case Hash to compare runs within the same lineage; runs without Case Hash stay
                visible as fallback entries.
              </p>
            </div>

            <div className="rounded-xl border border-slate-200 bg-slate-50/70 px-4 py-3">
              <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
                <Button
                  type="button"
                  onClick={() => navigate('/compare')}
                  disabled={isCompareButtonDisabled}
                >
                  Compare Selected
                </Button>
                <div className="space-y-1 text-sm text-slate-600">
                  <div>
                    Selected{' '}
                    <span className="font-semibold text-slate-950">{selectedSimulationIds.length}</span> /{' '}
                    {MAX_SELECTION}
                  </div>
                  {hiddenSelectedCount > 0 ? (
                    <div className="text-xs text-slate-500">
                      {hiddenSelectedCount} selected {hiddenSelectedCount === 1 ? 'run is' : 'runs are'} in
                      filtered-out groups.
                    </div>
                  ) : null}
                </div>
              </div>
            </div>
          </div>

          <div className="space-y-4 px-5 py-4">
            <div className="flex flex-col gap-4 xl:flex-row xl:items-end xl:justify-between">
              <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:gap-4">
                <div className="space-y-2">
                  <div className="text-sm font-medium text-slate-900">View</div>
                  <div className="flex flex-wrap gap-2">
                    <Button
                      type="button"
                      size="sm"
                      variant={viewMode === 'grouped' ? 'default' : 'outline'}
                      onClick={() => setViewMode('grouped')}
                    >
                      Grouped by Case Hash
                    </Button>
                    <Button
                      type="button"
                      size="sm"
                      variant={viewMode === 'flat' ? 'default' : 'outline'}
                      onClick={() => setViewMode('flat')}
                    >
                      All executions
                    </Button>
                  </div>
                </div>

                <div className="space-y-2">
                  <div className="text-sm font-medium text-slate-900">Scope</div>
                  <Select value={selectedCaseHashKey} onValueChange={setSelectedCaseHashKey}>
                    <SelectTrigger className="w-full bg-white shadow-none lg:w-72">
                      <SelectValue placeholder="All Case Hash groups" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value={ALL_CASE_HASHES_VALUE}>All Case Hash groups</SelectItem>
                      {caseHashOptions.map((option) => (
                        <SelectItem key={option.key} value={option.key} title={option.title}>
                          {option.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>

              <div className="space-y-3 xl:text-right">
                <div className="space-y-2">
                  <div className="text-sm font-medium text-slate-900">Filters</div>
                  <div className="flex flex-wrap gap-2 xl:justify-end">
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
                  </div>
                </div>

                <div className="flex flex-wrap items-center gap-2 xl:justify-end">
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
                  {hasActiveGroupFilters ? (
                    <Button type="button" variant="ghost" size="sm" onClick={resetGroupFilters}>
                      Reset filters
                    </Button>
                  ) : null}
                  {viewMode === 'grouped' && showGroupActions ? (
                    <>
                      <Button type="button" variant="ghost" size="sm" onClick={handleExpandAllGroups}>
                        Expand all
                      </Button>
                      <Button type="button" variant="ghost" size="sm" onClick={handleCollapseAllGroups}>
                        Collapse all
                      </Button>
                    </>
                  ) : null}
                </div>
              </div>
            </div>

            <div className="flex flex-col gap-2 border-t border-slate-200 pt-3 text-sm text-slate-600 sm:flex-row sm:items-center sm:justify-between">
              <div>
                Showing <span className="font-semibold text-slate-950">{activeSimulationCount}</span> of{' '}
                {totalSimulationCount} {viewMode === 'grouped' ? 'groups' : 'executions'}
              </div>
              <div>
                {viewMode === 'grouped'
                  ? `${filteredExecutionCount} executions available inside current group set`
                  : `${filteredSimulationGroups.length} Case Hash groups represented`}
              </div>
            </div>
          </div>
        </div>

        <div
          className={
            useScrollableGroupsPanel
              ? 'rounded-2xl border border-slate-200 bg-slate-50/30 p-3 lg:max-h-[70vh] lg:overflow-y-auto'
              : ''
          }
        >
          <div className="space-y-4">
            {(viewMode === 'grouped' ? filteredSimulationGroups.length : filteredFlatSimulations.length) === 0 ? (
                <div className="rounded-xl border border-dashed border-slate-300 bg-slate-50/40 px-6 py-10 text-center">
                <p className="text-sm font-medium text-slate-900">
                  {viewMode === 'grouped'
                    ? 'No Case Hash groups match these filters.'
                    : 'No executions match these filters.'}
                </p>
                <p className="mt-2 text-sm text-muted-foreground">
                  Try a different Case Hash selection or reset the quick filters.
                </p>
                <Button type="button" variant="outline" size="sm" className="mt-4" onClick={resetGroupFilters}>
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
                            {summary.isReference ? 'Reference baseline' : `${summary.changeCount} changes`}
                          </TableCell>
                          <TableCell className="align-top">
                            <TableCellText value={details?.initializationType ?? '—'} lines={1} />
                          </TableCell>
                          <TableCell className="align-top">{formatSimulationDateRange(summary)}</TableCell>
                          <TableCell className="align-top">
                            {details?.runStartDate || details?.runEndDate ? (
                              <span title={`${details?.runStartDate ?? '—'} → ${details?.runEndDate ?? '—'}`}>
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
              filteredSimulationGroups.map((group) => {
                const isOpen = expandedGroupKeys.includes(group.key);
                const groupSimulationWindow = formatGroupSimulationWindow(
                  group.simulations.map(({ summary }) => summary),
                );
                const groupInitializationSummary = summarizeDistinctValues(
                  group.simulations.map(({ details }) => details?.initializationType),
                );
                const maxChangeCount = Math.max(
                  ...group.simulations.map(({ summary }) => summary.changeCount),
                );
                return (
                  <Collapsible
                    key={group.key}
                    open={isOpen}
                    onOpenChange={(open) => toggleGroupExpansion(group.key, open)}
                  >
                    <div className="overflow-hidden rounded-xl border border-slate-200 bg-background">
                      <CollapsibleTrigger asChild>
                        <button
                          type="button"
                          className="flex w-full flex-col gap-4 bg-slate-50/70 px-4 py-4 text-left transition-colors hover:bg-slate-100/80"
                        >
                          <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                            <div className="flex min-w-0 items-start gap-3">
                              <ChevronDown
                                className={`mt-0.5 h-4 w-4 shrink-0 text-slate-500 transition-transform ${
                                  isOpen ? 'rotate-180' : ''
                                }`}
                              />
                              <div className="min-w-0 space-y-1">
                                <p className="text-[11px] font-medium uppercase tracking-[0.18em] text-slate-500">
                                  {group.isFallback ? 'Missing Case Hash' : 'Case Hash group'}
                                </p>
                                <p
                                  className="truncate font-mono text-sm text-slate-950"
                                  title={group.caseHash ?? MISSING_CASE_HASH_LABEL}
                                >
                                  {group.isFallback
                                    ? MISSING_CASE_HASH_LABEL
                                    : formatCaseHashLabel(group.caseHash)}
                                </p>
                                {group.isFallback ? (
                                  <p className="max-w-2xl text-xs text-muted-foreground">
                                    Older ingests without Case Hash stay visible here without subgrouping.
                                  </p>
                                ) : null}
                              </div>
                            </div>

                            <div className="flex shrink-0 flex-wrap items-center gap-2">
                              <Badge variant="outline">
                                {group.simulations.length} {group.simulations.length === 1 ? 'run' : 'runs'}
                              </Badge>
                            </div>
                          </div>

                          <div className="grid gap-3 border-t border-slate-200 pt-3 sm:grid-cols-[minmax(0,1.4fr)_minmax(0,0.9fr)_minmax(0,1fr)]">
                            <DetailField label="Simulation window" value={groupSimulationWindow} />
                            <DetailField label="Initialization" value={groupInitializationSummary} />
                            <DetailField label="Change spread" value={`Up to ${maxChangeCount} changes`} />
                          </div>
                        </button>
                      </CollapsibleTrigger>

                      <CollapsibleContent>
                        <div className="max-h-[24rem] overflow-auto border-t border-slate-200">
                          <Table>
                            <TableHeader>
                              <TableRow>
                                <TableHead className="w-12">Select</TableHead>
                                <TableHead>Execution ID</TableHead>
                                <TableHead>Role / changes</TableHead>
                                <TableHead>Initialization</TableHead>
                                <TableHead>Simulation dates</TableHead>
                                <TableHead>Run dates</TableHead>
                              </TableRow>
                            </TableHeader>
                            <TableBody>
                              {group.simulations.map(({ summary, details }) => (
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
                                  <TableCell className="align-top text-sm text-slate-700">
                                    {summary.isReference ? 'Reference baseline' : `${summary.changeCount} changes`}
                                  </TableCell>
                                  <TableCell className="align-top">
                                    <TableCellText value={details?.initializationType ?? '—'} lines={1} />
                                  </TableCell>
                                  <TableCell className="align-top">{formatSimulationDateRange(summary)}</TableCell>
                                  <TableCell className="align-top">
                                    {details?.runStartDate || details?.runEndDate ? (
                                      <span title={`${details?.runStartDate ?? '—'} → ${details?.runEndDate ?? '—'}`}>
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
                      </CollapsibleContent>
                    </div>
                  </Collapsible>
                );
              })
            )}
          </div>
        </div>
      </section>
    </div>
  );
};
