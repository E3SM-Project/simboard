import { TooltipProvider } from '@radix-ui/react-tooltip';
import type { SortingState, VisibilityState } from '@tanstack/react-table';
import { ChevronDown, LayoutGrid, Table } from 'lucide-react';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';

import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import { BrowseFiltersSidePanel } from '@/features/browse/components/BrowseFiltersSidePanel';
import { SimulationResultCards } from '@/features/browse/components/SimulationResults/SimulationResultsCards';
import { SimulationResultsTable } from '@/features/browse/components/SimulationResults/SimulationResultsTable';
import { useSimulationFilterOptions } from '@/lib/catalog/hooks/useSimulationFilterOptions';
import { useSimulations } from '@/lib/catalog/hooks/useSimulations';

const PAGE_SIZE_OPTIONS = [10, 25, 50, 100];
const DEFAULT_COLUMN_VISIBILITY: VisibilityState = {
  ensembleMember: false,
  gridResolution: false,
  gridName: false,
  compset: false,
};
const TOGGLEABLE_BROWSE_COLUMNS = [
  { id: 'ensembleMember', label: 'Ensemble member' },
  { id: 'gridResolution', label: 'Grid resolution' },
  { id: 'gridName', label: 'Grid name' },
  { id: 'compset', label: 'Component set' },
] as const;
const BROWSE_SORT_FIELDS: Record<string, string> = {
  caseName: 'case_name',
  executionId: 'execution_id',
  caseHash: 'case_hash',
  campaign: 'campaign',
  experimentType: 'experiment_type',
  gitTag: 'git_tag',
  simulationStartDate: 'simulation_start_date',
  simulationEndDate: 'simulation_end_date',
  gridResolution: 'grid_resolution',
  compset: 'compset',
  gridName: 'grid_name',
};

// -------------------- Types & Interfaces --------------------
export interface FilterState {
  caseName: string[];

  // Scientific Goal
  campaign: string[];
  experimentType: string[];
  simulationType: string[];
  initializationType: string[];

  // Simulation Context
  compset: string[];
  gridName: string[];
  gridResolution: string[];

  // Execution Details
  machineId: string[];
  compiler: string[];
  status: string[];

  // Metadata & Provenance
  gitTag: string[];
  createdBy: string[];
  hpcUsername: string[];
}

interface BrowsePageProps {
  selectedSimulationIds: string[];
  setSelectedSimulationIds: (ids: string[]) => void;
}

// -------------------- Pure Helpers --------------------
const createEmptyFilters = (): FilterState => ({
  caseName: [],

  // Scientific Goal
  campaign: [],
  experimentType: [],
  simulationType: [],
  initializationType: [],

  // Simulation Context
  compset: [],
  gridName: [],
  gridResolution: [],

  // Execution Details
  machineId: [],
  compiler: [],
  status: [],

  // Metadata & Provenance
  gitTag: [],
  createdBy: [],
  hpcUsername: [],
});

const FILTER_KEYS = Object.keys(createEmptyFilters()) as (keyof FilterState)[];
const MULTI_SELECT_FILTER_KEYS = FILTER_KEYS;

const areStringArraysEqual = (left: string[], right: string[]): boolean =>
  left.length === right.length && left.every((value, index) => value === right[index]);

const areFiltersEqual = (left: FilterState, right: FilterState): boolean =>
  MULTI_SELECT_FILTER_KEYS.every((key) =>
    areStringArraysEqual(left[key] as string[], right[key] as string[]),
  );

const parseViewMode = (params: URLSearchParams): 'grid' | 'table' =>
  params.get('view') === 'grid' ? 'grid' : 'table';

const parsePage = (params: URLSearchParams): number => {
  const p = Number(params.get('page'));
  if (!Number.isFinite(p) || p < 1) {
    return 1;
  }

  return Math.floor(p);
};

const parsePageSize = (params: URLSearchParams): number => {
  const ps = Number(params.get('pageSize'));
  return PAGE_SIZE_OPTIONS.includes(ps) ? ps : 25;
};

const decodeFilterValue = (value: string): string => {
  try {
    return decodeURIComponent(value);
  } catch {
    return value;
  }
};

const deserializeArrayFilter = (value: string): string[] =>
  value.split(',').filter(Boolean).map(decodeFilterValue);

const serializeArrayFilter = (values: string[]): string =>
  values.map((value) => encodeURIComponent(value)).join(',');

