import type { ColumnDef, SortingState } from '@tanstack/react-table';
import { flexRender, getCoreRowModel, useReactTable } from '@tanstack/react-table';
import { ChevronDown, ChevronRight, Copy, Search, SlidersHorizontal, X } from 'lucide-react';
import { Fragment, useEffect, useMemo, useRef, useState } from 'react';
import { Link, useLocation, useSearchParams } from 'react-router-dom';

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
import { toast } from '@/hooks/use-toast';
import { useCaseFilterOptions } from '@/lib/catalog/hooks/useCaseFilterOptions';
import { useCases } from '@/lib/catalog/hooks/useCases';
import { useExecutions } from '@/lib/catalog/hooks/useExecutions';
import { caseDetailsPath, executionDetailsPath } from '@/lib/catalog/urls';
import { cn } from '@/lib/utils';
import type { CaseListItemOut, ExecutionListItemOut } from '@/types';
import { formatModelDate } from '@/utils/utils';

type ActiveFilterKey =
  | 'caseName'
  | 'hpcUsername'
  | 'machineName'
  | 'campaign'
  | 'simulationType'
  | 'initializationType'
  | 'compiler'
  | 'gitTag'
  | 'caseGroup';

interface CaseExecutionFilters {
  hpcUsername: string;
  machineName: string;
  campaign: string;
  simulationType: string;
  initializationType: string;
  compiler: string;
  gitTag: string;
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
  machineName: '',
  campaign: '',
  simulationType: '',
  initializationType: '',
  compiler: '',
  gitTag: '',
});

const CASE_SORT_FIELDS: Record<string, string> = {
  latestRun: 'latest_run_activity',
  name: 'name',
  hpcUsers: 'hpc_username',
  machines: 'machine_name',
  executionCount: 'execution_count',
  caseGroup: 'case_group',
};

const DEFAULT_SORTING: SortingState = [{ id: 'latestRun', desc: true }];
const DEFAULT_PAGE_SIZE = 25;
const PAGE_SIZE_OPTIONS = [10, 25, 50, 100];
const CASE_SEARCH_PARAM_KEYS = [
  'search',
  'caseGroup',
  'machine',
  'machineId',
  'hpcUsername',
  'campaign',
  'simulationType',
  'initializationType',
  'compiler',
  'gitTag',
  'sortBy',
  'sortOrder',
  'page',
  'pageSize',
] as const;

interface CaseSearchState {
  caseNameFilter: string;
  caseGroupFilter: string;
  executionFilters: CaseExecutionFilters;
  legacyMachineId: string;
  sorting: SortingState;
  pagination: { pageIndex: number; pageSize: number };
}

const getTextParam = (params: URLSearchParams, key: string): string =>
  params.get(key)?.trim() ?? '';

const parsePositiveInteger = (value: string | null, fallback: number): number => {
  const parsed = Number(value);
  return Number.isInteger(parsed) && parsed > 0 ? parsed : fallback;
};

const parseCaseSearchState = (params: URLSearchParams): CaseSearchState => {
  const sortBy = params.get('sortBy');
  const sortOrder = params.get('sortOrder');
  const pageSize = parsePositiveInteger(params.get('pageSize'), DEFAULT_PAGE_SIZE);

  return {
    caseNameFilter: getTextParam(params, 'search'),
    caseGroupFilter: getTextParam(params, 'caseGroup'),
    executionFilters: {
      hpcUsername: getTextParam(params, 'hpcUsername'),
      machineName: getTextParam(params, 'machine'),
      campaign: getTextParam(params, 'campaign'),
      simulationType: getTextParam(params, 'simulationType'),
      initializationType: getTextParam(params, 'initializationType'),
      compiler: getTextParam(params, 'compiler'),
      gitTag: getTextParam(params, 'gitTag'),
    },
    legacyMachineId: getTextParam(params, 'machineId'),
    sorting:
      sortBy &&
      Object.prototype.hasOwnProperty.call(CASE_SORT_FIELDS, sortBy) &&
      (sortOrder === 'asc' || sortOrder === 'desc')
        ? [{ id: sortBy, desc: sortOrder === 'desc' }]
        : DEFAULT_SORTING,
    pagination: {
      pageIndex: parsePositiveInteger(params.get('page'), 1) - 1,
      pageSize: PAGE_SIZE_OPTIONS.includes(pageSize) ? pageSize : DEFAULT_PAGE_SIZE,
    },
  };
};

