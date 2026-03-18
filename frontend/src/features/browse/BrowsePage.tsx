import { TooltipProvider } from '@radix-ui/react-tooltip';
import { LayoutGrid, Table } from 'lucide-react';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';

import { Button } from '@/components/ui/button';
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
  useEffect(() => {
    // Skip the initial render — filters are read FROM the URL on mount.
    if (isInitialFilterSync.current) {
      isInitialFilterSync.current = false;
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
    setSearchParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        if (caseName) {
          next.set('caseName', caseName);
        } else {
          next.delete('caseName');
        }
        return next;
      },
      { replace: true },
    );
  };

  const handleResetFilters = () => {
    setAppliedFilters(createEmptyFilters());
    setSearchParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        next.delete('caseName');
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
      <div className="mx-auto max-w-[1440px] px-6 py-8">
        <div className="flex flex-col md:flex-row gap-8">
          <div className="flex flex-row w-full gap-6">
            <div className="w-full md:w-[400px] min-w-0 md:min-w-[180px] overflow-y-auto max-h-screen">
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
            <div className="flex-1 flex flex-col min-w-0">
              <header className="mb-3 px-2 mt-4 flex items-center justify-between">
                <div>
                  <h1 className="text-3xl font-bold mb-2">Browse Simulations</h1>
                  <p className="text-gray-600 max-w-6xl">
                    Explore and filter available simulations using the panel on the left. Select
                    simulations to view more details or take further actions.
                  </p>
                </div>
                <div className="flex flex-col items-end gap-1 ml-8">
                  <div className="flex items-center gap-3 text-sm text-muted-foreground">
                    <span>
                      <span className="font-semibold text-foreground">{filteredData.length}</span>{' '}
                      simulations found
                    </span>
                    <span className="h-4 w-px bg-gray-300 mx-1" />
                    <span>
                      View mode:{' '}
                      <span className="font-medium text-foreground">
                        {viewMode === 'grid' ? 'Cards' : 'Table'}
                      </span>
                    </span>
                  </div>
                  <TooltipProvider delayDuration={150}>
                    <div className="flex gap-2 mt-1">
                      <Tooltip>
                        <TooltipTrigger asChild>
                          <button
                            aria-label="Table view"
                            className={`p-2 rounded ${viewMode === 'table' ? 'bg-gray-200' : ''}`}
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
                            className={`p-2 rounded ${viewMode === 'grid' ? 'bg-gray-200' : ''}`}
                            onClick={() => setViewMode('grid')}
                          >
                            <LayoutGrid size={24} strokeWidth={2} />
                          </button>
                        </TooltipTrigger>
                        <TooltipContent>Show simulations as cards</TooltipContent>
                      </Tooltip>
                    </div>
                  </TooltipProvider>
                </div>
              </header>

              <div className="flex flex-col items-start gap-2">
                <div className="flex flex-wrap gap-2">
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
                            className="inline-flex items-center px-3 py-1 rounded-full bg-gray-100 text-sm text-gray-700 border border-gray-300"
                          >
                            <span className="mr-2 font-medium capitalize">
                              {String(key).replace(/Id$/, '')}:
                            </span>
                            <span className="mr-2">{display}</span>
                            <button
                              type="button"
                              aria-label={`Remove ${String(key)} filter`}
                              className="ml-1 text-gray-400 hover:text-gray-700 rounded-full focus:outline-none"
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
                          className="inline-flex items-center px-3 py-1 rounded-full bg-gray-100 text-sm text-gray-700 border border-gray-300"
                        >
                          <span className="mr-2 font-medium capitalize">
                            {String(key).replace(/Id$/, '')}:
                          </span>
                          <span className="mr-2">{display}</span>
                          <button
                            type="button"
                            aria-label={`Remove ${String(key)} filter`}
                            className="ml-1 text-gray-400 hover:text-gray-700 rounded-full focus:outline-none"
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
                  {(selectedCaseName ||
                    Object.values(appliedFilters).some((v) =>
                      Array.isArray(v) ? v.length > 0 : !!v,
                    )) && (
                    <button
                      type="button"
                      className="inline-flex items-center px-3 py-1 rounded-full bg-red-100 text-sm text-red-700 border border-red-300 ml-2"
                      aria-label="Clear all filters"
                      onClick={handleResetFilters}
                    >
                      <span className="mr-2 font-medium">Clear All</span>
                      <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                        <path
                          d="M4 4L12 12M12 4L4 12"
                          stroke="currentColor"
                          strokeWidth="2"
                          strokeLinecap="round"
                        />
                      </svg>
                    </button>
                  )}
                </div>
              </div>
              <div>
                {viewMode === 'table' ? (
                  <SimulationResultsTable
                    simulations={simulations}
                    filteredData={filteredData}
                    page={page}
                    pageSize={pageSize}
                    selectedSimulationIds={selectedSimulationIds}
                    setSelectedSimulationIds={setSelectedSimulationIds}
                    handleCompareButtonClick={handleCompareButtonClick}
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
                <div className="flex items-center justify-between py-4 text-sm text-muted-foreground">
                  <div className="flex items-center gap-2">
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
                  <div className="flex items-center gap-2">
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
