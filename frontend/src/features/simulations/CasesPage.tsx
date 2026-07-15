import type { ColumnDef, SortingState } from '@tanstack/react-table';
import {
  flexRender,
  getCoreRowModel,
  useReactTable,
} from '@tanstack/react-table';
import { ChevronDown, ChevronRight, Search, SlidersHorizontal, X } from 'lucide-react';
import { Fragment, useEffect, useMemo, useState } from 'react';
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
import {
  formatCaseDate,
  formatCaseHashLabel,
  MISSING_CASE_HASH_LABEL,
} from '@/features/simulations/caseUtils';
import { useCaseFilterOptions } from '@/features/simulations/hooks/useCaseFilterOptions';
import { useCases } from '@/features/simulations/hooks/useCases';
import { useSimulations } from '@/features/simulations/hooks/useSimulations';
import { cn } from '@/lib/utils';
import type {
  CaseListItemOut,
  SimulationListItemOut,
} from '@/types';

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
  | 'caseGroup';

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

const sortCaseSimulations = (caseSimulations: SimulationListItemOut[]) =>
  [...caseSimulations].sort(
    (left, right) =>
      new Date(right.simulationStartDate).getTime() - new Date(left.simulationStartDate).getTime(),
  );

const CASE_SORT_FIELDS: Record<string, string> = {
  name: 'name',
  hpcUsers: 'hpc_username',
  machines: 'machine_name',
  simulationCount: 'simulation_count',
  caseGroup: 'case_group',
  createdAt: 'created_at',
  updatedAt: 'updated_at',
};

