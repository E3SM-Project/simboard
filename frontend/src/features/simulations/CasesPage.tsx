import type { ColumnDef, SortingState } from '@tanstack/react-table';
import {
  flexRender,
  getCoreRowModel,
  getPaginationRowModel,
  getSortedRowModel,
  useReactTable,
} from '@tanstack/react-table';
import { ChevronDown, ChevronRight, Pin, Search, SlidersHorizontal, X } from 'lucide-react';
import { Fragment, useMemo, useState } from 'react';
import { Link, useLocation } from 'react-router-dom';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible';
import { Input } from '@/components/ui/input';
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
import { formatCaseDate } from '@/features/simulations/caseUtils';
import { useCases } from '@/features/simulations/hooks/useCases';
import { cn } from '@/lib/utils';
import type { CaseOut, SimulationOut, SimulationSummaryOut } from '@/types';

type ReferenceFilter = 'all' | 'with-reference' | 'without-reference';
type ActiveFilterKey =
  | 'caseName'
  | 'hpcUsername'
  | 'machineId'
  | 'campaign'
  | 'simulationType'
  | 'initializationType'
  | 'compiler'
  | 'gitTag'
  | 'createdBy'
  | 'caseGroup'
  | 'reference';

interface CasesPageProps {
  simulations: SimulationOut[];
}

interface CaseSimulationFilters {
  hpcUsername: string;
  machineId: string;
  campaign: string;
  simulationType: string;
  initializationType: string;
  compiler: string;
  gitTag: string;
  createdBy: string;
}

interface SelectOption {
  value: string;
  label: string;
}

interface ActiveFilterPill {
  key: ActiveFilterKey;
  label: string;
  value: string;
}

type CaseSimulationListItem = SimulationOut | SimulationSummaryOut;

const createEmptySimulationFilters = (): CaseSimulationFilters => ({
  hpcUsername: '',
  machineId: '',
  campaign: '',
  simulationType: '',
  initializationType: '',
  compiler: '',
  gitTag: '',
  createdBy: '',
});

const sortStringValues = (values: string[]) =>
  values.sort((left, right) => left.localeCompare(right, undefined, { sensitivity: 'base' }));

const sortCaseSimulations = (caseSimulations: CaseSimulationListItem[]) =>
  [...caseSimulations].sort((left, right) => {
    if (left.isReference !== right.isReference) {
      return left.isReference ? -1 : 1;
    }

    return (
      new Date(right.simulationStartDate).getTime() - new Date(left.simulationStartDate).getTime()
    );
  });

const getSimulationChangeTitle = (simulation: CaseSimulationListItem) => {
  if ('runConfigDeltas' in simulation && simulation.runConfigDeltas) {
    const changedFields = Object.keys(simulation.runConfigDeltas);

    if (changedFields.length > 0) {
      return `Changed fields: ${changedFields.join(', ')}`;
    }
  }

  return `${simulation.changeCount} changes from reference`;
};

