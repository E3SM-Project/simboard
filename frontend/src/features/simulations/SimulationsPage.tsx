import type { ColumnDef } from '@tanstack/react-table';
import {
  getCoreRowModel,
  getFilteredRowModel,
  getPaginationRowModel,
  getSortedRowModel,
  SortingState,
  useReactTable,
  VisibilityState,
} from '@tanstack/react-table';
import { format } from 'date-fns';
import { useMemo, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Input } from '@/components/ui/input';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { cn } from '@/lib/utils';
import type { SimulationOut } from '@/types/index';

// -------------------- Types & Interfaces --------------------
interface SimulationsPageProps {
  simulations: SimulationOut[];
}

// -------------------- Pure Helpers --------------------
const statusColors: Record<string, string> = {
  running: 'bg-blue-100 text-blue-800',
  complete: 'bg-green-100 text-green-800',
  failed: 'bg-red-100 text-red-800',
  'not-started': 'bg-gray-100 text-gray-800',
};

const typeColors: Record<SimulationOut['simulationType'], string> = {
  production: 'border-green-600 text-green-700',
  master: 'border-blue-600 text-blue-700',
  experimental: 'border-amber-600 text-amber-700',
};

/**
 * Formats a given date string into the 'yyyy-MM-dd' format.
 * If the input is undefined or an invalid date, it returns a placeholder ('—').
 *
 * @param d - The date string to format. Can be undefined.
 * @returns The formatted date string in 'yyyy-MM-dd' format, or '—' if the input is invalid.
 *
 * @example
 * ```typescript
 * formatDate('2023-10-05'); // Returns '2023-10-05'
 * formatDate(undefined);    // Returns '—'
 * formatDate('invalid');    // Returns '—'
 * ```
 */
const formatDate = (d?: string) => {
  if (!d) return '—';

  const dt = new Date(d);
  if (Number.isNaN(dt.getTime())) return '—';

  return format(dt, 'yyyy-MM-dd');
};