export const BrowsePage = ({
  selectedSimulationIds,
  setSelectedSimulationIds,
}: BrowsePageProps) => {
  // -------------------- Router --------------------
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();

  // -------------------- Local State --------------------
  const [appliedFilters, setAppliedFilters] = useState<FilterState>(createEmptyFilters);

  const [viewMode, setViewMode] = useState<'grid' | 'table'>(() => parseViewMode(searchParams));
  const [page, setPage] = useState(() => parsePage(searchParams));
  const [pageSize, setPageSize] = useState(() => parsePageSize(searchParams));
  const [sorting, setSorting] = useState<SortingState>([]);
  const [columnVisibility, setColumnVisibility] =
    useState<VisibilityState>(DEFAULT_COLUMN_VISIBILITY);

  // -------------------- Derived Data --------------------
  const { data: filterOptions } = useSimulationFilterOptions();
  const primarySort = sorting[0];
  const simulationParams = useMemo(
    () => ({
      page,
      pageSize,
      ...Object.fromEntries(
        FILTER_KEYS.map((key) => [key, appliedFilters[key].length ? appliedFilters[key] : undefined]),
      ),
      sortBy: primarySort ? BROWSE_SORT_FIELDS[primarySort.id] : 'created_at',
      sortOrder: primarySort?.desc === false ? ('asc' as const) : ('desc' as const),
    }),
    [appliedFilters, page, pageSize, primarySort],
  );
  const {
    data: simulations,
    page: simulationPage,
    loading,
    error,
    refetch,
  } = useSimulations(simulationParams);
  const totalItems = simulationPage?.total ?? 0;
  const availableFilters = useMemo<FilterState>(
    () => ({
      caseName: filterOptions?.caseNames ?? [],
      campaign: filterOptions?.campaigns ?? [],
      experimentType: filterOptions?.experimentTypes ?? [],
      simulationType: filterOptions?.simulationTypes ?? [],
      initializationType: filterOptions?.initializationTypes ?? [],
      compset: filterOptions?.compsets ?? [],
      gridName: filterOptions?.gridNames ?? [],
      gridResolution: filterOptions?.gridResolutions ?? [],
      machineId: filterOptions?.machineIds ?? [],
      compiler: filterOptions?.compilers ?? [],
      status: filterOptions?.statuses ?? [],
      gitTag: filterOptions?.gitTags ?? [],
      createdBy: filterOptions?.createdByIds ?? [],
      hpcUsername: filterOptions?.hpcUsernames ?? [],
    }),
    [filterOptions],
  );
  const machineOptions = filterOptions?.machines ?? [];
  const creatorOptions = filterOptions?.creators ?? [];
  const caseOptions = useMemo(
    () => availableFilters.caseName.map((name) => ({ value: name, label: name })),
    [availableFilters.caseName],
  );

  // -------------------- Effects --------------------
  useEffect(() => {
    const next = createEmptyFilters();

    MULTI_SELECT_FILTER_KEYS.forEach((key) => {
      const value = searchParams.get(key);
      if (value !== null) {
        next[key] = deserializeArrayFilter(value) as FilterState[typeof key];
      }
    });

    setAppliedFilters((current) => (areFiltersEqual(current, next) ? current : next));

    // Sync view, page, pageSize from URL (handles back/forward navigation).
    setViewMode(parseViewMode(searchParams));
    setPage(parsePage(searchParams));
    setPageSize(parsePageSize(searchParams));
  }, [searchParams]);

  // Reset page to 1 when filters/case change (skip the initial URL→state sync).
  const prevPageResetSignature = useRef<string | null>(null);
  useEffect(() => {
    const currentSignature = JSON.stringify({
      appliedFilters,
      sorting,
    });

    if (prevPageResetSignature.current === null) {
      // First render — record reference without resetting page.
      prevPageResetSignature.current = currentSignature;
      return;
    }

    if (prevPageResetSignature.current !== currentSignature) {
      prevPageResetSignature.current = currentSignature;
      setPage(1);
    }
  }, [appliedFilters, sorting]);

  // Sync applied filters to URL via setSearchParams (single writer).
  // Use a ref to avoid re-running this effect on every searchParams change.
  const isInitialFilterSync = useRef(true);
  const skipNextFilterUrlSync = useRef(false);
  useEffect(() => {
    // Skip the initial render — filters are read FROM the URL on mount.
    if (isInitialFilterSync.current) {
      isInitialFilterSync.current = false;
      return;
    }

    if (skipNextFilterUrlSync.current) {
      skipNextFilterUrlSync.current = false;
      return;
    }

    setSearchParams(
      (prev) => {
        const next = new URLSearchParams(prev);

        for (const key of FILTER_KEYS) {
          const value = appliedFilters[key];
          if (Array.isArray(value) && value.length) {
            next.set(key, serializeArrayFilter(value));
          } else if (typeof value === 'string' && value) {
            next.set(key, value);
          } else {
            next.delete(key);
          }
        }

        if (viewMode === 'grid') {
          next.set('view', 'grid');
        } else {
          next.delete('view');
        }
        if (page > 1) {
          next.set('page', String(page));
        } else {
          next.delete('page');
        }
        if (pageSize !== 25) {
          next.set('pageSize', String(pageSize));
        } else {
          next.delete('pageSize');
        }

        return next;
      },
      { replace: true },
    );
  }, [appliedFilters, viewMode, page, pageSize, setSearchParams]);

  // -------------------- Handlers --------------------
  const handleResetFilters = () => {
    skipNextFilterUrlSync.current = true;
    setAppliedFilters(createEmptyFilters());
    setSearchParams(
      (prev) => {
        const next = new URLSearchParams(prev);

        FILTER_KEYS.forEach((key) => {
          next.delete(key);
        });

        next.delete('page');
        return next;
      },
      { replace: true },
    );
  };

  const handleCompareButtonClick = () => {
    navigate('/compare');
  };

  const handlePageSizeChange = useCallback((newSize: string) => {
    setPageSize(Number(newSize));
    setPage(1);
  }, []);

  // -------------------- Pagination --------------------
  const totalPages = Math.max(1, Math.ceil(totalItems / pageSize));

  // Clamp page state when totalPages shrinks (e.g. after filtering).
  useEffect(() => {
    setPage((p) => (p > totalPages ? totalPages : p));
  }, [totalPages]);

  if (loading) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center text-slate-500">
        Loading runs…
      </div>
    );
  }

  if (error && !simulationPage) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center px-6">
        <div className="space-y-3 text-center">
          <p className="text-red-600">Could not load runs: {error}</p>
          <Button type="button" variant="outline" onClick={() => void refetch()}>
            Retry
          </Button>
        </div>
      </div>
    );
  }

  // -------------------- Render --------------------
  return (
    <div className="w-full bg-white">
      <div className="mx-auto w-full max-w-[2200px] px-4 py-6 sm:px-6 lg:px-8 xl:px-10 2xl:px-12">
        {error ? (
          <div className="mb-4 flex items-center justify-between gap-3 rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700">
            <span>Could not refresh runs: {error}</span>
            <Button type="button" variant="outline" size="sm" onClick={() => void refetch()}>
              Retry
            </Button>
          </div>
        ) : null}

        <div className="grid gap-6 lg:items-start lg:grid-cols-[clamp(300px,22vw,380px)_minmax(0,1fr)] xl:gap-8">
          <div className="min-w-0 lg:sticky lg:top-6 lg:h-[calc(100vh-3rem)] lg:self-start">
            <div className="lg:h-full lg:pr-2">
              <BrowseFiltersSidePanel
                appliedFilters={appliedFilters}
                availableFilters={availableFilters}
                onChange={setAppliedFilters}
                machineOptions={machineOptions}
                creatorOptions={creatorOptions}
                caseOptions={caseOptions}
              />
            </div>
          </div>
          <div className="min-w-0">
            <div className="flex min-w-0 flex-col">
              <header className="mb-4 flex flex-col gap-4 rounded-xl border border-slate-200 bg-white p-5 shadow-sm xl:flex-row xl:items-start xl:justify-between">
                <div className="min-w-0">
                  <h1 className="mb-2 text-3xl font-bold tracking-tight text-slate-950">Runs</h1>
                  <p className="max-w-4xl text-[15px] leading-7 text-slate-600 sm:text-base">
                    Explore and filter individual runs using the panel on the left. This is the
                    advanced execution-level workspace for drilling into details and setting up
                    cross-case compare across runs.
                  </p>
                </div>
                <div className="xl:min-w-[360px]">
                  <TooltipProvider delayDuration={150}>
                    <div className="flex flex-col gap-3 rounded-xl border border-slate-200 bg-slate-50/40 p-3">
                      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-slate-600">
                        <div>
                          <span className="font-medium text-slate-500">Results</span>{' '}
                          <span className="font-semibold text-slate-950">
                            {totalItems}
                          </span>
                        </div>
                        <div>
                          <span className="font-medium text-slate-500">View</span>{' '}
                          <span className="font-semibold text-slate-950">
                            {viewMode === 'grid' ? 'Cards' : 'Table'}
                          </span>
                        </div>
                      </div>

                      <div className="flex flex-wrap items-center justify-between gap-3">
                        <div>
                          {viewMode === 'table' && (
                            <DropdownMenu>
                              <DropdownMenuTrigger asChild>
                                <Button
                                  variant="outline"
                                  className="h-10 shrink-0 rounded-lg border-slate-200 bg-white text-slate-700 shadow-none hover:bg-slate-50"
                                >
                                  Columns <ChevronDown className="h-4 w-4" />
                                </Button>
                              </DropdownMenuTrigger>
                              <DropdownMenuContent align="start">
                                {TOGGLEABLE_BROWSE_COLUMNS.map((column) => (
                                  <DropdownMenuCheckboxItem
                                    key={column.id}
                                    className="capitalize"
                                    checked={columnVisibility[column.id] !== false}
                                    onCheckedChange={(checked) =>
                                      setColumnVisibility((prev) => ({
                                        ...prev,
                                        [column.id]: !!checked,
                                      }))
                                    }
                                  >
                                    {column.label}
                                  </DropdownMenuCheckboxItem>
                                ))}
                              </DropdownMenuContent>
                            </DropdownMenu>
                          )}
                        </div>
                        <div className="inline-flex shrink-0 w-fit items-center gap-1 rounded-lg border border-slate-200 bg-white p-1">
                          <Tooltip>
                            <TooltipTrigger asChild>
                              <button
                                aria-label="Table view"
                                className={`rounded-md border px-3 py-2 transition-colors ${
                                  viewMode === 'table'
                                    ? 'border-slate-300 bg-slate-100 text-slate-950 shadow-sm'
                                    : 'border-transparent text-slate-500 hover:bg-slate-50 hover:text-slate-900'
                                }`}
                                onClick={() => setViewMode('table')}
                              >
                                <Table size={24} strokeWidth={2} />
                              </button>
                            </TooltipTrigger>
                            <TooltipContent>Show simulations in a table</TooltipContent>
                          </Tooltip>
                          <Tooltip>
                            <TooltipTrigger asChild>
                              <button
                                aria-label="Grid view"
                                className={`rounded-md border px-3 py-2 transition-colors ${
                                  viewMode === 'grid'
                                    ? 'border-slate-300 bg-slate-100 text-slate-950 shadow-sm'
                                    : 'border-transparent text-slate-500 hover:bg-slate-50 hover:text-slate-900'
                                }`}
                                onClick={() => setViewMode('grid')}
                              >
                                <LayoutGrid size={24} strokeWidth={2} />
                              </button>
                            </TooltipTrigger>
                            <TooltipContent>Show simulations as cards</TooltipContent>
                          </Tooltip>
                        </div>
                      </div>
                    </div>
                  </TooltipProvider>
                </div>
              </header>

              {Object.values(appliedFilters).some((v) =>
                Array.isArray(v) ? v.length > 0 : !!v,
              ) && (
                <div className="mb-4 rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
                  <div className="mb-3 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                    <div>
                      <p className="text-sm font-semibold text-slate-900">Active filters</p>
                      <p className="text-xs text-slate-500">
                        Current query scope and faceted filters
                      </p>
                    </div>
                    <button
                      type="button"
                      className="inline-flex items-center rounded-md border border-red-200 bg-red-50 px-3 py-1.5 text-sm font-medium text-red-700 transition-colors hover:bg-red-100"
                      aria-label="Clear all filters"
                      onClick={handleResetFilters}
                    >
                      <span className="mr-2">Clear all</span>
                      <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
                        <path
                          d="M4 4L12 12M12 4L4 12"
                          stroke="currentColor"
                          strokeWidth="2"
                          strokeLinecap="round"
                        />
                      </svg>
                    </button>
                  </div>
                  <div className="flex min-w-0 flex-wrap gap-2">
                    {(
                      Object.entries(appliedFilters) as [keyof FilterState, string[] | string][]
                    ).flatMap(([key, values]) => {
                      if (Array.isArray(values)) {
                        return values.map((value, idx) => {
                          const display =
                            key === 'machineId'
                              ? (machineOptions.find((opt) => opt.value === value)?.label ?? value)
                              : key === 'createdBy'
                                ? (creatorOptions.find((opt) => opt.value === value)?.label ??
                                  value)
                                : value;
                          return (
                            <span
                              key={`${key}-${value}-${idx}`}
                              className="inline-flex min-w-0 max-w-full items-center rounded-md border border-slate-200 bg-slate-50 px-3 py-1.5 text-sm text-slate-700"
                            >
                              <span className="mr-2 shrink-0 text-xs font-medium text-slate-500">
                                {String(key).replace(/Id$/, '')}:
                              </span>
                              <span className="mr-2 min-w-0 flex-1 truncate font-medium text-slate-700">
                                {display}
                              </span>
                              <button
                                type="button"
                                aria-label={`Remove ${String(key)} filter`}
                                className="ml-1 shrink-0 rounded-sm text-slate-400 transition-colors hover:text-slate-700 focus:outline-none"
                                onClick={() => {
                                  setAppliedFilters((prev) => ({
                                    ...prev,
                                    [key]: (prev[key] as string[]).filter((v) => v !== value),
                                  }));
                                }}
                              >
                                <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                                  <path
                                    d="M4 4L12 12M12 4L4 12"
                                    stroke="currentColor"
                                    strokeWidth="2"
                                    strokeLinecap="round"
                                  />
                                </svg>
                              </button>
                            </span>
                          );
                        });
                      } else if (values) {
                        const display =
                          key === 'machineId'
                            ? (machineOptions.find((opt) => opt.value === values)?.label ?? values)
                            : key === 'createdBy'
                              ? (creatorOptions.find((opt) => opt.value === values)?.label ??
                                values)
                              : values;
                        return (
                          <span
                            key={`${String(key)}-${values}`}
                            className="inline-flex min-w-0 max-w-full items-center rounded-md border border-slate-200 bg-slate-50 px-3 py-1.5 text-sm text-slate-700"
                          >
                            <span className="mr-2 shrink-0 text-xs font-medium text-slate-500">
                              {String(key).replace(/Id$/, '')}:
                            </span>
                            <span className="mr-2 min-w-0 flex-1 truncate font-medium text-slate-700">
                              {display}
                            </span>
                            <button
                              type="button"
                              aria-label={`Remove ${String(key)} filter`}
                              className="ml-1 shrink-0 rounded-sm text-slate-400 transition-colors hover:text-slate-700 focus:outline-none"
                              onClick={() => {
                                setAppliedFilters((prev) => ({ ...prev, [key]: '' }));
                              }}
                            >
                              <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                                <path
                                  d="M4 4L12 12M12 4L4 12"
                                  stroke="currentColor"
                                  strokeWidth="2"
                                  strokeLinecap="round"
                                />
                              </svg>
                            </button>
                          </span>
                        );
                      }
                      return [];
                    })}
                  </div>
                </div>
              )}
              <div className="min-w-0">
                {viewMode === 'table' ? (
                  <SimulationResultsTable
                    simulations={simulations}
                    filteredData={simulations}
                    sorting={sorting}
                    setSorting={setSorting}
                    selectedSimulationIds={selectedSimulationIds}
                    setSelectedSimulationIds={setSelectedSimulationIds}
                    handleCompareButtonClick={handleCompareButtonClick}
                    columnVisibility={columnVisibility}
                    setColumnVisibility={setColumnVisibility}
                  />
                ) : (
                  <SimulationResultCards
                    simulations={simulations}
                    filteredData={simulations}
                    selectedSimulationIds={selectedSimulationIds}
                    setSelectedSimulationIds={setSelectedSimulationIds}
                    handleCompareButtonClick={handleCompareButtonClick}
                  />
                )}

                {/* Shared pagination controls */}
                <div className="flex flex-col gap-3 py-4 text-sm text-muted-foreground lg:flex-row lg:items-center lg:justify-between">
                  <div className="flex flex-wrap items-center gap-2">
                    <span>Rows per page:</span>
                    <Select value={String(pageSize)} onValueChange={handlePageSizeChange}>
                      <SelectTrigger className="w-[70px] h-8">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {PAGE_SIZE_OPTIONS.map((size) => (
                          <SelectItem key={size} value={String(size)}>
                            {size}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <span className="ml-2">
                      Showing {totalItems === 0 ? 0 : (page - 1) * pageSize + 1}–
                      {Math.min(page * pageSize, totalItems)} of {totalItems}
                    </span>
                  </div>
                  <div className="flex flex-wrap items-center gap-2 lg:justify-end">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => setPage((p) => Math.max(1, p - 1))}
                      disabled={page <= 1}
                    >
                      Previous
                    </Button>
                    <span>
                      Page {page} of {totalPages}
                    </span>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                      disabled={page >= totalPages}
                    >
                      Next
                    </Button>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