export const CasesPage = ({ simulations }: CasesPageProps) => {
  const location = useLocation();
  const { data: cases, loading, error } = useCases();
  const currentPath = `${location.pathname}${location.search}`;

  const [caseNameFilter, setCaseNameFilter] = useState('');
  const [caseGroupFilter, setCaseGroupFilter] = useState('');
  const [simulationFilters, setSimulationFilters] = useState<CaseSimulationFilters>(
    createEmptySimulationFilters,
  );
  const [referenceFilter, setReferenceFilter] = useState<ReferenceFilter>('all');
  const [showAdvancedFilters, setShowAdvancedFilters] = useState(false);
  const [expandedCaseId, setExpandedCaseId] = useState<string | null>(null);
  const [sorting, setSorting] = useState<SortingState>([
    { id: 'updatedAt', desc: true },
    { id: 'name', desc: false },
  ]);

  const caseGroups = useMemo(
    () =>
      [
        ...new Set(
          cases
            .map((caseRecord) => caseRecord.caseGroup)
            .filter((group): group is string => Boolean(group)),
        ),
      ].sort((left, right) => left.localeCompare(right, undefined, { sensitivity: 'base' })),
    [cases],
  );

  const simulationsByCaseId = useMemo(() => {
    const caseMap = new Map<string, SimulationOut[]>();
    for (const simulation of simulations) {
      const caseSimulations = caseMap.get(simulation.caseId) ?? [];
      caseSimulations.push(simulation);
      caseMap.set(simulation.caseId, caseSimulations);
    }

    return caseMap;
  }, [simulations]);

  const caseMachineSummaries = useMemo(() => {
    const summaries = new Map<string, string>();

    for (const [caseId, caseSimulations] of simulationsByCaseId.entries()) {
      const machineNames = [
        ...new Set(
          caseSimulations
            .map((simulation) => simulation.machine?.name)
            .filter((machineName): machineName is string => Boolean(machineName)),
        ),
      ].sort((left, right) => left.localeCompare(right, undefined, { sensitivity: 'base' }));

      if (machineNames.length === 0) {
        summaries.set(caseId, '—');
      } else if (machineNames.length === 1) {
        summaries.set(caseId, machineNames[0]);
      } else {
        summaries.set(caseId, `${machineNames[0]} +${machineNames.length - 1}`);
      }
    }

    return summaries;
  }, [simulationsByCaseId]);

  const caseHpcUserSummaries = useMemo(() => {
    const summaries = new Map<string, string>();

    for (const [caseId, caseSimulations] of simulationsByCaseId.entries()) {
      const usernames = [
        ...new Set(
          caseSimulations
            .map((simulation) => simulation.hpcUsername)
            .filter((username): username is string => Boolean(username)),
        ),
      ].sort((left, right) => left.localeCompare(right, undefined, { sensitivity: 'base' }));

      if (simulationFilters.hpcUsername) {
        summaries.set(caseId, simulationFilters.hpcUsername);
      } else if (usernames.length === 0) {
        summaries.set(caseId, '—');
      } else if (usernames.length === 1) {
        summaries.set(caseId, usernames[0]);
      } else {
        summaries.set(caseId, `${usernames.length} users`);
      }
    }

    return summaries;
  }, [simulationFilters.hpcUsername, simulationsByCaseId]);
  const hpcUsernames = useMemo(
    () =>
      [
        ...new Set(
          simulations
            .map((simulation) => simulation.hpcUsername)
            .filter((username): username is string => Boolean(username)),
        ),
      ].sort((left, right) => left.localeCompare(right, undefined, { sensitivity: 'base' })),
    [simulations],
  );

  const machineOptions = useMemo(() => {
    const machineMap = new Map<string, string>();

    for (const simulation of simulations) {
      if (!simulation.machine?.id) continue;
      machineMap.set(simulation.machine.id, simulation.machine.name);
    }

    return Array.from(machineMap, ([value, label]) => ({ value, label })).sort((left, right) =>
      left.label.localeCompare(right.label, undefined, { sensitivity: 'base' }),
    );
  }, [simulations]);

  const creatorOptions = useMemo(() => {
    const creatorMap = new Map<string, string>();

    for (const simulation of simulations) {
      if (!simulation.createdBy) continue;
      creatorMap.set(simulation.createdBy, simulation.createdByUser?.email ?? simulation.createdBy);
    }

    return Array.from(creatorMap, ([value, label]) => ({ value, label })).sort((left, right) =>
      left.label.localeCompare(right.label, undefined, { sensitivity: 'base' }),
    );
  }, [simulations]);

  const { campaigns, simulationTypes, initializationTypes, compilers, gitTags } = useMemo(() => {
    const campaigns = new Set<string>();
    const simulationTypes = new Set<string>();
    const initializationTypes = new Set<string>();
    const compilers = new Set<string>();
    const gitTags = new Set<string>();

    for (const simulation of simulations) {
      if (simulation.campaign) campaigns.add(simulation.campaign);
      if (simulation.simulationType) simulationTypes.add(simulation.simulationType);
      if (simulation.initializationType) {
        initializationTypes.add(simulation.initializationType);
      }
      if (simulation.compiler) compilers.add(simulation.compiler);
      if (simulation.gitTag) gitTags.add(simulation.gitTag);
    }

    return {
      campaigns: sortStringValues([...campaigns]),
      simulationTypes: sortStringValues([...simulationTypes]),
      initializationTypes: sortStringValues([...initializationTypes]),
      compilers: sortStringValues([...compilers]),
      gitTags: sortStringValues([...gitTags]),
    };
  }, [simulations]);

  const hasActiveSimulationFilters = useMemo(
    () => Object.values(simulationFilters).some(Boolean),
    [simulationFilters],
  );
  const hasActiveFilters =
    caseNameFilter.trim().length > 0 ||
    caseGroupFilter.length > 0 ||
    referenceFilter !== 'all' ||
    hasActiveSimulationFilters;
  const advancedFilterCount = useMemo(
    () =>
      [
        simulationFilters.machineId,
        simulationFilters.campaign,
        simulationFilters.simulationType,
        simulationFilters.initializationType,
        simulationFilters.compiler,
        simulationFilters.gitTag,
        simulationFilters.createdBy,
        caseGroupFilter,
        referenceFilter !== 'all' ? referenceFilter : '',
      ].filter(Boolean).length,
    [referenceFilter, caseGroupFilter, simulationFilters],
  );
  const matchingSimulationsByCaseId = useMemo(() => {
    const matchingMap = new Map<string, SimulationOut[]>();

    const matchesSimulationFilters = (simulation: SimulationOut) => {
      if (
        simulationFilters.hpcUsername &&
        simulation.hpcUsername !== simulationFilters.hpcUsername
      ) {
        return false;
      }
      if (simulationFilters.machineId && simulation.machine?.id !== simulationFilters.machineId) {
        return false;
      }
      if (simulationFilters.campaign && simulation.campaign !== simulationFilters.campaign) {
        return false;
      }
      if (
        simulationFilters.simulationType &&
        simulation.simulationType !== simulationFilters.simulationType
      ) {
        return false;
      }
      if (
        simulationFilters.initializationType &&
        simulation.initializationType !== simulationFilters.initializationType
      ) {
        return false;
      }
      if (simulationFilters.compiler && simulation.compiler !== simulationFilters.compiler) {
        return false;
      }
      if (simulationFilters.gitTag && simulation.gitTag !== simulationFilters.gitTag) {
        return false;
      }
      if (simulationFilters.createdBy && simulation.createdBy !== simulationFilters.createdBy) {
        return false;
      }

      return true;
    };

    for (const simulation of simulations) {
      if (!matchesSimulationFilters(simulation)) continue;

      const caseSimulations = matchingMap.get(simulation.caseId) ?? [];
      caseSimulations.push(simulation);
      matchingMap.set(simulation.caseId, caseSimulations);
    }

    return matchingMap;
  }, [simulationFilters, simulations]);

  const activeFilterPills = useMemo(() => {
    const filters: ActiveFilterPill[] = [];

    if (caseNameFilter.trim()) {
      filters.push({ key: 'caseName', label: 'Case', value: caseNameFilter.trim() });
    }

    if (simulationFilters.hpcUsername) {
      filters.push({ key: 'hpcUsername', label: 'HPC', value: simulationFilters.hpcUsername });
    }

    if (simulationFilters.machineId) {
      filters.push({
        key: 'machineId',
        label: 'Machine',
        value:
          machineOptions.find((option) => option.value === simulationFilters.machineId)?.label ??
          simulationFilters.machineId,
      });
    }

    if (simulationFilters.campaign) {
      filters.push({ key: 'campaign', label: 'Campaign', value: simulationFilters.campaign });
    }
    if (simulationFilters.simulationType) {
      filters.push({
        key: 'simulationType',
        label: 'Type',
        value: simulationFilters.simulationType,
      });
    }

    if (simulationFilters.initializationType) {
      filters.push({
        key: 'initializationType',
        label: 'Init',
        value: simulationFilters.initializationType,
      });
    }

    if (simulationFilters.compiler) {
      filters.push({ key: 'compiler', label: 'Compiler', value: simulationFilters.compiler });
    }

    if (simulationFilters.gitTag) {
      filters.push({ key: 'gitTag', label: 'Tag', value: simulationFilters.gitTag });
    }

    if (simulationFilters.createdBy) {
      filters.push({
        key: 'createdBy',
        label: 'Creator',
        value:
          creatorOptions.find((option) => option.value === simulationFilters.createdBy)?.label ??
          simulationFilters.createdBy,
      });
    }

    if (caseGroupFilter) filters.push({ key: 'caseGroup', label: 'Group', value: caseGroupFilter });

    if (referenceFilter !== 'all') {
      filters.push({
        key: 'reference',
        label: 'Reference',
        value: referenceFilter === 'with-reference' ? 'Present' : 'Missing',
      });
    }

    return filters;
  }, [
    referenceFilter,
    caseGroupFilter,
    caseNameFilter,
    creatorOptions,
    machineOptions,
    simulationFilters,
  ]);

  const setSimulationFilter = (key: keyof CaseSimulationFilters, value: string) => {
    setSimulationFilters((current) => ({
      ...current,
      [key]: value,
    }));
    table.setPageIndex(0);
  };

  const clearAllFilters = () => {
    setCaseNameFilter('');
    setCaseGroupFilter('');
    setSimulationFilters(createEmptySimulationFilters());
    setReferenceFilter('all');
    setShowAdvancedFilters(false);
    table.setPageIndex(0);
  };

  const removeFilter = (filterKey: ActiveFilterKey) => {
    switch (filterKey) {
      case 'caseName':
        setCaseNameFilter('');
        break;
      case 'caseGroup':
        setCaseGroupFilter('');
        break;
      case 'reference':
        setReferenceFilter('all');
        break;
      default:
        setSimulationFilters((current) => ({
          ...current,
          [filterKey]: '',
        }));
        break;
    }

    table.setPageIndex(0);
  };

  const filteredCases = useMemo(() => {
    const normalizedNameFilter = caseNameFilter.trim().toLowerCase();

    return cases.filter((caseRecord) => {
      const matchesName =
        normalizedNameFilter.length === 0 ||
        caseRecord.name.toLowerCase().includes(normalizedNameFilter);
      const matchesGroup = !caseGroupFilter || caseRecord.caseGroup === caseGroupFilter;
      const hasReferenceSimulation = caseRecord.referenceSimulationId != null;
      const matchesReference =
        referenceFilter === 'all' ||
        (referenceFilter === 'with-reference' && hasReferenceSimulation) ||
        (referenceFilter === 'without-reference' && !hasReferenceSimulation);
      const matchesSimulationFilters =
        !hasActiveSimulationFilters ||
        (matchingSimulationsByCaseId.get(caseRecord.id)?.length ?? 0) > 0;

      return matchesName && matchesGroup && matchesReference && matchesSimulationFilters;
    });
  }, [
    caseGroupFilter,
    cases,
    referenceFilter,
    caseNameFilter,
    hasActiveSimulationFilters,
    matchingSimulationsByCaseId,
  ]);

  const visibleRunCount = useMemo(
    () =>
      filteredCases.reduce((count, caseRecord) => {
        if (hasActiveSimulationFilters) {
          return count + (matchingSimulationsByCaseId.get(caseRecord.id)?.length ?? 0);
        }

        return (
          count + (simulationsByCaseId.get(caseRecord.id)?.length ?? caseRecord.simulations.length)
        );
      }, 0),
    [filteredCases, hasActiveSimulationFilters, matchingSimulationsByCaseId, simulationsByCaseId],
  );

  const columns = useMemo<ColumnDef<CaseOut>[]>(
    () => [
      {
        id: 'expand',
        header: '',
        enableSorting: false,
        cell: ({ row }) => {
          const isExpanded = expandedCaseId === row.original.id;

          return (
            <Button
              variant="ghost"
              size="icon"
              type="button"
              className="h-8 w-8"
              aria-label={isExpanded ? 'Collapse simulations' : 'Expand simulations'}
              onClick={(event) => {
                event.stopPropagation();
                setExpandedCaseId((current) =>
                  current === row.original.id ? null : row.original.id,
                );
              }}
            >
              {isExpanded ? (
                <ChevronDown className="h-4 w-4" />
              ) : (
                <ChevronRight className="h-4 w-4" />
              )}
            </Button>
          );
        },
      },
      {
        accessorKey: 'name',
        header: 'Case Name',
        cell: ({ row }) => (
          <Link
            to={`/cases/${row.original.id}`}
            state={{ from: currentPath }}
            className="block max-w-[28rem] truncate font-medium text-blue-600 hover:underline"
            title={row.original.name}
            onClick={(event) => event.stopPropagation()}
          >
            {row.original.name}
          </Link>
        ),
      },
      {
        id: 'hpcUsers',
        header: 'HPC Users',
        accessorFn: (caseRecord) => caseHpcUserSummaries.get(caseRecord.id) ?? '—',
        cell: ({ row }) => (
          <TableCellText value={caseHpcUserSummaries.get(row.original.id) ?? '—'} lines={1} />
        ),
      },
      {
        id: 'machines',
        header: 'Machines',
        accessorFn: (caseRecord) => caseMachineSummaries.get(caseRecord.id) ?? '—',
        cell: ({ row }) => (
          <TableCellText value={caseMachineSummaries.get(row.original.id) ?? '—'} lines={1} />
        ),
      },
      {
        id: 'simulationCount',
        header: 'Total Simulations',
        accessorFn: (caseRecord) => caseRecord.simulations.length,
        cell: ({ row }) => {
          const totalSimulations =
            simulationsByCaseId.get(row.original.id)?.length ?? row.original.simulations.length;

          return <Badge variant="secondary">{totalSimulations}</Badge>;
        },
      },
      {
        accessorKey: 'caseGroup',
        header: 'Case Group',
        cell: ({ row }) => <TableCellText value={row.original.caseGroup ?? '—'} />,
      },
      {
        accessorKey: 'updatedAt',
        header: 'Last Updated',
        cell: ({ row }) => formatCaseDate(row.original.updatedAt),
      },
      {
        id: 'details',
        header: 'Details',
        enableSorting: false,
        cell: ({ row }) => (
          <Button variant="outline" size="sm" asChild onClick={(event) => event.stopPropagation()}>
            <Link to={`/cases/${row.original.id}`} state={{ from: currentPath }}>
              View case
            </Link>
          </Button>
        ),
      },
    ],
    [caseHpcUserSummaries, caseMachineSummaries, currentPath, expandedCaseId, simulationsByCaseId],
  );

  const table = useReactTable({
    data: filteredCases,
    columns,
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    initialState: {
      pagination: {
        pageIndex: 0,
        pageSize: 25,
      },
    },
  });

  const renderSelectField = ({
    label,
    value,
    placeholder,
    options,
    onValueChange,
  }: {
    label: string;
    value: string;
    placeholder: string;
    options: SelectOption[];
    onValueChange: (value: string) => void;
  }) => (
    <div className="space-y-2">
      <label className="text-xs font-medium uppercase tracking-[0.12em] text-slate-500">
        {label}
      </label>
      <Select value={value || '__all__'} onValueChange={onValueChange}>
        <SelectTrigger className="h-10 rounded-xl border-slate-200 bg-white shadow-none">
          <SelectValue placeholder={placeholder} />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="__all__">{placeholder}</SelectItem>
          {options.map((option) => (
            <SelectItem key={option.value} value={option.value}>
              {option.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );

  const renderExpandedContent = (caseRecord: CaseOut) => {
    const detailedCaseSimulations = simulationsByCaseId.get(caseRecord.id);
    const summaryCaseSimulations = caseRecord.simulations;
    const isUsingSummaryFallback =
      (detailedCaseSimulations == null || detailedCaseSimulations.length === 0) &&
      summaryCaseSimulations.length > 0;
    const allCaseSimulations = sortCaseSimulations(
      detailedCaseSimulations?.length ? detailedCaseSimulations : summaryCaseSimulations,
    );
    const matchingCaseSimulations = sortCaseSimulations(
      isUsingSummaryFallback
        ? summaryCaseSimulations
        : (matchingSimulationsByCaseId.get(caseRecord.id) ?? []),
    );
    const visibleCaseSimulations = hasActiveSimulationFilters
      ? matchingCaseSimulations
      : allCaseSimulations;

    return (
      <div className="space-y-3 bg-muted/20 p-4">
        <div className="flex items-center justify-between gap-3">
          <div>
            <p className="text-sm font-medium">Simulation Summaries</p>
            <p className="text-xs text-muted-foreground">
              {isUsingSummaryFallback
                ? 'Showing case-level run summaries because full simulation details are unavailable.'
                : hasActiveSimulationFilters
                  ? `${matchingCaseSimulations.length} of ${allCaseSimulations.length} runs match the current filters.`
                  : 'Reference runs are pinned first. Open the case page for full context.'}
            </p>
          </div>
          <Button variant="outline" size="sm" asChild>
            <Link to={`/cases/${caseRecord.id}`} state={{ from: currentPath }}>
              Open case page
            </Link>
          </Button>
        </div>

        <div className="max-w-4xl overflow-hidden rounded-md border bg-background">
          <div className="max-h-[26rem] overflow-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Execution ID</TableHead>
                  <TableHead>Changes</TableHead>
                  <TableHead>Simulation Dates</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {visibleCaseSimulations.map((simulation) => (
                  <TableRow key={simulation.id}>
                    <TableCell className="align-top">
                      <Link
                        to={`/simulations/${simulation.id}`}
                        state={{ from: currentPath }}
                        className="inline-flex items-center gap-1 font-mono text-xs text-blue-600 hover:underline"
                      >
                        {simulation.executionId}
                        {simulation.isReference && (
                          <span
                            className="inline-flex items-center"
                            title="Reference simulation"
                            aria-label="Reference simulation"
                          >
                            <Pin className="h-3.5 w-3.5 text-amber-600" />
                          </span>
                        )}
                      </Link>
                    </TableCell>
                    <TableCell className="align-top">
                      {simulation.isReference ? (
                        <span
                          className="text-sm font-medium text-slate-700"
                          title="Reference simulation"
                        >
                          Reference
                        </span>
                      ) : (
                        <Badge variant="secondary" title={getSimulationChangeTitle(simulation)}>
                          {simulation.changeCount}
                        </Badge>
                      )}
                    </TableCell>
                    <TableCell className="align-top">
                      {`${formatCaseDate(simulation.simulationStartDate)} → ${formatCaseDate(
                        simulation.simulationEndDate ?? null,
                      )}`}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </div>
      </div>
    );
  };

  if (loading) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center">
        <div className="text-center text-gray-500">Loading cases…</div>
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

  return (
    <div className="mx-auto w-full max-w-[1480px] space-y-6 px-6 py-8">
      <div className="overflow-hidden rounded-3xl border border-slate-200/80 bg-gradient-to-br from-white via-slate-50/70 to-slate-100/80 shadow-sm">
        <div className="space-y-5 p-5 sm:p-6">
          <div className="flex flex-col gap-5 xl:flex-row xl:items-end xl:justify-between">
            <div className="space-y-3">
              <div className="space-y-2">
                <h1 className="text-3xl font-semibold tracking-tight text-slate-950">Cases</h1>
                <p className="max-w-3xl text-sm leading-6 text-slate-600 sm:text-[15px]">
                  Find the cases behind your runs. Start with HPC username or machine, then refine
                  by campaign, version context, and reference state.
                </p>
              </div>
            </div>

            <div className="grid gap-3 sm:grid-cols-3 xl:min-w-[440px]">
              <div className="rounded-2xl border border-slate-200 bg-white/85 p-4 shadow-sm shadow-slate-200/30">
                <p className="text-xs font-medium uppercase tracking-[0.14em] text-slate-500">
                  Cases shown
                </p>
                <p className="mt-3 text-2xl font-semibold tracking-tight text-slate-950">
                  {filteredCases.length}
                </p>
                <p className="mt-1 text-xs text-slate-500">of {cases.length} total cases</p>
              </div>
              <div className="rounded-2xl border border-slate-200 bg-white/85 p-4 shadow-sm shadow-slate-200/30">
                <p className="text-xs font-medium uppercase tracking-[0.14em] text-slate-500">
                  Runs shown
                </p>
                <p className="mt-3 text-2xl font-semibold tracking-tight text-slate-950">
                  {visibleRunCount}
                </p>
                <p className="mt-1 text-xs text-slate-500">
                  {hasActiveSimulationFilters
                    ? 'matching runs in visible cases'
                    : 'runs across visible cases'}
                </p>
              </div>
              <div className="rounded-2xl border border-slate-200 bg-white/85 p-4 shadow-sm shadow-slate-200/30">
                <p className="text-xs font-medium uppercase tracking-[0.14em] text-slate-500">
                  Active filters
                </p>
                <p className="mt-3 text-2xl font-semibold tracking-tight text-slate-950">
                  {activeFilterPills.length}
                </p>
                <p className="mt-1 text-xs text-slate-500">
                  {advancedFilterCount > 0
                    ? `${advancedFilterCount} advanced refinements applied`
                    : 'Quick case discovery'}
                </p>
              </div>
            </div>
          </div>

          <Collapsible open={showAdvancedFilters} onOpenChange={setShowAdvancedFilters}>
            <div className="rounded-2xl border border-slate-200 bg-white/90 p-4 shadow-sm shadow-slate-200/30">
              <div className="flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
                <div className="grid flex-1 gap-3 md:grid-cols-[minmax(0,1.35fr)_220px_220px]">
                  <div className="space-y-2">
                    <label className="text-xs font-medium uppercase tracking-[0.12em] text-slate-500">
                      Search
                    </label>
                    <div className="relative">
                      <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
                      <Input
                        placeholder="Search case name…"
                        value={caseNameFilter}
                        onChange={(event) => {
                          setCaseNameFilter(event.target.value);
                          table.setPageIndex(0);
                        }}
                        className="h-10 rounded-xl border-slate-200 bg-white pl-10 shadow-none"
                      />
                    </div>
                  </div>

                  {renderSelectField({
                    label: 'HPC Username',
                    value: simulationFilters.hpcUsername,
                    placeholder: 'All HPC usernames',
                    options: hpcUsernames.map((username) => ({
                      value: username,
                      label: username,
                    })),
                    onValueChange: (value) =>
                      setSimulationFilter('hpcUsername', value === '__all__' ? '' : value),
                  })}

                  {renderSelectField({
                    label: 'Machine',
                    value: simulationFilters.machineId,
                    placeholder: 'All machines',
                    options: machineOptions,
                    onValueChange: (value) =>
                      setSimulationFilter('machineId', value === '__all__' ? '' : value),
                  })}
                </div>

                <div className="flex flex-wrap items-center gap-2 lg:justify-end">
                  <CollapsibleTrigger asChild>
                    <Button
                      variant="outline"
                      type="button"
                      className="h-10 rounded-xl border-slate-200 bg-white px-4 text-slate-700 shadow-none hover:bg-slate-50"
                    >
                      <SlidersHorizontal className="mr-2 h-4 w-4" />
                      {advancedFilterCount > 0
                        ? `More filters (${advancedFilterCount})`
                        : 'More filters'}
                      <ChevronDown
                        className={cn(
                          'ml-2 h-4 w-4 transition-transform duration-200',
                          showAdvancedFilters && 'rotate-180',
                        )}
                      />
                    </Button>
                  </CollapsibleTrigger>
                  <Button
                    variant="ghost"
                    type="button"
                    onClick={clearAllFilters}
                    disabled={!hasActiveFilters}
                    className="h-10 rounded-xl px-4 text-slate-600 hover:bg-slate-100 hover:text-slate-900"
                  >
                    Clear all
                  </Button>
                </div>
              </div>

              <CollapsibleContent>
                <div className="mt-4 border-t border-slate-200 pt-4">
                  <div className="grid gap-6 xl:grid-cols-[minmax(0,2fr)_minmax(260px,1fr)]">
                    <div className="space-y-4">
                      <div className="space-y-1">
                        <p className="text-sm font-medium text-slate-900">Run context</p>
                        <p className="text-xs text-slate-500">
                          Filter cases by the metadata attached to the runs inside them.
                        </p>
                      </div>
                      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
                        {renderSelectField({
                          label: 'Campaign',
                          value: simulationFilters.campaign,
                          placeholder: 'All campaigns',
                          options: campaigns.map((campaign) => ({
                            value: campaign,
                            label: campaign,
                          })),
                          onValueChange: (value) =>
                            setSimulationFilter('campaign', value === '__all__' ? '' : value),
                        })}
                        {renderSelectField({
                          label: 'Type',
                          value: simulationFilters.simulationType,
                          placeholder: 'All types',
                          options: simulationTypes.map((simulationType) => ({
                            value: simulationType,
                            label: simulationType,
                          })),
                          onValueChange: (value) =>
                            setSimulationFilter('simulationType', value === '__all__' ? '' : value),
                        })}
                        {renderSelectField({
                          label: 'Initialization',
                          value: simulationFilters.initializationType,
                          placeholder: 'All init types',
                          options: initializationTypes.map((initializationType) => ({
                            value: initializationType,
                            label: initializationType,
                          })),
                          onValueChange: (value) =>
                            setSimulationFilter(
                              'initializationType',
                              value === '__all__' ? '' : value,
                            ),
                        })}
                        {renderSelectField({
                          label: 'Compiler',
                          value: simulationFilters.compiler,
                          placeholder: 'All compilers',
                          options: compilers.map((compiler) => ({
                            value: compiler,
                            label: compiler,
                          })),
                          onValueChange: (value) =>
                            setSimulationFilter('compiler', value === '__all__' ? '' : value),
                        })}
                        {renderSelectField({
                          label: 'Tag',
                          value: simulationFilters.gitTag,
                          placeholder: 'All tags',
                          options: gitTags.map((gitTag) => ({ value: gitTag, label: gitTag })),
                          onValueChange: (value) =>
                            setSimulationFilter('gitTag', value === '__all__' ? '' : value),
                        })}
                        {renderSelectField({
                          label: 'Creator',
                          value: simulationFilters.createdBy,
                          placeholder: 'All creators',
                          options: creatorOptions,
                          onValueChange: (value) =>
                            setSimulationFilter('createdBy', value === '__all__' ? '' : value),
                        })}
                      </div>
                    </div>

                    <div className="space-y-4 rounded-2xl border border-slate-200 bg-slate-50/80 p-4">
                      <div className="space-y-1">
                        <p className="text-sm font-medium text-slate-900">Case settings</p>
                        <p className="text-xs text-slate-500">
                          Narrow the result set using case-level metadata and reference state.
                        </p>
                      </div>
                      <div className="grid gap-3">
                        {renderSelectField({
                          label: 'Case group',
                          value: caseGroupFilter,
                          placeholder: 'All case groups',
                          options: caseGroups.map((group) => ({ value: group, label: group })),
                          onValueChange: (value) => {
                            setCaseGroupFilter(value === '__all__' ? '' : value);
                            table.setPageIndex(0);
                          },
                        })}
                        <div className="space-y-2">
                          <label className="text-xs font-medium uppercase tracking-[0.12em] text-slate-500">
                            Reference state
                          </label>
                          <Select
                            value={referenceFilter}
                            onValueChange={(value: ReferenceFilter) => {
                              setReferenceFilter(value);
                              table.setPageIndex(0);
                            }}
                          >
                            <SelectTrigger className="h-10 rounded-xl border-slate-200 bg-white shadow-none">
                              <SelectValue />
                            </SelectTrigger>
                            <SelectContent>
                              <SelectItem value="all">All reference states</SelectItem>
                              <SelectItem value="with-reference">Reference present</SelectItem>
                              <SelectItem value="without-reference">Reference missing</SelectItem>
                            </SelectContent>
                          </Select>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              </CollapsibleContent>
            </div>
          </Collapsible>

          {hasActiveFilters && (
            <div className="flex flex-wrap items-center gap-2">
              {activeFilterPills.map((filter) => (
                <span
                  key={`${filter.key}-${filter.value}`}
                  className="inline-flex items-center rounded-full border border-slate-200 bg-white px-3 py-1.5 text-sm text-slate-700 shadow-sm shadow-slate-200/30"
                >
                  <span className="mr-2 text-xs font-medium uppercase tracking-[0.08em] text-slate-500">
                    {filter.label}
                  </span>
                  <span className="font-medium">{filter.value}</span>
                  <button
                    type="button"
                    aria-label={`Remove ${filter.label} filter`}
                    className="ml-2 inline-flex h-5 w-5 items-center justify-center rounded-full text-slate-400 transition-colors hover:bg-slate-100 hover:text-slate-700"
                    onClick={() => removeFilter(filter.key)}
                  >
                    <X className="h-3.5 w-3.5" />
                  </button>
                </span>
              ))}
            </div>
          )}
        </div>
      </div>

      <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              {table.getHeaderGroups().map((headerGroup) => (
                <TableRow key={headerGroup.id}>
                  {headerGroup.headers.map((header) => (
                    <TableHead key={header.id}>
                      {header.isPlaceholder ? null : (
                        <button
                          type="button"
                          className={
                            header.column.getCanSort() ? 'select-none text-left' : 'text-left'
                          }
                          onClick={header.column.getToggleSortingHandler()}
                        >
                          {flexRender(header.column.columnDef.header, header.getContext())}
                          {header.column.getIsSorted() === 'asc' && ' ▲'}
                          {header.column.getIsSorted() === 'desc' && ' ▼'}
                        </button>
                      )}
                    </TableHead>
                  ))}
                </TableRow>
              ))}
            </TableHeader>
            <TableBody>
              {table.getRowModel().rows.length > 0 ? (
                table.getRowModel().rows.map((row) => {
                  const isExpanded = expandedCaseId === row.original.id;

                  return (
                    <Fragment key={row.id}>
                      <TableRow
                        className="cursor-pointer hover:bg-muted/40"
                        onClick={() =>
                          setExpandedCaseId((current) =>
                            current === row.original.id ? null : row.original.id,
                          )
                        }
                      >
                        {row.getVisibleCells().map((cell) => (
                          <TableCell key={cell.id} className="align-top">
                            {flexRender(cell.column.columnDef.cell, cell.getContext())}
                          </TableCell>
                        ))}
                      </TableRow>
                      {isExpanded && (
                        <TableRow className="hover:bg-transparent">
                          <TableCell colSpan={columns.length} className="p-0">
                            {renderExpandedContent(row.original)}
                          </TableCell>
                        </TableRow>
                      )}
                    </Fragment>
                  );
                })
              ) : (
                <TableRow>
                  <TableCell
                    colSpan={columns.length}
                    className="py-10 text-center text-muted-foreground"
                  >
                    No cases match the current filters.
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </div>
      </div>

      <div className="flex flex-col gap-3 text-sm text-muted-foreground md:flex-row md:items-center md:justify-between">
        <div>
          Showing {table.getRowModel().rows.length} of {filteredCases.length} filtered cases
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => table.previousPage()}
            disabled={!table.getCanPreviousPage()}
          >
            Previous
          </Button>
          <span>
            Page {table.getState().pagination.pageIndex + 1} of {table.getPageCount() || 1}
          </span>
          <Button
            variant="outline"
            size="sm"
            onClick={() => table.nextPage()}
            disabled={!table.getCanNextPage()}
          >
            Next
          </Button>
        </div>
      </div>
    </div>
  );
};