export const SimulationsPage = ({ simulations }: SimulationsPageProps) => {
  const [globalFilter, setGlobalFilter] = useState('');
  const [selectedRows, setSelectedRows] = useState<Record<string, boolean>>({});
  const [sorting, setSorting] = useState<SortingState>([
    { id: 'createdAt', desc: true },
    { id: 'name', desc: false },
  ]);
  const [viewMode, setViewMode] = useState<'simple' | 'advanced'>('simple');
  const [columnVisibility, setColumnVisibility] = useState<VisibilityState>({});
  const navigate = useNavigate();

  const columns = useMemo<ColumnDef<SimulationOut>[]>(
    () => [
      {
        accessorKey: 'name',
        header: 'Name',
        cell: ({ row }) => (
          <Link
            to={`/simulations/${row.original.id}`}
            className="text-blue-600 hover:underline"
            onClick={(e) => e.stopPropagation()}
          >
            {row.original.name}
          </Link>
        ),
        size: 260,
      },
      {
        accessorKey: 'simulationType',
        header: 'Type',
        cell: ({ row }) => (
          <Badge
            variant="outline"
            className={cn('capitalize', typeColors[row.original.simulationType])}
          >
            {row.original.simulationType}
          </Badge>
        ),
        size: 130,
      },
      {
        accessorKey: 'status',
        header: 'Status',
        cell: ({ row }) => (
          <Badge
            className={cn(
              'capitalize',
              statusColors[row.original.status] || 'bg-gray-100 text-gray-800',
            )}
          >
            {row.original.status}
          </Badge>
        ),
        size: 130,
      },
      { accessorKey: 'gitTag', header: 'Version / Tag', size: 180 },
      { accessorKey: 'gridName', header: 'Grid', size: 110 },
      {
        accessorKey: 'compset',
        header: 'Compset',
        cell: ({ getValue }) => (
          <span title={String(getValue() ?? '')} className="inline-block max-w-[16ch] truncate">
            {String(getValue() ?? '—')}
          </span>
        ),
        size: 180,
      },
      {
        id: 'modelDates',
        header: 'Simulation Dates',
        accessorFn: (r) =>
          `${formatDate(r.simulationStartDate ?? undefined)} → ${formatDate(r.simulationEndDate ?? undefined)}`,
        size: 220,
      },
      {
        accessorKey: 'machineId',
        header: 'Machine',
        cell: ({ row }) => (
          <span title={row.original.machine?.name ?? '—'}>{row.original.machine?.name ?? '—'}</span>
        ),
        size: 140,
      },
      {
        accessorKey: 'createdAt',
        header: 'Submitted',
        cell: ({ getValue }) => formatDate(getValue() as string | undefined),
        size: 140,
      },
      // --- Power columns (hidden by default) ---
      {
        accessorKey: 'gitBranch',
        header: 'Branch',
        cell: ({ getValue }) => (
          <span className="inline-block max-w-[12ch] truncate" title={String(getValue() ?? '')}>
            {String(getValue() ?? '—')}
          </span>
        ),
        size: 140,
        enableHiding: true,
        meta: { isAdvanced: true },
      },
      {
        accessorKey: 'gitCommitHash',
        header: 'Git Hash',
        cell: ({ getValue }) => (
          <span className="font-mono" title={String(getValue() ?? '')}>
            {String(getValue() ?? '').slice(0, 7) || '—'}
          </span>
        ),
        size: 120,
        enableHiding: true,
        meta: { isAdvanced: true },
      },
      {
        id: 'runDates',
        header: 'Run Dates',
        accessorFn: (r) =>
          r.runStartDate || r.runEndDate
            ? `${formatDate(r.runStartDate ?? undefined)} → ${formatDate(r.runEndDate ?? undefined)}`
            : '—',
        cell: ({ getValue }) => <span>{getValue() as string}</span>,
        size: 220,
        enableHiding: true,
        meta: { isAdvanced: true },
      },
      {
        accessorKey: 'lastUpdatedAt',
        header: 'Last Updated',
        cell: ({ row }) => (
          <span title={`by ${row.original.lastUpdatedBy || '—'}`}>
            {formatDate(row.original.updatedAt ?? undefined)}
          </span>
        ),
        size: 170,
        enableHiding: true,
        meta: { isAdvanced: true },
      },
    ],
    [],
  );

  const table = useReactTable({
    data: simulations,
    columns,
    state: { globalFilter, sorting, columnVisibility },
    onSortingChange: setSorting,
    onColumnVisibilityChange: setColumnVisibility,
    globalFilterFn: (row, _id, value) => {
      if (!value) return true;
      const v = String(value).toLowerCase();
      const s: SimulationOut = row.original as SimulationOut;
      return [s.id, s.name, s.gitTag, s.gridName, s.compset, s.machineId]
        .filter(Boolean)
        .some((field) => String(field).toLowerCase().includes(v));
    },
    getCoreRowModel: getCoreRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
  });

  // Select all in current page helper
  const toggleAllOnPage = (checked: boolean | 'indeterminate') => {
    const bool = checked === true;
    const pageRows = table.getRowModel().rows;
    const next = { ...selectedRows };
    pageRows.forEach((r) => (next[r.original.id] = bool));
    setSelectedRows(next);
  };

  return (
    <div className="mx-auto w-full max-w-[1600px] px-8 py-8 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">All Simulations</h1>
          <p className="text-gray-600 text-sm">
            Complete catalog. Use search, filters, and sorting to locate specific runs.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <Button variant="outline" onClick={() => navigate('/upload')}>
            Upload to Catalog
          </Button>
        </div>
      </div>

      {/* Filter & Search Controls */}
      <div className="flex flex-wrap gap-3 items-center bg-muted p-4 rounded-md">
        <Input
          placeholder="Search by ID, name, version, grid, compset, machine, or variable…"
          value={globalFilter}
          onChange={(e) => setGlobalFilter(e.target.value)}
          className="w-[500px]"
        />
        {/* Column visibility quick presets */}
        <div className="ml-auto flex items-center gap-2 text-sm">
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="outline" size="sm">
                Columns
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-56">
              <DropdownMenuLabel>Toggle columns</DropdownMenuLabel>
              <DropdownMenuSeparator />
              {table.getAllLeafColumns().map((column) => {
                if (!column.getCanHide()) return null;
                return (
                  <DropdownMenuCheckboxItem
                    key={column.id}
                    className="capitalize"
                    checked={column.getIsVisible()}
                    onCheckedChange={(v) => column.toggleVisibility(Boolean(v))}
                  >
                    {String(column.columnDef.header ?? column.id)}
                  </DropdownMenuCheckboxItem>
                );
              })}
            </DropdownMenuContent>
          </DropdownMenu>
          <span className="text-muted-foreground hidden sm:inline">View:</span>
          <Button
            variant={viewMode === 'simple' ? 'default' : 'secondary'}
            size="sm"
            onClick={() => {
              setViewMode('simple');
              setColumnVisibility({
                gitCommitHash: false,
                gitBranch: false,
                runDates: false,
                lastUpdatedAt: false,
              });
            }}
            title="Hide advanced columns (Git, Branch, Run Date, Edited)"
          >
            Simple
          </Button>
          <Button
            variant={viewMode === 'advanced' ? 'default' : 'secondary'}
            size="sm"
            onClick={() => {
              setViewMode('advanced');
              setColumnVisibility({
                gitCommitHash: true,
                gitBranch: true,
                runDates: true,
                lastUpdatedAt: true,
              });
            }}
            title="Show advanced columns (Git, Branch, Run Date, Edited)"
          >
            Advanced
          </Button>
        </div>
      </div>

      {/* Main Table */}
      <div className="overflow-auto rounded-md border bg-background relative">
        <Table>
          <TableHeader className="sticky top-0 bg-background z-20">
            {table.getHeaderGroups().map((headerGroup) => (
              <TableRow key={headerGroup.id}>
                {/* Sticky select-all column */}
                <TableHead className="w-10 sticky left-0 z-30 bg-background border-r">
                  <Checkbox
                    checked={
                      table.getRowModel().rows.length > 0 &&
                      table.getRowModel().rows.every((r) => selectedRows[r.original.id])
                    }
                    onCheckedChange={toggleAllOnPage}
                    aria-label="Select all on page"
                  />
                </TableHead>
                {headerGroup.headers.map((header) => {
                  const isName = header.column.id === 'name';
                  const isAdvanced = header.column.columnDef.meta?.isAdvanced;
                  return (
                    <TableHead
                      key={header.id}
                      className={cn(
                        'whitespace-nowrap',
                        isName && 'sticky left-10 z-20 bg-background border-r',
                        isAdvanced && columnVisibility[header.column.id] && 'bg-blue-100',
                      )}
                    >
                      {header.isPlaceholder ? null : (
                        <div
                          className={cn(
                            'select-none',
                            header.column.getCanSort() && 'cursor-pointer',
                          )}
                          onClick={header.column.getToggleSortingHandler?.()}
                          title={
                            header.column.getIsSorted() === 'asc'
                              ? 'Sorted ascending'
                              : header.column.getIsSorted() === 'desc'
                                ? 'Sorted descending'
                                : 'Click to sort'
                          }
                        >
                          {String(header.column.columnDef.header ?? header.column.id)}
                          {header.column.getIsSorted() === 'asc' && ' ▲'}
                          {header.column.getIsSorted() === 'desc' && ' ▼'}
                        </div>
                      )}
                    </TableHead>
                  );
                })}
              </TableRow>
            ))}
          </TableHeader>
          <TableBody>
            {table.getRowModel().rows.map((row) => (
              <TableRow
                key={row.id}
                className="hover:bg-muted/40 cursor-pointer"
                onClick={() => navigate(`/simulations/${row.original.id}`)}
              >
                {/* Sticky checkbox cell */}
                <TableCell
                  className="w-10 sticky left-0 z-10 bg-background border-r"
                  onClick={(e) => e.stopPropagation()}
                >
                  <Checkbox
                    checked={!!selectedRows[row.original.id]}
                    onCheckedChange={(checked) =>
                      setSelectedRows((prev) => ({ ...prev, [row.original.id]: checked === true }))
                    }
                    aria-label="Select row"
                  />
                </TableCell>
                {row.getVisibleCells().map((cell) => {
                  const isName = cell.column.id === 'name';
                  const isAdvanced = cell.column.columnDef.meta?.isAdvanced;
                  return (
                    <TableCell
                      key={cell.id}
                      className={cn(
                        'whitespace-nowrap',
                        isName && 'sticky left-10 z-[5] bg-background border-r',
                        isAdvanced && columnVisibility[cell.column.id] && 'bg-blue-50',
                      )}
                    >
                      {typeof cell.column.columnDef.cell === 'function'
                        ? cell.column.columnDef.cell(cell.getContext())
                        : ((cell.getValue() as unknown) ?? '—')}
                    </TableCell>
                  );
                })}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>

      {/* Footer / Pagination */}
      <div className="flex items-center justify-between py-2 text-sm text-muted-foreground">
        <div>
          Showing {table.getRowModel().rows.length} of {simulations.length}
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
            Page {table.getState().pagination.pageIndex + 1} of {table.getPageCount()}
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
