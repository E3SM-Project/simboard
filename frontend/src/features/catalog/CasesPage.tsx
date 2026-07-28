import type { ColumnDef, SortingState } from '@tanstack/react-table';
import { flexRender, getCoreRowModel, useReactTable } from '@tanstack/react-table';
import { ChevronDown, ChevronRight, Search, SlidersHorizontal, X } from 'lucide-react';
import { Fragment, useEffect, useMemo, useState } from 'react';
import { Link, useLocation } from 'react-router-dom';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible';
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
  MISSING_CASE_HASH_LABEL,
} from '@/features/catalog/caseUtils';
import { SearchableFilterSelect } from '@/features/catalog/components/SearchableFilterSelect';
import { useCaseFilterOptions } from '@/lib/catalog/hooks/useCaseFilterOptions';
import { useCases } from '@/lib/catalog/hooks/useCases';
import { useExecutions } from '@/lib/catalog/hooks/useExecutions';
import { cn } from '@/lib/utils';
import type { CaseListItemOut, ExecutionListItemOut } from '@/types';
import { compareModelDates, formatModelDate } from '@/utils/utils';

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

interface CaseExecutionFilters {
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

const createEmptyExecutionFilters = (): CaseExecutionFilters => ({
  hpcUsername: '',
  machineId: '',
  campaign: '',
  simulationType: '',
  initializationType: '',
  compiler: '',
  gitTag: '',
  createdBy: '',
});

const sortCaseExecutions = (caseExecutions: ExecutionListItemOut[]) =>
  [...caseExecutions].sort((left, right) =>
    compareModelDates(right.simulationStartDate, left.simulationStartDate),
  );

const CASE_SORT_FIELDS: Record<string, string> = {
  name: 'name',
  hpcUsers: 'hpc_username',
  machines: 'machine_name',
  executionCount: 'execution_count',
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
  const [executionFilters, setExecutionFilters] = useState<CaseExecutionFilters>(
    createEmptyExecutionFilters,
  );
  const [showAdvancedFilters, setShowAdvancedFilters] = useState(false);
  const [expandedCaseId, setExpandedCaseId] = useState<string | null>(null);
  const [expandedExecutionPage, setExpandedExecutionPage] = useState(1);
  const { data: executions, page: expandedExecutionPageData } = useExecutions(
    {
      caseId: expandedCaseId ?? undefined,
      page: expandedExecutionPage,
      pageSize: 25,
      hpcUsername: executionFilters.hpcUsername || undefined,
      machineId: executionFilters.machineId || undefined,
      campaign: executionFilters.campaign || undefined,
      simulationType: executionFilters.simulationType || undefined,
      initializationType: executionFilters.initializationType || undefined,
      compiler: executionFilters.compiler || undefined,
      gitTag: executionFilters.gitTag || undefined,
      createdBy: executionFilters.createdBy || undefined,
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
  }, [debouncedCaseName, caseGroupFilter, executionFilters]);
  useEffect(() => {
    setPagination((current) => ({ ...current, pageIndex: 0 }));
  }, [sorting]);
  useEffect(() => {
    setExpandedExecutionPage(1);
  }, [expandedCaseId, executionFilters]);
  const primarySort = sorting[0];
  const {
    data: cases,
    page: casePage,
    loading,
    error,
  } = useCases({
    page: pagination.pageIndex + 1,
    pageSize: pagination.pageSize,
    search: debouncedCaseName || undefined,
    caseGroup: caseGroupFilter || undefined,
    hpcUsername: executionFilters.hpcUsername || undefined,
    machineId: executionFilters.machineId || undefined,
    campaign: executionFilters.campaign || undefined,
    simulationType: executionFilters.simulationType || undefined,
    initializationType: executionFilters.initializationType || undefined,
    compiler: executionFilters.compiler || undefined,
    gitTag: executionFilters.gitTag || undefined,
    createdBy: executionFilters.createdBy || undefined,
    sortBy: primarySort ? CASE_SORT_FIELDS[primarySort.id] : 'updated_at',
    sortOrder: primarySort?.desc === false ? 'asc' : 'desc',
  });

  const executionsByCaseId = useMemo(() => {
    const caseMap = new Map<string, ExecutionListItemOut[]>();
    for (const execution of executions) {
      const caseExecutions = caseMap.get(execution.caseId) ?? [];
      caseExecutions.push(execution);
      caseMap.set(execution.caseId, caseExecutions);
    }

    return caseMap;
  }, [executions]);

  const {
    caseGroupOptions,
    hpcUsernameOptions,
    machineOptions,
    creatorOptions,
    campaignOptions,
    simulationTypeOptions,
    initializationTypeOptions,
    compilerOptions,
    gitTagOptions,
  } = useMemo(
    () => ({
      caseGroupOptions: (filterOptions?.caseGroups ?? []).map((group) => ({
        value: group,
        label: group,
      })),
      hpcUsernameOptions: (filterOptions?.hpcUsernames ?? []).map((username) => ({
        value: username,
        label: username,
      })),
      machineOptions: filterOptions?.machines ?? [],
      creatorOptions: filterOptions?.creators ?? [],
      campaignOptions: (filterOptions?.campaigns ?? []).map((campaign) => ({
        value: campaign,
        label: campaign,
      })),
      simulationTypeOptions: (filterOptions?.simulationTypes ?? []).map((simulationType) => ({
        value: simulationType,
        label: simulationType,
      })),
      initializationTypeOptions: (filterOptions?.initializationTypes ?? []).map(
        (initializationType) => ({ value: initializationType, label: initializationType }),
      ),
      compilerOptions: (filterOptions?.compilers ?? []).map((compiler) => ({
        value: compiler,
        label: compiler,
      })),
      gitTagOptions: (filterOptions?.gitTags ?? []).map((gitTag) => ({
        value: gitTag,
        label: gitTag,
      })),
    }),
    [filterOptions],
  );

  const hasActiveExecutionFilters = useMemo(
    () => Object.values(executionFilters).some(Boolean),
    [executionFilters],
  );
  const hasActiveFilters =
    caseNameFilter.trim().length > 0 || caseGroupFilter.length > 0 || hasActiveExecutionFilters;
  const advancedFilterCount = useMemo(
    () =>
      [
        executionFilters.machineId,
        executionFilters.campaign,
        executionFilters.simulationType,
        executionFilters.initializationType,
        executionFilters.compiler,
        executionFilters.gitTag,
        executionFilters.createdBy,
        caseGroupFilter,
      ].filter(Boolean).length,
    [caseGroupFilter, executionFilters],
  );
  const activeFilterPills = useMemo(() => {
    const filters: ActiveFilterPill[] = [];

    if (caseNameFilter.trim()) {
      filters.push({ key: 'caseName', label: 'Case', value: caseNameFilter.trim() });
    }

    if (executionFilters.hpcUsername) {
      filters.push({ key: 'hpcUsername', label: 'HPC', value: executionFilters.hpcUsername });
    }

    if (executionFilters.machineId) {
      filters.push({
        key: 'machineId',
        label: 'Machine',
        value:
          machineOptions.find((option) => option.value === executionFilters.machineId)?.label ??
          executionFilters.machineId,
      });
    }

    if (executionFilters.campaign) {
      filters.push({ key: 'campaign', label: 'Campaign', value: executionFilters.campaign });
    }
    if (executionFilters.simulationType) {
      filters.push({
        key: 'simulationType',
        label: 'Type',
        value: executionFilters.simulationType,
      });
    }

    if (executionFilters.initializationType) {
      filters.push({
        key: 'initializationType',
        label: 'Init',
        value: executionFilters.initializationType,
      });
    }

    if (executionFilters.compiler) {
      filters.push({ key: 'compiler', label: 'Compiler', value: executionFilters.compiler });
    }

    if (executionFilters.gitTag) {
      filters.push({ key: 'gitTag', label: 'Tag', value: executionFilters.gitTag });
    }

    if (executionFilters.createdBy) {
      filters.push({
        key: 'createdBy',
        label: 'Creator',
        value:
          creatorOptions.find((option) => option.value === executionFilters.createdBy)?.label ??
          executionFilters.createdBy,
      });
    }

    if (caseGroupFilter) filters.push({ key: 'caseGroup', label: 'Group', value: caseGroupFilter });

    return filters;
  }, [caseGroupFilter, caseNameFilter, creatorOptions, machineOptions, executionFilters]);

  const setExecutionFilter = (key: keyof CaseExecutionFilters, value: string) => {
    setExecutionFilters((current) => ({
      ...current,
      [key]: value,
    }));
    table.setPageIndex(0);
  };

  const clearAllFilters = () => {
    setCaseNameFilter('');
    setCaseGroupFilter('');
    setExecutionFilters(createEmptyExecutionFilters());
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
        setExecutionFilters((current) => ({
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
  }, [caseGroupFilter, cases, caseNameFilter]);

  const visibleRunCount = useMemo(
    () => filteredCases.reduce((count, caseRecord) => count + caseRecord.executionCount, 0),
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
              aria-label={isExpanded ? 'Collapse executions' : 'Expand executions'}
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
        cell: ({ row }) => <TableCellText value={row.original.hpcUsername} lines={1} />,
      },
      {
        id: 'machines',
        header: 'Machines',
        accessorFn: (caseRecord) => caseRecord.machineName,
        cell: ({ row }) => <TableCellText value={row.original.machineName} lines={1} />,
      },
      {
        id: 'executionCount',
        header: 'Total Executions',
        accessorFn: (caseRecord) => caseRecord.executionCount,
        cell: ({ row }) => {
          return <Badge variant="secondary">{row.original.executionCount}</Badge>;
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
    pageCount: Math.max(1, Math.ceil((casePage?.total ?? 0) / pagination.pageSize)),
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
      <SearchableFilterSelect
        label={label}
        value={value}
        placeholder={placeholder}
        options={options}
        onValueChange={onValueChange}
      />
    </div>
  );

  const renderExpandedContent = (caseRecord: CaseListItemOut) => {
    const visibleCaseExecutions = sortCaseExecutions(
      executionsByCaseId.get(caseRecord.id) ?? [],
    );
    const expandedExecutionTotal = expandedExecutionPageData?.total ?? 0;
    const expandedExecutionPageCount = Math.max(1, Math.ceil(expandedExecutionTotal / 25));

    return (
      <div className="space-y-3 bg-muted/20 p-4">
        <div className="flex items-center justify-between gap-3">
          <div>
            <p className="text-sm font-medium">Execution Summaries</p>
            <p className="text-xs text-muted-foreground">
              {hasActiveExecutionFilters
                ? `${expandedExecutionTotal} executions match the current filters.`
                : 'Open the case page to organize executions by Case Hash and launch compare.'}
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
                {visibleCaseExecutions.map((execution) => (
                  <TableRow key={execution.id}>
                    <TableCell className="align-top">
                      <Link
                        to={`/executions/${execution.id}`}
                        state={{ from: currentPath }}
                        className="inline-flex items-center gap-1 font-mono text-xs text-blue-600 hover:underline"
                      >
                        {execution.executionId}
                      </Link>
                    </TableCell>
                    <TableCell className="align-top">
                      <span
                        className="font-mono text-xs text-slate-700"
                        title={execution.caseHash ?? MISSING_CASE_HASH_LABEL}
                      >
                        {formatCaseHashLabel(execution.caseHash ?? null)}
                      </span>
                    </TableCell>
                    <TableCell className="align-top">
                      {`${formatModelDate(execution.simulationStartDate)} → ${formatModelDate(
                        execution.simulationEndDate ?? null,
                      )}`}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </div>
        {expandedExecutionTotal > 25 && (
          <div className="flex max-w-4xl items-center justify-end gap-2 text-sm">
            <Button
              variant="outline"
              size="sm"
              disabled={expandedExecutionPage <= 1}
              onClick={() => setExpandedExecutionPage((page) => Math.max(1, page - 1))}
            >
              Previous executions
            </Button>
            <span>
              Page {expandedExecutionPage} of {expandedExecutionPageCount}
            </span>
            <Button
              variant="outline"
              size="sm"
              disabled={expandedExecutionPage >= expandedExecutionPageCount}
              onClick={() =>
                setExpandedExecutionPage((page) => Math.min(expandedExecutionPageCount, page + 1))
              }
            >
              Next executions
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
                  Find the cases behind your executions. Start with HPC username or machine, then
                  refine by campaign, version context, and case metadata.
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
                  Executions on page
                </p>
                <p className="mt-3 text-2xl font-semibold tracking-tight text-slate-950">
                  {visibleRunCount}
                </p>
                <p className="mt-1 text-xs text-slate-500">total executions across visible cases</p>
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
                    value: executionFilters.hpcUsername,
                    placeholder: 'All HPC usernames',
                    options: hpcUsernameOptions,
                    onValueChange: (value) => setExecutionFilter('hpcUsername', value),
                  })}

                  {renderSelectField({
                    label: 'Machine',
                    value: executionFilters.machineId,
                    placeholder: 'All machines',
                    options: machineOptions,
                    onValueChange: (value) => setExecutionFilter('machineId', value),
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
                        <p className="text-sm font-medium text-slate-900">Execution context</p>
                        <p className="text-xs text-slate-500">
                          Filter cases by the metadata attached to the executions inside them.
                        </p>
                      </div>
                      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
                        {renderSelectField({
                          label: 'Campaign',
                          value: executionFilters.campaign,
                          placeholder: 'All campaigns',
                          options: campaignOptions,
                          onValueChange: (value) => setExecutionFilter('campaign', value),
                        })}
                        {renderSelectField({
                          label: 'Type',
                          value: executionFilters.simulationType,
                          placeholder: 'All types',
                          options: simulationTypeOptions,
                          onValueChange: (value) => setExecutionFilter('simulationType', value),
                        })}
                        {renderSelectField({
                          label: 'Initialization',
                          value: executionFilters.initializationType,
                          placeholder: 'All init types',
                          options: initializationTypeOptions,
                          onValueChange: (value) =>
                            setExecutionFilter('initializationType', value),
                        })}
                        {renderSelectField({
                          label: 'Compiler',
                          value: executionFilters.compiler,
                          placeholder: 'All compilers',
                          options: compilerOptions,
                          onValueChange: (value) => setExecutionFilter('compiler', value),
                        })}
                        {renderSelectField({
                          label: 'Tag',
                          value: executionFilters.gitTag,
                          placeholder: 'All tags',
                          options: gitTagOptions,
                          onValueChange: (value) => setExecutionFilter('gitTag', value),
                        })}
                        {renderSelectField({
                          label: 'Creator',
                          value: executionFilters.createdBy,
                          placeholder: 'All creators',
                          options: creatorOptions,
                          onValueChange: (value) => setExecutionFilter('createdBy', value),
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
                          options: caseGroupOptions,
                          onValueChange: (value) => {
                            setCaseGroupFilter(value);
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