const serializeCaseSearchState = ({
  caseNameFilter,
  caseGroupFilter,
  executionFilters,
  legacyMachineId,
  sorting,
  pagination,
}: CaseSearchState): URLSearchParams => {
  const params = new URLSearchParams();
  const search = caseNameFilter.trim();

  if (search) params.set('search', search);
  if (caseGroupFilter) params.set('caseGroup', caseGroupFilter);

  if (executionFilters.machineName) params.set('machine', executionFilters.machineName);
  else if (legacyMachineId) params.set('machineId', legacyMachineId);

  (Object.entries(executionFilters) as [keyof CaseExecutionFilters, string][]).forEach(
    ([key, value]) => {
      if (key !== 'machineName' && value) params.set(key, value);
    },
  );

  const primarySort = sorting[0];
  if (primarySort && !(primarySort.id === 'latestRun' && primarySort.desc)) {
    params.set('sortBy', primarySort.id);
    params.set('sortOrder', primarySort.desc ? 'desc' : 'asc');
  }
  if (pagination.pageIndex > 0) params.set('page', String(pagination.pageIndex + 1));
  if (pagination.pageSize !== DEFAULT_PAGE_SIZE)
    params.set('pageSize', String(pagination.pageSize));

  return params;
};

const getLatestExecution = (caseRecord: CaseListItemOut) => caseRecord.latestExecution;

const formatLatestCompletedRun = (runEndDate: string | null) =>
  runEndDate ? formatCaseDate(runEndDate) : null;

const formatRunDateRange = (runStartDate: string | null, runEndDate: string | null) => {
  if (!runStartDate && !runEndDate) return null;

  return `${formatCaseDate(runStartDate)} → ${formatCaseDate(runEndDate)}`;
};

const UnavailableTimestamp = () => (
  <span
    title="Run timestamps are not available for this execution."
    aria-label="Run timestamps unavailable"
  >
    —
  </span>
);

