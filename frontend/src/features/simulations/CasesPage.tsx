import type { ColumnDef, SortingState } from '@tanstack/react-table';
import {
  flexRender,
  getCoreRowModel,
  getPaginationRowModel,
  getSortedRowModel,
  useReactTable,
} from '@tanstack/react-table';
import { ChevronDown, ChevronRight } from 'lucide-react';
import { Fragment, useMemo, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';

import { SimulationStatusBadge } from '@/components/shared/SimulationStatusBadge';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
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
  getCanonicalSimulation,
} from '@/features/simulations/caseUtils';
import { useCases } from '@/features/simulations/hooks/useCases';
import type { CaseOut, SimulationOut } from '@/types';

type CanonicalFilter = 'all' | 'with-canonical' | 'without-canonical';

interface CasesPageProps {
  simulations: SimulationOut[];
}

interface CaseSimulationFilters {
  hpcUsername: string;
  machineId: string;
  status: string;
  campaign: string;
  simulationType: string;
  initializationType: string;
  compiler: string;
  gitTag: string;
  createdBy: string;
}

const createEmptySimulationFilters = (): CaseSimulationFilters => ({
  hpcUsername: '',
  machineId: '',
  status: '',
  campaign: '',
  simulationType: '',
  initializationType: '',
  compiler: '',
  gitTag: '',
  createdBy: '',
});

const sortStringValues = (values: string[]) =>
  values.sort((left, right) => left.localeCompare(right, undefined, { sensitivity: 'base' }));

const sortCaseSimulations = (caseSimulations: SimulationOut[]) =>
  [...caseSimulations].sort((left, right) => {
    if (left.isCanonical !== right.isCanonical) {
      return left.isCanonical ? -1 : 1;
    }

    return new Date(right.simulationStartDate).getTime() - new Date(left.simulationStartDate).getTime();
  });