export const CasesPage = () => {
  const location = useLocation();
  const currentPath = `${location.pathname}${location.search}`;

  const [caseNameFilter, setCaseNameFilter] = useState('');
  const [debouncedCaseName, setDebouncedCaseName] = useState('');
  const [caseGroupFilter, setCaseGroupFilter] = useState('');
  const [simulationFilters, setSimulationFilters] = useState<CaseSimulationFilters>(
    createEmptySimulationFilters,
  );
  const [showAdvancedFilters, setShowAdvancedFilters] = useState(false);
  const [expandedCaseId, setExpandedCaseId] = useState<string | null>(null);
  const [expandedSimulationPage, setExpandedSimulationPage] = useState(1);
  const { data: simulations, page: expandedSimulationPageData } = useSimulations(
    {
      caseId: expandedCaseId ?? undefined,
      page: expandedSimulationPage,
      pageSize: 25,
      hpcUsername: simulationFilters.hpcUsername || undefined,
      machineId: simulationFilters.machineId || undefined,
      campaign: simulationFilters.campaign || undefined,
      simulationType: simulationFilters.simulationType || undefined,
      initializationType: simulationFilters.initializationType || undefined,
      compiler: simulationFilters.compiler || undefined,
      gitTag: simulationFilters.gitTag || undefined,
      createdBy: simulationFilters.createdBy || undefined,
    },
    expandedCaseId != null,
  );
  const { data: filterOptions } = useCaseFilterOptions();
  const [sorting, setSorting] = useState<SortingState>([
    { id: 'updatedAt', desc: true },
    { id: 'name', desc: false },
  ]);
  const [pagination, setPagination] = useState({ pageIndex: 0, pageSize: 25 });
  useEffect(() => {
    const timeout = window.setTimeout(() => setDebouncedCaseName(caseNameFilter.trim()), 300);
    return () => window.clearTimeout(timeout);
  }, [caseNameFilter]);
  useEffect(() => {
    setPagination((current) => ({ ...current, pageIndex: 0 }));
  }, [debouncedCaseName, caseGroupFilter, simulationFilters]);
  useEffect(() => {
    setPagination((current) => ({ ...current, pageIndex: 0 }));
  }, [sorting]);
  useEffect(() => {
    setExpandedSimulationPage(1);
  }, [expandedCaseId, simulationFilters]);
  const primarySort = sorting[0];
  const { data: cases, page: casePage, loading, error } = useCases({
    page: pagination.pageIndex + 1,
    pageSize: pagination.pageSize,
    search: debouncedCaseName || undefined,
    caseGroup: caseGroupFilter || undefined,
    hpcUsername: simulationFilters.hpcUsername || undefined,
    machineId: simulationFilters.machineId || undefined,
    campaign: simulationFilters.campaign || undefined,
    simulationType: simulationFilters.simulationType || undefined,
    initializationType: simulationFilters.initializationType || undefined,
    compiler: simulationFilters.compiler || undefined,
    gitTag: simulationFilters.gitTag || undefined,
    createdBy: simulationFilters.createdBy || undefined,
    sortBy: primarySort ? CASE_SORT_FIELDS[primarySort.id] : 'updated_at',
    sortOrder: primarySort?.desc === false ? 'asc' : 'desc',
  });

  const caseGroups = filterOptions?.caseGroups ?? [];

  const simulationsByCaseId = useMemo(() => {
    const caseMap = new Map<string, SimulationListItemOut[]>();
    for (const simulation of simulations) {
      const caseSimulations = caseMap.get(simulation.caseId) ?? [];
      caseSimulations.push(simulation);
      caseMap.set(simulation.caseId, caseSimulations);
    }

    return caseMap;
  }, [simulations]);

  const hpcUsernames = filterOptions?.hpcUsernames ?? [];
  const machineOptions = useMemo(() => filterOptions?.machines ?? [], [filterOptions?.machines]);
  const creatorOptions = useMemo(() => filterOptions?.creators ?? [], [filterOptions?.creators]);
  const campaigns = filterOptions?.campaigns ?? [];
  const simulationTypes = filterOptions?.simulationTypes ?? [];
  const initializationTypes = filterOptions?.initializationTypes ?? [];
  const compilers = filterOptions?.compilers ?? [];
  const gitTags = filterOptions?.gitTags ?? [];

  const hasActiveSimulationFilters = useMemo(
    () => Object.values(simulationFilters).some(Boolean),
    [simulationFilters],
  );
  const hasActiveFilters =
    caseNameFilter.trim().length > 0 || caseGroupFilter.length > 0 || hasActiveSimulationFilters;
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
      ].filter(Boolean).length,
    [caseGroupFilter, simulationFilters],
  );
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

    return filters;
  }, [caseGroupFilter, caseNameFilter, creatorOptions, machineOptions, simulationFilters]);

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
      return matchesName && matchesGroup;
    });
  }, [
    caseGroupFilter,
    cases,
    caseNameFilter,
  ]);

  const visibleRunCount = useMemo(
    () => filteredCases.reduce((count, caseRecord) => count + caseRecord.simulationCount, 0),
    [filteredCases],
  );

  const columns = useMemo<ColumnDef<CaseListItemOut>[]>(
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
        accessorFn: (caseRecord) => caseRecord.hpcUsername,
        cell: ({ row }) => (
          <TableCellText value={row.original.hpcUsername} lines={1} />
        ),
      },
      {
        id: 'machines',
        header: 'Machines',
        accessorFn: (caseRecord) => caseRecord.machineName,
        cell: ({ row }) => (
          <TableCellText value={row.original.machineName} lines={1} />
        ),
      },
      {
        id: 'simulationCount',
        header: 'Total Simulations',
        accessorFn: (caseRecord) => caseRecord.simulationCount,
        cell: ({ row }) => {
          return <Badge variant="secondary">{row.original.simulationCount}</Badge>;
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
    [currentPath, expandedCaseId],
  );

  const table = useReactTable({
    data: filteredCases,
    columns,
    state: { sorting, pagination },
    onSortingChange: setSorting,
    onPaginationChange: setPagination,
    getCoreRowModel: getCoreRowModel(),
    manualSorting: true,
    manualPagination: true,
    pageCount: Math.ceil((casePage?.total ?? 0) / pagination.pageSize),
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

  const renderExpandedContent = (caseRecord: CaseListItemOut) => {
    const visibleCaseSimulations = sortCaseSimulations(
      simulationsByCaseId.get(caseRecord.id) ?? [],
    );
    const expandedSimulationTotal = expandedSimulationPageData?.total ?? 0;
    const expandedSimulationPageCount = Math.max(1, Math.ceil(expandedSimulationTotal / 25));

    return (
      <div className="space-y-3 bg-muted/20 p-4">
        <div className="flex items-center justify-between gap-3">
          <div>
            <p className="text-sm font-medium">Simulation Summaries</p>
            <p className="text-xs text-muted-foreground">
              {hasActiveSimulationFilters
                  ? `${expandedSimulationTotal} runs match the current filters.`
                  : 'Open the case page to organize runs by Case Hash and launch compare.'}
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
                  <TableHead>Case Hash</TableHead>
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
                      </Link>
                    </TableCell>
                    <TableCell className="align-top">
                      <span
                        className="font-mono text-xs text-slate-700"
                        title={simulation.caseHash ?? MISSING_CASE_HASH_LABEL}
                      >
                        {formatCaseHashLabel(simulation.caseHash ?? null)}
                      </span>
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
        {expandedSimulationTotal > 25 && (
          <div className="flex max-w-4xl items-center justify-end gap-2 text-sm">
            <Button
              variant="outline"
              size="sm"
              disabled={expandedSimulationPage <= 1}
              onClick={() => setExpandedSimulationPage((page) => Math.max(1, page - 1))}
            >
              Previous runs
            </Button>
            <span>
              Page {expandedSimulationPage} of {expandedSimulationPageCount}
            </span>
            <Button
              variant="outline"
              size="sm"
              disabled={expandedSimulationPage >= expandedSimulationPageCount}
              onClick={() =>
                setExpandedSimulationPage((page) => Math.min(expandedSimulationPageCount, page + 1))
              }
            >
              Next runs
            </Button>
          </div>
        )}
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
                  by campaign, version context, and case metadata.
                </p>
              </div>
            </div>

            <div className="grid gap-3 sm:grid-cols-3 xl:min-w-[440px]">
              <div className="rounded-2xl border border-slate-200 bg-white/85 p-4 shadow-sm shadow-slate-200/30">
                <p className="text-xs font-medium uppercase tracking-[0.14em] text-slate-500">
                  Cases on page
                </p>
                <p className="mt-3 text-2xl font-semibold tracking-tight text-slate-950">
                  {filteredCases.length}
                </p>
                <p className="mt-1 text-xs text-slate-500">
                  of {casePage?.total ?? 0} matching cases
                </p>
              </div>
              <div className="rounded-2xl border border-slate-200 bg-white/85 p-4 shadow-sm shadow-slate-200/30">
                <p className="text-xs font-medium uppercase tracking-[0.14em] text-slate-500">
                  Runs on page
                </p>
                <p className="mt-3 text-2xl font-semibold tracking-tight text-slate-950">
                  {visibleRunCount}
                </p>
                <p className="mt-1 text-xs text-slate-500">
                  total runs across visible cases
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
                          Narrow the result set using case-level metadata.
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
          Showing {table.getRowModel().rows.length} of {casePage?.total ?? 0} filtered cases
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