export const CasesPage = () => {
  const location = useLocation();
  const [searchParams, setSearchParams] = useSearchParams();
  const [initialSearchState] = useState(() => parseCaseSearchState(searchParams));
  const isApplyingUrlState = useRef(false);
  const currentPath = `${location.pathname}${location.search}`;

  const [caseNameFilter, setCaseNameFilter] = useState(initialSearchState.caseNameFilter);
  const [debouncedCaseName, setDebouncedCaseName] = useState(initialSearchState.caseNameFilter);
  const [caseGroupFilter, setCaseGroupFilter] = useState(initialSearchState.caseGroupFilter);
  const [executionFilters, setExecutionFilters] = useState<CaseExecutionFilters>(
    initialSearchState.executionFilters,
  );
  const [legacyMachineId, setLegacyMachineId] = useState(initialSearchState.legacyMachineId);
  const [showAdvancedFilters, setShowAdvancedFilters] = useState(() =>
    [
      initialSearchState.caseGroupFilter,
      initialSearchState.executionFilters.campaign,
      initialSearchState.executionFilters.simulationType,
      initialSearchState.executionFilters.initializationType,
      initialSearchState.executionFilters.compiler,
      initialSearchState.executionFilters.gitTag,
    ].some(Boolean),
  );
  const [expandedCaseId, setExpandedCaseId] = useState<string | null>(null);
  const requiresMachineLookup = Boolean(executionFilters.machineName || legacyMachineId);
  const { data: allFilterOptions } = useCaseFilterOptions({}, requiresMachineLookup);
  const allMachineOptions = useMemo(() => allFilterOptions?.machines ?? [], [allFilterOptions]);
  const selectedMachineId =
    allMachineOptions.find((option) => option.label === executionFilters.machineName)?.value ||
    legacyMachineId ||
    undefined;
  const caseFilterOptionParams = useMemo(
    () => ({
      search: debouncedCaseName || undefined,
      caseGroup: caseGroupFilter || undefined,
      machineId: selectedMachineId,
      hpcUsername: executionFilters.hpcUsername || undefined,
      simulationType: executionFilters.simulationType || undefined,
      campaign: executionFilters.campaign || undefined,
      initializationType: executionFilters.initializationType || undefined,
      compiler: executionFilters.compiler || undefined,
      gitTag: executionFilters.gitTag || undefined,
    }),
    [caseGroupFilter, debouncedCaseName, executionFilters, selectedMachineId],
  );
  const { data: filterOptions } = useCaseFilterOptions(caseFilterOptionParams);
  const {
    data: executions,
    page: expandedExecutionPage,
    isFetching: expandedExecutionsFetching,
  } = useExecutions(
    {
      caseId: expandedCaseId ?? undefined,
      page: 1,
      pageSize: 5,
      sortBy: 'run_activity',
      sortOrder: 'desc',
      hpcUsername: executionFilters.hpcUsername || undefined,
      machineId: selectedMachineId,
      campaign: executionFilters.campaign || undefined,
      simulationType: executionFilters.simulationType || undefined,
      initializationType: executionFilters.initializationType || undefined,
      compiler: executionFilters.compiler || undefined,
      gitTag: executionFilters.gitTag || undefined,
    },
    expandedCaseId != null,
  );
  const [sorting, setSorting] = useState<SortingState>(initialSearchState.sorting);
  const [pagination, setPagination] = useState(initialSearchState.pagination);
  const canonicalSearchParams = useMemo(
    () =>
      serializeCaseSearchState({
        caseNameFilter: debouncedCaseName,
        caseGroupFilter,
        executionFilters,
        legacyMachineId,
        sorting,
        pagination,
      }),
    [caseGroupFilter, debouncedCaseName, executionFilters, legacyMachineId, pagination, sorting],
  );

  useEffect(() => {
    const next = parseCaseSearchState(searchParams);
    const canonicalParams = serializeCaseSearchState(next);
    const normalizedParams = new URLSearchParams(searchParams);
    CASE_SEARCH_PARAM_KEYS.forEach((key) => normalizedParams.delete(key));
    canonicalParams.forEach((value, key) => normalizedParams.set(key, value));

    isApplyingUrlState.current = true;
    setCaseNameFilter(next.caseNameFilter);
    setDebouncedCaseName(next.caseNameFilter);
    setCaseGroupFilter(next.caseGroupFilter);
    setExecutionFilters(next.executionFilters);
    setLegacyMachineId(next.legacyMachineId);
    setSorting(next.sorting);
    setPagination(next.pagination);
    setShowAdvancedFilters(
      [
        next.caseGroupFilter,
        next.executionFilters.campaign,
        next.executionFilters.simulationType,
        next.executionFilters.initializationType,
        next.executionFilters.compiler,
        next.executionFilters.gitTag,
      ].some(Boolean),
    );

    if (normalizedParams.toString() !== searchParams.toString()) {
      setSearchParams(normalizedParams, { replace: true });
    }
  }, [searchParams, setSearchParams]);

  useEffect(() => {
    if (!legacyMachineId || executionFilters.machineName) return;

    const legacyMachine = allMachineOptions.find((option) => option.value === legacyMachineId);
    if (!legacyMachine) return;

    setExecutionFilters((current) => ({ ...current, machineName: legacyMachine.label }));
    setLegacyMachineId('');
  }, [allMachineOptions, executionFilters.machineName, legacyMachineId]);

  useEffect(() => {
    const timeout = window.setTimeout(() => setDebouncedCaseName(caseNameFilter.trim()), 300);
    return () => window.clearTimeout(timeout);
  }, [caseNameFilter]);

  useEffect(() => {
    if (isApplyingUrlState.current) {
      isApplyingUrlState.current = false;
      return;
    }

    setSearchParams(
      (previous) => {
        const next = new URLSearchParams(previous);
        CASE_SEARCH_PARAM_KEYS.forEach((key) => next.delete(key));
        canonicalSearchParams.forEach((value, key) => next.set(key, value));
        return next.toString() === previous.toString() ? previous : next;
      },
      { replace: true },
    );
  }, [canonicalSearchParams, setSearchParams]);
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
    machineId: selectedMachineId,
    campaign: executionFilters.campaign || undefined,
    simulationType: executionFilters.simulationType || undefined,
    initializationType: executionFilters.initializationType || undefined,
    compiler: executionFilters.compiler || undefined,
    gitTag: executionFilters.gitTag || undefined,
    sortBy: primarySort ? CASE_SORT_FIELDS[primarySort.id] : 'latest_run_activity',
    sortOrder: primarySort?.desc === false ? 'asc' : 'desc',
  });

  useEffect(() => {
    if (!casePage) return;

    const lastPageIndex = Math.max(0, Math.ceil(casePage.total / pagination.pageSize) - 1);
    setPagination((current) =>
      current.pageIndex > lastPageIndex ? { ...current, pageIndex: lastPageIndex } : current,
    );
  }, [casePage, pagination.pageSize]);

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
      machineOptions: (filterOptions?.machines ?? []).map((machine) => ({
        value: machine.label,
        label: machine.label,
      })),
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
        executionFilters.campaign,
        executionFilters.simulationType,
        executionFilters.initializationType,
        executionFilters.compiler,
        executionFilters.gitTag,
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

    if (executionFilters.machineName) {
      filters.push({
        key: 'machineName',
        label: 'Machine',
        value: executionFilters.machineName,
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

    if (caseGroupFilter) filters.push({ key: 'caseGroup', label: 'Group', value: caseGroupFilter });

    return filters;
  }, [caseGroupFilter, caseNameFilter, executionFilters]);

  const setExecutionFilter = (key: keyof CaseExecutionFilters, value: string) => {
    setExecutionFilters((current) => ({
      ...current,
      [key]: value,
    }));
    if (key === 'machineName') setLegacyMachineId('');
    table.setPageIndex(0);
  };

  const clearAllFilters = () => {
    setCaseNameFilter('');
    setCaseGroupFilter('');
    setExecutionFilters(createEmptyExecutionFilters());
    setLegacyMachineId('');
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
        if (filterKey === 'machineName') setLegacyMachineId('');
        break;
    }

    table.setPageIndex(0);
  };

  const handleCopySearch = async () => {
    const query = canonicalSearchParams.toString();
    const searchUrl = new URL(
      `${location.pathname}${query ? `?${query}` : ''}`,
      window.location.origin,
    ).toString();

    try {
      await navigator.clipboard.writeText(searchUrl);
      toast({
        title: 'Search link copied',
        description: 'This link restores the current case search.',
      });
    } catch {
      toast({
        title: 'Unable to copy search link',
        description: 'Copy the URL from your browser instead.',
        variant: 'destructive',
      });
    }
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
          <div className="min-w-[14rem] max-w-[28rem]">
            <Link
              to={caseDetailsPath({
                machineName: row.original.machineName,
                hpcUsername: row.original.hpcUsername,
                caseName: row.original.name,
              })}
              state={{ from: currentPath }}
              className="block truncate font-medium text-blue-600 hover:underline focus-visible:rounded-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
              title={row.original.name}
              onClick={(event) => event.stopPropagation()}
            >
              {row.original.name}
            </Link>
            {row.original.caseGroup && (
              <button
                type="button"
                className="mt-1 max-w-full truncate text-left text-xs text-slate-500 hover:text-blue-600 hover:underline"
                title={`Filter by case group: ${row.original.caseGroup}`}
                onClick={(event) => {
                  event.stopPropagation();
                  setCaseGroupFilter(row.original.caseGroup ?? '');
                  setPagination((current) => ({ ...current, pageIndex: 0 }));
                }}
              >
                Group: {row.original.caseGroup}
              </button>
            )}
          </div>
        ),
      },
      {
        id: 'latestRun',
        header: 'Latest completed run',
        cell: ({ row }) => {
          const latestExecution = getLatestExecution(row.original);
          const completedRun = latestExecution
            ? formatLatestCompletedRun(latestExecution.runEndDate)
            : null;

          return (
            <div className="min-w-[10rem] text-sm text-slate-600">
              {completedRun ?? <UnavailableTimestamp />}
            </div>
          );
        },
      },
      {
        id: 'machines',
        header: 'Machines',
        accessorFn: (caseRecord) => caseRecord.machineName,
        cell: ({ row }) => <TableCellText value={row.original.machineName} lines={1} />,
      },
      {
        id: 'hpcUsers',
        header: 'HPC Users',
        accessorFn: (caseRecord) => caseRecord.hpcUsername,
        cell: ({ row }) => <TableCellText value={row.original.hpcUsername} lines={1} />,
      },
      {
        id: 'executionCount',
        header: 'Total Executions',
        accessorFn: (caseRecord) => caseRecord.executionCount,
        cell: ({ row }) => {
          return <Badge variant="secondary">{row.original.executionCount}</Badge>;
        },
      },
    ],
    [currentPath, expandedCaseId],
  );

  const table = useReactTable({
    data: filteredCases,
    columns,
    state: { sorting, pagination },
    onSortingChange: (updater) => {
      setSorting(updater);
      setPagination((current) => ({ ...current, pageIndex: 0 }));
    },
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
  }) => {
    const optionsWithSelection =
      value && !options.some((option) => option.value === value)
        ? [{ value, label: value }, ...options]
        : options;

    return (
      <div className="space-y-2">
        <label className="text-xs font-medium uppercase tracking-[0.12em] text-slate-500">
          {label}
        </label>
        <SearchableFilterSelect
          label={label}
          value={value}
          placeholder={placeholder}
          options={optionsWithSelection}
          onValueChange={onValueChange}
        />
      </div>
    );
  };

  const renderExpandedContent = (caseRecord: CaseListItemOut) => {
    const visibleCaseExecutions = executionsByCaseId.get(caseRecord.id) ?? [];
    const expandedExecutionLabel = hasActiveExecutionFilters
      ? expandedExecutionsFetching || !expandedExecutionPage
        ? 'View matching executions on the case details page'
        : `View all ${expandedExecutionPage.total} executions on the case details page`
      : `View all ${caseRecord.executionCount} executions on the case details page`;
    return (
      <div className="mx-3 my-3 space-y-2 rounded-xl border border-slate-200 bg-slate-50/80 p-3 shadow-sm sm:ml-12">
        <div>
          <p className="text-sm font-medium">Latest executions</p>
          <p className="text-xs text-muted-foreground">
            {hasActiveExecutionFilters
              ? 'Matching current execution filters.'
              : 'Five most recent runs by run date.'}
          </p>
        </div>

        <div className="overflow-hidden rounded-lg border border-slate-200 bg-background">
          <div className="max-h-[20rem] overflow-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Run dates (latest first)</TableHead>
                  <TableHead>Execution ID</TableHead>
                  <TableHead>Case Hash</TableHead>
                  <TableHead>Simulation dates</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {visibleCaseExecutions.map((execution) => (
                  <TableRow key={execution.id}>
                    <TableCell className="py-2 align-top text-xs text-slate-600">
                      {formatRunDateRange(execution.runStartDate, execution.runEndDate) ?? (
                        <UnavailableTimestamp />
                      )}
                    </TableCell>
                    <TableCell className="py-2 align-top">
                      <Link
                        to={executionDetailsPath({
                          machineName: execution.machineName,
                          hpcUsername: execution.hpcUsername,
                          caseName: execution.caseName,
                          executionId: execution.executionId,
                        })}
                        state={{ from: currentPath }}
                        className="inline-flex items-center gap-1 font-mono text-xs text-blue-600 hover:underline"
                      >
                        {execution.executionId}
                      </Link>
                    </TableCell>
                    <TableCell className="py-2 align-top">
                      <span
                        className="font-mono text-xs text-slate-700"
                        title={execution.caseHash ?? MISSING_CASE_HASH_LABEL}
                      >
                        {formatCaseHashLabel(execution.caseHash ?? null)}
                      </span>
                    </TableCell>
                    <TableCell className="py-2 align-top text-xs text-slate-600">
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

        <div className="flex justify-end pt-1">
          <Button variant="outline" size="sm" asChild>
            <Link
              to={caseDetailsPath({
                machineName: caseRecord.machineName,
                hpcUsername: caseRecord.hpcUsername,
                caseName: caseRecord.name,
              })}
              state={{ from: currentPath }}
            >
              {expandedExecutionLabel}
            </Link>
          </Button>
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
                  Find cases and their execution context. Search case names, then refine by run or
                  case metadata.
                </p>
              </div>
            </div>

            <div className="rounded-xl border border-slate-200 bg-white/75 px-4 py-3 text-sm text-slate-600 shadow-sm shadow-slate-200/20">
              <span className="font-medium text-slate-900">{casePage?.total ?? 0} cases</span>
              <span className="px-2 text-slate-300">·</span>
              <span>{visibleRunCount} runs on this page</span>
              {activeFilterPills.length > 0 && (
                <>
                  <span className="px-2 text-slate-300">·</span>
                  <span>{activeFilterPills.length} active filters</span>
                </>
              )}
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
                    label: 'Machine',
                    value: executionFilters.machineName,
                    placeholder: 'All machines',
                    options: machineOptions,
                    onValueChange: (value) => setExecutionFilter('machineName', value),
                  })}

                  {renderSelectField({
                    label: 'HPC Username',
                    value: executionFilters.hpcUsername,
                    placeholder: 'All HPC usernames',
                    options: hpcUsernameOptions,
                    onValueChange: (value) => setExecutionFilter('hpcUsername', value),
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
                    variant="outline"
                    type="button"
                    onClick={() => void handleCopySearch()}
                    disabled={canonicalSearchParams.size === 0}
                    className="h-10 rounded-xl border-slate-200 bg-white px-4 text-slate-700 shadow-none hover:bg-slate-50"
                    aria-label="Copy search link"
                  >
                    <Copy className="mr-2 h-4 w-4" />
                    Copy search
                  </Button>
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
                          Shows cases with at least one execution matching these filters.
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
                          onValueChange: (value) => setExecutionFilter('initializationType', value),
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
                      </div>
                    </div>

                    <div className="space-y-4 rounded-2xl border border-slate-200 bg-slate-50/80 p-4">
                      <div className="space-y-1">
                        <p className="text-sm font-medium text-slate-900">Case metadata</p>
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
                        <TableRow className="bg-slate-50/40 hover:bg-slate-50/40">
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