export const CasesPage = ({ simulations }: CasesPageProps) => {
  const navigate = useNavigate();
  const { data: cases, loading, error } = useCases();
  const [caseNameFilter, setCaseNameFilter] = useState('');
  const [caseGroupFilter, setCaseGroupFilter] = useState('');
  const [simulationFilters, setSimulationFilters] =
    useState<CaseSimulationFilters>(createEmptySimulationFilters);
  const [canonicalFilter, setCanonicalFilter] = useState<CanonicalFilter>('all');
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
  const statuses = useMemo(
    () =>
      sortStringValues(
        [...new Set(simulations.map((simulation) => simulation.status).filter(Boolean))] as string[],
      ),
    [simulations],
  );
  const campaigns = useMemo(
    () =>
      sortStringValues(
        [...new Set(simulations.map((simulation) => simulation.campaign).filter(Boolean))] as string[],
      ),
    [simulations],
  );
  const simulationTypes = useMemo(
    () =>
      sortStringValues(
        [...new Set(simulations.map((simulation) => simulation.simulationType).filter(Boolean))] as string[],
      ),
    [simulations],
  );
  const initializationTypes = useMemo(
    () =>
      sortStringValues(
        [
          ...new Set(
            simulations.map((simulation) => simulation.initializationType).filter(Boolean),
          ),
        ] as string[],
      ),
    [simulations],
  );
  const compilers = useMemo(
    () =>
      sortStringValues(
        [...new Set(simulations.map((simulation) => simulation.compiler).filter(Boolean))] as string[],
      ),
    [simulations],
  );
  const gitTags = useMemo(
    () =>
      sortStringValues(
        [...new Set(simulations.map((simulation) => simulation.gitTag).filter(Boolean))] as string[],
      ),
    [simulations],
  );
  const hasActiveSimulationFilters = useMemo(
    () => Object.values(simulationFilters).some(Boolean),
    [simulationFilters],
  );
  const hasActiveFilters =
    caseNameFilter.trim().length > 0 ||
    caseGroupFilter.length > 0 ||
    canonicalFilter !== 'all' ||
    hasActiveSimulationFilters;
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
      if (simulationFilters.status && simulation.status !== simulationFilters.status) {
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
    const filters: { key: string; label: string; value: string }[] = [];
    if (caseNameFilter.trim()) filters.push({ key: 'caseName', label: 'Case', value: caseNameFilter.trim() });
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
    if (simulationFilters.status) {
      filters.push({ key: 'status', label: 'Status', value: simulationFilters.status });
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
    if (canonicalFilter !== 'all') {
      filters.push({
        key: 'canonical',
        label: 'Canonical',
        value: canonicalFilter === 'with-canonical' ? 'Present' : 'Missing',
      });
    }

    return filters;
  }, [canonicalFilter, caseGroupFilter, caseNameFilter, creatorOptions, machineOptions, simulationFilters]);

  const filteredCases = useMemo(() => {
    const normalizedNameFilter = caseNameFilter.trim().toLowerCase();

    return cases.filter((caseRecord) => {
      const matchesName =
        normalizedNameFilter.length === 0 ||
        caseRecord.name.toLowerCase().includes(normalizedNameFilter);
      const matchesGroup = !caseGroupFilter || caseRecord.caseGroup === caseGroupFilter;
      const hasCanonicalSimulation = caseRecord.canonicalSimulationId != null;
      const matchesCanonical =
        canonicalFilter === 'all' ||
        (canonicalFilter === 'with-canonical' && hasCanonicalSimulation) ||
        (canonicalFilter === 'without-canonical' && !hasCanonicalSimulation);
      const matchesSimulationFilters =
        !hasActiveSimulationFilters ||
        (matchingSimulationsByCaseId.get(caseRecord.id)?.length ?? 0) > 0;

      return matchesName && matchesGroup && matchesCanonical && matchesSimulationFilters;
    });
  }, [
    caseGroupFilter,
    cases,
    canonicalFilter,
    caseNameFilter,
    hasActiveSimulationFilters,
    matchingSimulationsByCaseId,
  ]);

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
                setExpandedCaseId((current) => (current === row.original.id ? null : row.original.id));
              }}
            >
              {isExpanded ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
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
            className="block max-w-[28rem] truncate font-medium text-blue-600 hover:underline"
            title={row.original.name}
            onClick={(event) => event.stopPropagation()}
          >
            {row.original.name}
          </Link>
        ),
      },
      {
        accessorKey: 'caseGroup',
        header: 'Case Group',
        cell: ({ row }) => <TableCellText value={row.original.caseGroup ?? '—'} />,
      },
      {
        id: 'canonicalSimulation',
        header: 'Canonical Simulation',
        accessorFn: (caseRecord) => getCanonicalSimulation(caseRecord)?.executionId ?? '—',
        cell: ({ row }) => {
          const canonicalSimulation = getCanonicalSimulation(row.original);

          if (!canonicalSimulation) {
            return <span className="text-muted-foreground">—</span>;
          }

          return (
            <Link
              to={`/simulations/${canonicalSimulation.id}`}
              className="font-mono text-xs text-blue-600 hover:underline"
              title={canonicalSimulation.executionId}
              onClick={(event) => event.stopPropagation()}
            >
              {canonicalSimulation.executionId}
            </Link>
          );
        },
      },
      {
        id: 'simulationCount',
        header: 'Total Simulations',
        accessorFn: (caseRecord) => caseRecord.simulations.length,
        cell: ({ row }) => {
          const totalSimulations =
            simulationsByCaseId.get(row.original.id)?.length ?? row.original.simulations.length;
          const matchingSimulations = matchingSimulationsByCaseId.get(row.original.id)?.length ?? 0;

          return hasActiveSimulationFilters ? (
            <div className="flex items-center gap-2">
              <Badge variant="secondary">{matchingSimulations}</Badge>
              <span className="text-xs text-muted-foreground">of {totalSimulations}</span>
            </div>
          ) : (
            <Badge variant="secondary">{totalSimulations}</Badge>
          );
        },
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
            <Link to={`/cases/${row.original.id}`}>View case</Link>
          </Button>
        ),
      },
    ],
    [expandedCaseId, hasActiveSimulationFilters, matchingSimulationsByCaseId, simulationsByCaseId],
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

  const renderExpandedContent = (caseRecord: CaseOut) => {
    const allCaseSimulations = sortCaseSimulations(simulationsByCaseId.get(caseRecord.id) ?? []);
    const matchingCaseSimulations = sortCaseSimulations(
      matchingSimulationsByCaseId.get(caseRecord.id) ?? [],
    );
    const simulations =
      hasActiveSimulationFilters ? matchingCaseSimulations : allCaseSimulations;

    return (
      <div className="space-y-3 bg-muted/20 p-4">
        <div className="flex items-center justify-between gap-3">
          <div>
            <p className="text-sm font-medium">Simulation Summaries</p>
            <p className="text-xs text-muted-foreground">
              {hasActiveSimulationFilters
                ? `${matchingCaseSimulations.length} of ${allCaseSimulations.length} runs match the current filters.`
                : 'Canonical simulations are pinned first. Open the case page for full context.'}
            </p>
          </div>
          <Button variant="outline" size="sm" asChild>
            <Link to={`/cases/${caseRecord.id}`}>Open case page</Link>
          </Button>
        </div>

        <div className="overflow-hidden rounded-md border bg-background">
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Execution ID</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Canonical</TableHead>
                  <TableHead>Change Count</TableHead>
                  <TableHead>Simulation Dates</TableHead>
                  <TableHead>View Details</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {simulations.map((simulation) => (
                  <TableRow key={simulation.id}>
                    <TableCell className="align-top">
                      <Link
                        to={`/simulations/${simulation.id}`}
                        className="font-mono text-xs text-blue-600 hover:underline"
                      >
                        {simulation.executionId}
                      </Link>
                    </TableCell>
                    <TableCell className="align-top">
                      <SimulationStatusBadge status={simulation.status} />
                    </TableCell>
                    <TableCell className="align-top">
                      {simulation.isCanonical ? (
                        <Badge
                          variant="outline"
                          className="border-green-200 bg-green-50 text-green-700"
                        >
                          Canonical
                        </Badge>
                      ) : (
                        <span className="text-muted-foreground">—</span>
                      )}
                    </TableCell>
                    <TableCell className="align-top">{simulation.changeCount}</TableCell>
                    <TableCell className="align-top">
                      {`${formatCaseDate(simulation.simulationStartDate)} → ${formatCaseDate(
                        simulation.simulationEndDate ?? null,
                      )}`}
                    </TableCell>
                    <TableCell className="align-top">
                      <Link
                        to={`/simulations/${simulation.id}`}
                        className="text-blue-600 hover:underline"
                      >
                        View simulation
                      </Link>
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
    <div className="mx-auto w-full max-w-[1400px] space-y-6 px-8 py-8">
      <div className="flex flex-col gap-2 md:flex-row md:items-end md:justify-between">
        <div>
          <h1 className="text-2xl font-bold">Cases</h1>
          <p className="text-sm text-muted-foreground">
            Discover cases through run metadata like HPC username, machine, status, and version context.
          </p>
        </div>
        <div className="text-sm text-muted-foreground">
          {filteredCases.length} of {cases.length} cases
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-3 rounded-md bg-muted p-4">
        <Input
          placeholder="Search case name…"
          value={caseNameFilter}
          onChange={(event) => {
            setCaseNameFilter(event.target.value);
            table.setPageIndex(0);
          }}
          className="w-full md:w-[320px]"
        />

        <Select
          value={simulationFilters.hpcUsername || '__all__'}
          onValueChange={(value) => {
            setSimulationFilters((current) => ({
              ...current,
              hpcUsername: value === '__all__' ? '' : value,
            }));
            table.setPageIndex(0);
          }}
        >
          <SelectTrigger className="w-full md:w-[220px]">
            <SelectValue placeholder="All HPC usernames" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="__all__">All HPC usernames</SelectItem>
            {hpcUsernames.map((username) => (
              <SelectItem key={username} value={username}>
                {username}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Select
          value={simulationFilters.machineId || '__all__'}
          onValueChange={(value) => {
            setSimulationFilters((current) => ({
              ...current,
              machineId: value === '__all__' ? '' : value,
            }));
            table.setPageIndex(0);
          }}
        >
          <SelectTrigger className="w-full md:w-[220px]">
            <SelectValue placeholder="All machines" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="__all__">All machines</SelectItem>
            {machineOptions.map((option) => (
              <SelectItem key={option.value} value={option.value}>
                {option.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Select
          value={simulationFilters.status || '__all__'}
          onValueChange={(value) => {
            setSimulationFilters((current) => ({
              ...current,
              status: value === '__all__' ? '' : value,
            }));
            table.setPageIndex(0);
          }}
        >
          <SelectTrigger className="w-full md:w-[220px]">
            <SelectValue placeholder="All statuses" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="__all__">All statuses</SelectItem>
            {statuses.map((status) => (
              <SelectItem key={status} value={status}>
                {status}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Select
          value={simulationFilters.campaign || '__all__'}
          onValueChange={(value) => {
            setSimulationFilters((current) => ({
              ...current,
              campaign: value === '__all__' ? '' : value,
            }));
            table.setPageIndex(0);
          }}
        >
          <SelectTrigger className="w-full md:w-[220px]">
            <SelectValue placeholder="All campaigns" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="__all__">All campaigns</SelectItem>
            {campaigns.map((campaign) => (
              <SelectItem key={campaign} value={campaign}>
                {campaign}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Select
          value={simulationFilters.simulationType || '__all__'}
          onValueChange={(value) => {
            setSimulationFilters((current) => ({
              ...current,
              simulationType: value === '__all__' ? '' : value,
            }));
            table.setPageIndex(0);
          }}
        >
          <SelectTrigger className="w-full md:w-[220px]">
            <SelectValue placeholder="All types" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="__all__">All types</SelectItem>
            {simulationTypes.map((simulationType) => (
              <SelectItem key={simulationType} value={simulationType}>
                {simulationType}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Select
          value={simulationFilters.initializationType || '__all__'}
          onValueChange={(value) => {
            setSimulationFilters((current) => ({
              ...current,
              initializationType: value === '__all__' ? '' : value,
            }));
            table.setPageIndex(0);
          }}
        >
          <SelectTrigger className="w-full md:w-[220px]">
            <SelectValue placeholder="All init types" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="__all__">All init types</SelectItem>
            {initializationTypes.map((initializationType) => (
              <SelectItem key={initializationType} value={initializationType}>
                {initializationType}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Select
          value={simulationFilters.compiler || '__all__'}
          onValueChange={(value) => {
            setSimulationFilters((current) => ({
              ...current,
              compiler: value === '__all__' ? '' : value,
            }));
            table.setPageIndex(0);
          }}
        >
          <SelectTrigger className="w-full md:w-[220px]">
            <SelectValue placeholder="All compilers" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="__all__">All compilers</SelectItem>
            {compilers.map((compiler) => (
              <SelectItem key={compiler} value={compiler}>
                {compiler}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Select
          value={simulationFilters.gitTag || '__all__'}
          onValueChange={(value) => {
            setSimulationFilters((current) => ({
              ...current,
              gitTag: value === '__all__' ? '' : value,
            }));
            table.setPageIndex(0);
          }}
        >
          <SelectTrigger className="w-full md:w-[220px]">
            <SelectValue placeholder="All tags" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="__all__">All tags</SelectItem>
            {gitTags.map((gitTag) => (
              <SelectItem key={gitTag} value={gitTag}>
                {gitTag}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Select
          value={simulationFilters.createdBy || '__all__'}
          onValueChange={(value) => {
            setSimulationFilters((current) => ({
              ...current,
              createdBy: value === '__all__' ? '' : value,
            }));
            table.setPageIndex(0);
          }}
        >
          <SelectTrigger className="w-full md:w-[220px]">
            <SelectValue placeholder="All creators" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="__all__">All creators</SelectItem>
            {creatorOptions.map((option) => (
              <SelectItem key={option.value} value={option.value}>
                {option.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Select
          value={caseGroupFilter || '__all__'}
          onValueChange={(value) => {
            setCaseGroupFilter(value === '__all__' ? '' : value);
            table.setPageIndex(0);
          }}
        >
          <SelectTrigger className="w-full md:w-[220px]">
            <SelectValue placeholder="All case groups" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="__all__">All case groups</SelectItem>
            {caseGroups.map((group) => (
              <SelectItem key={group} value={group}>
                {group}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Select
          value={canonicalFilter}
          onValueChange={(value: CanonicalFilter) => {
            setCanonicalFilter(value);
            table.setPageIndex(0);
          }}
        >
          <SelectTrigger className="w-full md:w-[220px]">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All canonical states</SelectItem>
            <SelectItem value="with-canonical">Canonical present</SelectItem>
            <SelectItem value="without-canonical">Canonical missing</SelectItem>
          </SelectContent>
        </Select>

        <Button
          variant="outline"
          size="sm"
          type="button"
          onClick={() => {
            setCaseNameFilter('');
            setCaseGroupFilter('');
            setSimulationFilters(createEmptySimulationFilters());
            setCanonicalFilter('all');
            table.setPageIndex(0);
          }}
          disabled={!hasActiveFilters}
        >
          Clear filters
        </Button>
      </div>

      {hasActiveFilters && (
        <div className="flex flex-wrap items-center gap-2 rounded-md border bg-background p-3">
          {activeFilterPills.map((filter) => (
            <span
              key={`${filter.key}-${filter.value}`}
              className="inline-flex items-center rounded-md border border-slate-200 bg-slate-50 px-3 py-1.5 text-sm text-slate-700"
            >
              <span className="mr-2 text-xs font-medium text-slate-500">{filter.label}:</span>
              <span className="font-medium">{filter.value}</span>
            </span>
          ))}
        </div>
      )}

      <div className="overflow-hidden rounded-md border bg-background">
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
                        onClick={() => navigate(`/cases/${row.original.id}`)}
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
