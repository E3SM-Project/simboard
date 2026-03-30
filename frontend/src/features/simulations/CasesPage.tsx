import type { ColumnDef, SortingState } from '@tanstack/react-table';
import {
  flexRender,
  getCoreRowModel,
  getPaginationRowModel,
  getSortedRowModel,
  useReactTable,
} from '@tanstack/react-table';
import { useMemo, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';

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
import { formatCaseDate, getCanonicalSimulation } from '@/features/simulations/caseUtils';
import { useCases } from '@/features/simulations/hooks/useCases';
import type { CaseOut } from '@/types';

type CanonicalFilter = 'all' | 'with-canonical' | 'without-canonical';

export const CasesPage = () => {
  const navigate = useNavigate();
  const { data: cases, loading, error } = useCases();
  const [caseNameFilter, setCaseNameFilter] = useState('');
  const [caseGroupFilter, setCaseGroupFilter] = useState('');
  const [canonicalFilter, setCanonicalFilter] = useState<CanonicalFilter>('all');
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

      return matchesName && matchesGroup && matchesCanonical;
    });
  }, [cases, caseGroupFilter, canonicalFilter, caseNameFilter]);

  const columns = useMemo<ColumnDef<CaseOut>[]>(
    () => [
      {
        accessorKey: 'name',
        header: 'Case Name',
        cell: ({ row }) => (
          <Link
            to={`/cases/${row.original.id}`}
            className="block max-w-full truncate font-medium text-blue-600 hover:underline"
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
        cell: ({ row }) => <Badge variant="secondary">{row.original.simulations.length}</Badge>,
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
    [],
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
            Browse experiment-level records, inspect canonical baselines, and drill into each case.
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
      </div>

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
                table.getRowModel().rows.map((row) => (
                  <TableRow
                    key={row.id}
                    className="cursor-pointer hover:bg-muted/40"
                    onClick={() => navigate(`/cases/${row.original.id}`)}
                  >
                    {row.getVisibleCells().map((cell) => (
                      <TableCell key={cell.id} className="align-top">
                        {flexRender(cell.column.columnDef.cell, cell.getContext())}
                      </TableCell>
                    ))}
                  </TableRow>
                ))
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
