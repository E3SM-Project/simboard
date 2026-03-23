import { TooltipProvider } from '@radix-ui/react-tooltip';
import type { VisibilityState } from '@tanstack/react-table';
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
import { listCaseNames, listSimulations, SIMULATIONS_URL } from '@/features/simulations/api/api';
import type { SimulationOut } from '@/types/index';

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

// -------------------- Types & Interfaces --------------------
export interface FilterState {
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

  // Canonical Status
  canonicalStatus: string;

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

  // Canonical Status
  canonicalStatus: '',

  // Metadata & Provenance
  gitTag: [],
  createdBy: [],
  hpcUsername: [],
});

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

export const BrowsePage = ({
  selectedSimulationIds,
  setSelectedSimulationIds,
}: BrowsePageProps) => {
  // -------------------- Router --------------------
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const selectedCaseName = searchParams.get('caseName') ?? '';

  // -------------------- Local State --------------------
  const [simulations, setSimulations] = useState<SimulationOut[]>([]);
  const [caseOptions, setCaseOptions] = useState<{ value: string; label: string }[]>([]);
  const [appliedFilters, setAppliedFilters] = useState<FilterState>(createEmptyFilters);

  const [viewMode, setViewMode] = useState<'grid' | 'table'>(() => parseViewMode(searchParams));
  const [page, setPage] = useState(() => parsePage(searchParams));
  const [pageSize, setPageSize] = useState(() => parsePageSize(searchParams));
  const [columnVisibility, setColumnVisibility] =
    useState<VisibilityState>(DEFAULT_COLUMN_VISIBILITY);

  // -------------------- Derived Data --------------------
  const availableFilters = useMemo(() => {
    // Start with empty filter options.
    const filters = createEmptyFilters();

    // Array-based filter keys that correspond to SimulationOut properties.
    const arrayKeys = Object.keys(createEmptyFilters()).filter(
      (k) => k !== 'canonicalStatus',
    ) as (keyof SimulationOut)[];

    // Populate filter options based on available simulations.
    for (const sim of simulations) {
      for (const key of arrayKeys) {
        const value = sim[key];

        // Handle both string and string[] fields.
        if (Array.isArray(value)) {
          value.forEach((v) => {
            if (typeof v !== 'string') return;
            const filterValues = filters[key as keyof FilterState] as string[];
            const isValueValid = v && !filterValues.includes(v);

            if (isValueValid) {
              filterValues.push(v);
            }
          });
        } else if (typeof value === 'string' && value) {
          const filterValues = filters[key as keyof FilterState] as string[];
          const isValueValid = !filterValues.includes(value);

          if (isValueValid) {
            filterValues.push(value);
          }
        }
      }
    }

    // Sort all string array filters alphabetically for easier navigation.
    (Object.keys(filters) as (keyof FilterState)[]).forEach((key) => {
      const val = filters[key];
      if (Array.isArray(val) && val.length > 0 && typeof val[0] === 'string') {
        (val as string[]).sort((a, b) => a.localeCompare(b, undefined, { sensitivity: 'base' }));
      }
    });

    return filters;
  }, [simulations]);

  const simMachineId = (simulation: SimulationOut) => {
    if (simulation.machine?.id) {
      return simulation.machine.id;
    }

    const legacyMachineId = (simulation as { machineId?: string }).machineId;
    if (typeof legacyMachineId === 'string') {
      return legacyMachineId;
    }

    return undefined;
  };
  const simMachineName = (s: SimulationOut) => s.machine?.name ?? 'Unknown machine';

  const machineOptions = useMemo(() => {
    const machines = new Map<string, string>();

    for (const s of simulations) {
      const id = simMachineId(s);

      if (id) machines.set(id, simMachineName(s));
    }

    const sortedMachines = Array.from(machines, ([value, label]) => ({ value, label })).sort(
      (a, b) => a.label.localeCompare(b.label, undefined, { sensitivity: 'base' }),
    );

    return sortedMachines;
  }, [simulations]);

  const creatorOptions = useMemo(() => {
    const creators = new Map<string, string>();

    for (const simulation of simulations) {
      if (!simulation.createdBy) continue;

      creators.set(simulation.createdBy, simulation.createdByUser?.email ?? simulation.createdBy);
    }

    return Array.from(creators, ([value, label]) => ({ value, label })).sort((a, b) =>
      a.label.localeCompare(b.label, undefined, { sensitivity: 'base' }),
    );
  }, [simulations]);

  const filteredData = useMemo(() => {
    const arrayFilterGetters: Partial<
      Record<
        keyof FilterState,
        (rec: SimulationOut) => string | string[] | [string | null, string | null] | undefined
      >
    > = {
      machineId: (rec) => simMachineId(rec) ?? '',
      campaign: (rec) => rec.campaign ?? [],
      experimentType: (rec) => rec.experimentType ?? [],
      compset: (rec) => rec.compset ?? [],
      gridName: (rec) => rec.gridName ?? [],
      gridResolution: (rec) => rec.gridResolution ?? [],
      simulationType: (rec) => rec.simulationType ?? [],
      initializationType: (rec) => rec.initializationType ?? [],
      compiler: (rec) => rec.compiler ?? [],
      status: (rec) => rec.status ?? [],
      gitTag: (rec) => rec.gitTag ?? [],
      createdBy: (rec) => rec.createdBy ?? [],
      hpcUsername: (rec) => rec.hpcUsername ?? [],
    };

    return simulations.filter((record) => {
      for (const key of Object.keys(arrayFilterGetters) as (keyof FilterState)[]) {
        const getter = arrayFilterGetters[key];
        if (
          getter &&
          Array.isArray(appliedFilters[key]) &&
          (appliedFilters[key] as string[]).length > 0
        ) {
          const raw = getter(record);
          const recVals = Array.isArray(raw) ? raw : ([raw].filter(Boolean) as string[]);
          if (!recVals.some((v) => (appliedFilters[key] as string[]).includes(v as string))) {
            return false;
          }
        }
      }

      if (appliedFilters.canonicalStatus === 'canonical' && !record.isCanonical) return false;
      if (appliedFilters.canonicalStatus === 'non-canonical' && record.isCanonical) return false;

      return true;
    });
  }, [simulations, appliedFilters]);

  // -------------------- Effects --------------------
  useEffect(() => {
    let cancelled = false;

    listCaseNames()
      .then((names) => {
        if (!cancelled) {
          const options = names
            .map((name) => ({ value: name, label: name }))
            .sort((a, b) => a.label.localeCompare(b.label, undefined, { sensitivity: 'base' }));
          setCaseOptions(options);
        }
      })
      .catch(() => {
        if (!cancelled) setCaseOptions([]);
      });

    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    const params = new URLSearchParams();

    if (selectedCaseName) {
      params.set('case_name', selectedCaseName);
    }

    const simulationsUrl = params.toString()
      ? `${SIMULATIONS_URL}?${params.toString()}`
      : SIMULATIONS_URL;

    listSimulations(simulationsUrl)
      .then((res) => {
        if (!cancelled) setSimulations(res);
      })
      .catch(() => {
        if (!cancelled) setSimulations([]);
      });

    return () => {
      cancelled = true;
    };
  }, [selectedCaseName]);

  useEffect(() => {
    const next = createEmptyFilters();
    const multiSelectFilterKeys = (
      Object.keys(createEmptyFilters()) as (keyof FilterState)[]
    ).filter((key) => key !== 'canonicalStatus');

    multiSelectFilterKeys.forEach((key) => {
      const value = searchParams.get(key);
      if (value !== null) {
        next[key] = value.split(',').filter(Boolean) as FilterState[typeof key];
      }
    });

    const canonicalStatus = searchParams.get('canonicalStatus');
    next.canonicalStatus =
      canonicalStatus !== null && ['', 'canonical', 'non-canonical'].includes(canonicalStatus)
        ? canonicalStatus
        : '';

    setAppliedFilters(next);

    // Sync view, page, pageSize from URL (handles back/forward navigation).
    setViewMode(parseViewMode(searchParams));
    setPage(parsePage(searchParams));
    setPageSize(parsePageSize(searchParams));
  }, [searchParams]);

  // Reset page to 1 when filters/case change (skip the initial URL→state sync).
  const prevPageResetSignature = useRef<string | null>(null);
  useEffect(() => {
    const currentSignature = JSON.stringify({
      selectedCaseName,
      appliedFilters,
    });

    if (prevPageResetSignature.current === null) {
      // First render — record baseline without resetting page.
      prevPageResetSignature.current = currentSignature;
      return;
    }

    if (prevPageResetSignature.current !== currentSignature) {
      prevPageResetSignature.current = currentSignature;
      setPage(1);
    }
  }, [appliedFilters, selectedCaseName]);

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

        // Preserve caseName (managed by handleCaseNameChange).
        const filterKeys = Object.keys(createEmptyFilters()) as (keyof FilterState)[];

        for (const key of filterKeys) {
          const value = appliedFilters[key];
          if (Array.isArray(value) && value.length) {
            next.set(key, value.join(','));
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
  const handleCaseNameChange = (caseName: string) => {
    skipNextFilterUrlSync.current = true;
    setAppliedFilters(createEmptyFilters());
    setPage(1);

    setSearchParams(
      (prev) => {
        const next = new URLSearchParams(prev);

        (Object.keys(createEmptyFilters()) as (keyof FilterState)[]).forEach((key) => {
          next.delete(key);
        });

        if (caseName) {
          next.set('caseName', caseName);
        } else {
          next.delete('caseName');
        }

        next.delete('page');

        return next;
      },
      { replace: true },
    );
  };

  const handleClearCaseNameFilter = () => {
    setSearchParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        next.delete('caseName');
        next.delete('page');
        return next;
      },
      { replace: true },
    );
  };

  const handleResetFilters = () => {
    skipNextFilterUrlSync.current = true;
    setAppliedFilters(createEmptyFilters());
    setSearchParams(
      (prev) => {
        const next = new URLSearchParams(prev);

        (Object.keys(createEmptyFilters()) as (keyof FilterState)[]).forEach((key) => {
          next.delete(key);
        });

        next.delete('caseName');
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
  const totalItems = filteredData.length;
  const totalPages = Math.max(1, Math.ceil(totalItems / pageSize));

  // Clamp page state when totalPages shrinks (e.g. after filtering).
  useEffect(() => {
    setPage((p) => (p > totalPages ? totalPages : p));
  }, [totalPages]);

  const paginatedData = useMemo(
    () => filteredData.slice((page - 1) * pageSize, page * pageSize),
    [filteredData, page, pageSize],
  );

  // -------------------- Render --------------------
  return (
    <div className="w-full bg-white">
      <div className="mx-auto w-full max-w-[2200px] px-4 py-6 sm:px-6 lg:px-8 xl:px-10 2xl:px-12">
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
                selectedCaseName={selectedCaseName}
                onCaseNameChange={handleCaseNameChange}
              />
            </div>
          </div>
          <div className="min-w-0">
            <div className="flex min-w-0 flex-col">
              <header className="mb-4 flex flex-col gap-4 rounded-xl border border-slate-200 bg-white p-5 shadow-sm xl:flex-row xl:items-start xl:justify-between">
                <div className="min-w-0">
                  <h1 className="mb-2 text-3xl font-bold tracking-tight text-slate-950">
                    Browse Simulations
                  </h1>
                  <p className="max-w-4xl text-[15px] leading-7 text-slate-600 sm:text-base">
                    Explore and filter available simulations using the panel on the left. Select
                    simulations to view more details or take further actions.
                  </p>
                </div>
                <div className="xl:min-w-[360px]">
                  <TooltipProvider delayDuration={150}>
                    <div className="flex flex-col gap-3 rounded-xl border border-slate-200 bg-slate-50/40 p-3">
                      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-slate-600">
                        <div>
                          <span className="font-medium text-slate-500">Results</span>{' '}
                          <span className="font-semibold text-slate-950">{filteredData.length}</span>
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

              {(selectedCaseName ||
                Object.values(appliedFilters).some((v) => (Array.isArray(v) ? v.length > 0 : !!v))) && (
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
                  {selectedCaseName && (
                    <span className="inline-flex max-w-full items-center rounded-md border border-slate-200 bg-slate-50 px-3 py-1.5 text-sm text-slate-700">
                      <span className="mr-2 text-xs font-medium text-slate-500">case:</span>
                      <span className="mr-2 truncate font-medium text-slate-700">
                        {selectedCaseName}
                      </span>
                      <button
                        type="button"
                        aria-label="Remove case filter"
                        className="ml-1 rounded-sm text-slate-400 transition-colors hover:text-slate-700 focus:outline-none"
                        onClick={handleClearCaseNameFilter}
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
                  )}
                  {(
                    Object.entries(appliedFilters) as [keyof FilterState, string[] | string][]
                  ).flatMap(([key, values]) => {
                    if (Array.isArray(values)) {
                      return values.map((value, idx) => {
                        const display =
                          key === 'machineId'
                            ? (machineOptions.find((opt) => opt.value === value)?.label ?? value)
                            : key === 'createdBy'
                              ? (creatorOptions.find((opt) => opt.value === value)?.label ?? value)
                            : value;
                        return (
                          <span
                            key={`${key}-${value}-${idx}`}
                            className="inline-flex max-w-full items-center rounded-md border border-slate-200 bg-slate-50 px-3 py-1.5 text-sm text-slate-700"
                          >
                            <span className="mr-2 text-xs font-medium text-slate-500">
                              {String(key).replace(/Id$/, '')}:
                            </span>
                            <span className="mr-2 truncate font-medium text-slate-700">
                              {display}
                            </span>
                            <button
                              type="button"
                              aria-label={`Remove ${String(key)} filter`}
                              className="ml-1 rounded-sm text-slate-400 transition-colors hover:text-slate-700 focus:outline-none"
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
                            ? (creatorOptions.find((opt) => opt.value === values)?.label ?? values)
                          : values;
                      return (
                        <span
                          key={`${String(key)}-${values}`}
                          className="inline-flex max-w-full items-center rounded-md border border-slate-200 bg-slate-50 px-3 py-1.5 text-sm text-slate-700"
                        >
                          <span className="mr-2 text-xs font-medium text-slate-500">
                            {String(key).replace(/Id$/, '')}:
                          </span>
                          <span className="mr-2 truncate font-medium text-slate-700">
                            {display}
                          </span>
                          <button
                            type="button"
                            aria-label={`Remove ${String(key)} filter`}
                            className="ml-1 rounded-sm text-slate-400 transition-colors hover:text-slate-700 focus:outline-none"
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
                    filteredData={filteredData}
                    page={page}
                    pageSize={pageSize}
                    selectedSimulationIds={selectedSimulationIds}
                    setSelectedSimulationIds={setSelectedSimulationIds}
                    handleCompareButtonClick={handleCompareButtonClick}
                    columnVisibility={columnVisibility}
                    setColumnVisibility={setColumnVisibility}
                  />
                ) : (
                  <SimulationResultCards
                    simulations={simulations}
                    filteredData={paginatedData}
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
