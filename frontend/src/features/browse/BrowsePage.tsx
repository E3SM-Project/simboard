import { TooltipProvider } from '@radix-ui/react-tooltip';
import { LayoutGrid, Table } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';

import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import { BrowseFiltersSidePanel } from '@/features/browse/components/BrowseFiltersSidePanel';
import { SimulationResultCards } from '@/features/browse/components/SimulationResults/SimulationResultsCards';
import { SimulationResultsTable } from '@/features/browse/components/SimulationResults/SimulationResultsTable';
import type { SimulationOut } from '@/types/index';

// -------------------- Types & Interfaces --------------------
export interface FilterState {
  // Scientific Goal
  campaignId: string[];
  experimentTypeId: string[];
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
  simulations: SimulationOut[];
  selectedSimulationIds: string[];
  setSelectedSimulationIds: (ids: string[]) => void;
}

// -------------------- Pure Helpers --------------------
const createEmptyFilters = (): FilterState => ({
  // Scientific Goal
  campaignId: [],
  experimentTypeId: [],
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
  simulations,
  selectedSimulationIds,
  setSelectedSimulationIds,
}: BrowsePageProps) => {
  // -------------------- Router --------------------
  const location = useLocation();
  const navigate = useNavigate();

  // -------------------- Local State --------------------
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
      campaignId: (rec) => rec.campaignId ?? [],
      experimentTypeId: (rec) => rec.experimentTypeId ?? [],
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
    const params = new URLSearchParams(location.search);
    const next: Partial<FilterState> = {};
    const arrayKeys: (keyof FilterState)[] = [
      'campaignId',
      'experimentTypeId',
      'machineId',
      'compset',
      'gridName',
      'simulationType',
      'gitTag',
      'status',
    ];

    arrayKeys.forEach((key) => {
      const value = params.get(key);
      if (value !== null) {
        // FIXME: Fix below eslint error with any (TS is being difficult).
        // eslint-disable-next-line @typescript-eslint/ban-ts-comment
        // @ts-ignore: Type 'string | string[]' is not assignable to type '(string[] & string) | undefined'.
        next[key] = arrayKeys.includes(key) ? (value.split(',') as string[]) : value;
      }
    });

    setAppliedFilters((prev) => ({ ...prev, ...next }));
  }, [location.search]);

  useEffect(() => {
    const params = new URLSearchParams();

    Object.entries(appliedFilters).forEach(([key, value]) => {
      if (Array.isArray(value) && value.length) {
        params.set(key, value.join(','));
      } else if (typeof value === 'string' && value) {
        params.set(key, value);
      }
    });

    navigate({ search: params.toString() }, { replace: true });
  }, [appliedFilters, navigate]);

  // -------------------- Handlers --------------------
  const handleResetFilters = () => {
    setAppliedFilters(createEmptyFilters());
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
                  {Object.values(appliedFilters).some((v) =>
                    Array.isArray(v) ? v.length > 0 : !!v,
                  ) && (
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
