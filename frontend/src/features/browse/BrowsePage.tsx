import { TooltipProvider } from '@radix-ui/react-tooltip';
import { LayoutGrid, Table } from 'lucide-react';
import { useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';

import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import { BrowseFiltersSidePanel } from '@/features/browse/components/BrowseFiltersSidePanel';
import { SimulationResultCards } from '@/features/browse/components/SimulationResults/SimulationResultsCards';
import { SimulationResultsTable } from '@/features/browse/components/SimulationResults/SimulationResultsTable';
import { listCaseNames, listSimulations, SIMULATIONS_URL } from '@/features/simulations/api/api';
import type { SimulationOut } from '@/types/index';

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

  // Metadata & Provenance
  gitTag: string[];
  createdBy: string[];
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

  // Metadata & Provenance
  gitTag: [],
  createdBy: [],
});

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
  const [viewMode, setViewMode] = useState<'grid' | 'table'>('grid');

  // -------------------- Derived Data --------------------
  const availableFilters = useMemo(() => {
    // Start with empty filter options.
    const filters = createEmptyFilters();

    // Populate filter options based on available simulations.
    for (const sim of simulations) {
      const keys = Object.keys(createEmptyFilters()) as (keyof FilterState)[];

      for (const key of keys) {
        const value = (sim as SimulationOut)[key];

        // Handle both string and string[] fields.
        if (Array.isArray(value)) {
          value.forEach((v) => {
            const filterValues = filters[key] as string[];
            const isValueValid = v && !filterValues.includes(v);

            if (isValueValid) {
              filterValues.push(v);
            }
          });
        } else if (typeof value === 'string' && value) {
          const filterValues = filters[key] as string[];
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

  const filteredData = useMemo(() => {
    const arrayFilterGetters: Record<
      keyof FilterState,
      (rec: SimulationOut) => string | string[] | [string | null, string | null] | undefined
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
    };

    return simulations.filter((record) => {
      for (const key of Object.keys(arrayFilterGetters) as (keyof FilterState)[]) {
        if (Array.isArray(appliedFilters[key]) && (appliedFilters[key] as string[]).length > 0) {
          const raw = arrayFilterGetters[key](record);
          const recVals = Array.isArray(raw) ? raw : ([raw].filter(Boolean) as string[]);
          if (!recVals.some((v) => (appliedFilters[key] as string[]).includes(v as string))) {
            return false;
          }
        }
      }

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
    const next: Partial<FilterState> = {};
    const allFilterKeys = Object.keys(createEmptyFilters()) as (keyof FilterState)[];

    allFilterKeys.forEach((key) => {
      const value = searchParams.get(key);
      if (value !== null) {
        // All FilterState values are string arrays.
        next[key] = value.split(',') as string[];
      }
    });

    setAppliedFilters((prev) => ({ ...prev, ...next }));
  }, [searchParams]);

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

        return next;
      },
      { replace: true },
    );
  }, [appliedFilters, setSearchParams]);

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
                            aria-label="Grid view"
                            className={`p-2 rounded ${viewMode === 'grid' ? 'bg-gray-200' : ''}`}
                            onClick={() => setViewMode('grid')}
                          >
                            <LayoutGrid size={24} strokeWidth={2} />
                          </button>
                        </TooltipTrigger>
                        <TooltipContent>Show simulations as cards</TooltipContent>
                      </Tooltip>
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
                    selectedSimulationIds={selectedSimulationIds}
                    setSelectedSimulationIds={setSelectedSimulationIds}
                    handleCompareButtonClick={handleCompareButtonClick}
                  />
                ) : (
                  <SimulationResultCards
                    simulations={simulations}
                    filteredData={filteredData}
                    selectedSimulationIds={selectedSimulationIds}
                    setSelectedSimulationIds={setSelectedSimulationIds}
                    handleCompareButtonClick={handleCompareButtonClick}
                  />
                )}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
