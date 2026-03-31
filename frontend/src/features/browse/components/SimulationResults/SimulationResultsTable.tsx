import type {
  Column,
  ColumnDef,
  ColumnFiltersState,
  Row,
  SortingState,
  VisibilityState,
} from '@tanstack/react-table';
import {
  flexRender,
  getCoreRowModel,
  getFilteredRowModel,
  getSortedRowModel,
  useReactTable,
} from '@tanstack/react-table';
import { ArrowUpDown } from 'lucide-react';
import { useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';

import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { TableCellText } from '@/components/ui/table-cell-text';
import { BrowseToolbar } from '@/features/browse/components/BrowseToolbar';
import { SimulationBrowseDetailsDialog } from '@/features/browse/components/SimulationResults/SimulationBrowseDetailsDialog';
import type { SimulationOut } from '@/types/index';

// Max number of rows that can be selected at once.
const MAX_SELECTION = 5;

const renderSortableHeader = (label: string) =>
  function SortableHeader({
    column,
  }: {
    column: {
      toggleSorting: () => void;
      getIsSorted: () => false | 'asc' | 'desc';
    };
  }) {
    const isSorted = column.getIsSorted();

    return (
      <Button
        variant="ghost"
        size="sm"
        onClick={() => column.toggleSorting()}
        className={`h-8 px-2 text-sm font-semibold ${
          isSorted
            ? 'bg-slate-100 text-slate-950 shadow-[inset_0_0_0_1px_rgba(148,163,184,0.3)]'
            : 'text-slate-500'
        } hover:bg-slate-100 hover:text-slate-950`}
      >
        {label}
        <ArrowUpDown className={`h-4 w-4 ${isSorted ? 'opacity-100' : 'opacity-50'}`} />
      </Button>
    );
  };

interface SimulationResultsTable {
  simulations: SimulationOut[];
  filteredData: SimulationOut[];
  page: number;
  pageSize: number;
  selectedSimulationIds: string[];
  setSelectedSimulationIds: (ids: string[]) => void;
  handleCompareButtonClick: () => void;
  columnVisibility: VisibilityState;
  setColumnVisibility: (
    updater: VisibilityState | ((old: VisibilityState) => VisibilityState),
  ) => void;
}

const shouldIgnoreRowSelection = (target: EventTarget | null): boolean =>
  target instanceof Element &&
  Boolean(target.closest('button, a, input, [role="button"], [data-prevent-selection]'));

const SimulationTableActions = ({ simulation }: { simulation: SimulationOut }) => {
  const navigate = useNavigate();
  const location = useLocation();
  const currentPath = `${location.pathname}${location.search}`;

  return (
    <div className="flex items-center justify-end gap-2" data-prevent-selection="true">
      <SimulationBrowseDetailsDialog
        simulation={simulation}
        triggerSize="sm"
        triggerClassName="h-9 rounded-lg border-slate-200 bg-white text-slate-700 hover:bg-slate-50"
      />
      <Button
        variant="outline"
        size="sm"
        data-prevent-selection="true"
        className="h-9 rounded-lg border-slate-200 bg-white text-slate-700 hover:bg-slate-50"
        onClick={(event) => {
          event.stopPropagation();
          navigate(`/simulations/${simulation.id}`, { state: { from: currentPath } });
        }}
      >
        All Details
      </Button>
    </div>
  );
};

const columns: ColumnDef<SimulationOut>[] = [
  {
    id: 'select',
    header: () => null,
    cell: ({ row }) => (
      <Checkbox
        checked={row.getIsSelected()}
        onCheckedChange={(value) => row.toggleSelected(!!value)}
        aria-label="Select row"
      />
    ),
    enableSorting: false,
    enableHiding: false,
    meta: { sticky: true, width: 50, position: 'left' },
  },
  {
    accessorKey: 'caseName',
    header: renderSortableHeader('Case Name'),
    cell: ({ row }) => (
      <TableCellText value={row.original.caseName} className="font-medium text-slate-950" />
    ),
    enableSorting: true,
    meta: { sticky: true, width: 320, position: 'left' },
  },
  {
    accessorKey: 'executionId',
    header: renderSortableHeader('Execution ID'),
    cell: ({ row }) => (
      <TableCellText
        value={row.original.executionId}
        mono
        className="font-medium text-slate-800"
      />
    ),
    enableSorting: true,
    meta: { width: 220 },
  },
  {
    accessorKey: 'isReference',
    header: renderSortableHeader('Reference'),
    cell: ({ row }) => {
      const isReference = row.original.isReference;
      const changeCount = row.original.changeCount;
      return (
        <div>
          {isReference ? 'Yes' : 'No'}
          {!isReference && changeCount > 0 && (
            <span className="ml-1 text-slate-400">({changeCount})</span>
          )}
        </div>
      );
    },
    enableSorting: true,
    meta: { width: 110 },
  },
  {
    accessorKey: 'campaign',
    header: renderSortableHeader('Campaign'),
    cell: ({ row }) => <TableCellText value={row.original.campaign} className="text-slate-600" />,
    enableSorting: true,
    meta: { width: 280 },
  },
  {
    accessorKey: 'experimentType',
    header: renderSortableHeader('Experiment'),
    cell: ({ row }) => (
      <TableCellText value={row.original.experimentType} className="text-slate-600" />
    ),
    enableSorting: true,
    meta: { width: 180 },
  },
  {
    accessorKey: 'gitTag',
    header: renderSortableHeader('Version Tag'),
    cell: ({ row }) => <TableCellText value={row.original.gitTag} className="text-slate-600" />,
    enableSorting: true,
    meta: { width: 180 },
  },
  {
    accessorKey: 'simulationStartDate',
    header: renderSortableHeader('Model Start Date'),
    cell: ({ row }) => {
      const start = row.original.simulationStartDate;
      return start ? (
        <span>{start}</span>
      ) : (
        <span className="text-muted-foreground italic">N/A</span>
      );
    },
    enableSorting: true,
    meta: { width: 150 },
  },
  {
    accessorKey: 'simulationEndDate',
    header: renderSortableHeader('Model End Date'),
    cell: ({ row }) => {
      const end = row.original.simulationEndDate;
      return end ? <span>{end}</span> : <span className="text-muted-foreground italic">N/A</span>;
    },
    enableSorting: true,
    meta: { width: 150 },
  },
  {
    accessorKey: 'ensembleMember',
    header: renderSortableHeader('Ensemble Member'),
    cell: ({ getValue }) => <TableCellText value={String(getValue() ?? '—')} />,
    enableSorting: true,
    meta: { width: 160 },
  },
  {
    accessorKey: 'gridResolution',
    header: renderSortableHeader('Grid Resolution'),
    cell: ({ row }) => <TableCellText value={row.original.gridResolution} />,
    enableSorting: true,
    meta: { width: 180 },
  },
  {
    accessorKey: 'compset',
    header: renderSortableHeader('Component Set'),
    cell: ({ row }) => <TableCellText value={row.original.compset} />,
    enableSorting: true,
    enableHiding: true,
    meta: { width: 220 },
  },
  {
    accessorKey: 'gridName',
    header: renderSortableHeader('Grid Name'),
    cell: ({ row }) => <TableCellText value={row.original.gridName} />,
    enableSorting: true,
    enableHiding: true,
    meta: { width: 180 },
  },
  {
    id: 'actions',
    enableHiding: false,
    cell: ({ row }) => <SimulationTableActions simulation={row.original} />,
    enableSorting: false,
    meta: { sticky: true, width: 220, position: 'right' },
  },
];

// Converts an array of IDs into a row selection object.
// Each ID becomes a key with a value of true, indicating selection.
//
// @param ids - Array of row IDs to select
// @returns An object mapping each ID to true
const idsToRowSelection = (ids: string[]): Record<string, boolean> =>
  Object.fromEntries(ids.map((id) => [id, true]));

/**
 * Limits the row selection to a maximum number of rows.
 * @param selection The current row selection object.
 * @param max The maximum number of rows that can be selected.
 * @returns A new selection object limited to the specified max.
 */
const limitRowSelection = (
  selection: Record<string, boolean>,
  max: number,
): Record<string, boolean> => {
  const selectedIds = Object.keys(selection).filter((id) => selection[id]);
  if (selectedIds.length <= max) return selection;

  const limitedSelection = { ...selection };
  selectedIds.slice(max).forEach((id) => {
    limitedSelection[id] = false;
  });

  return limitedSelection;
};

/**
 * Calculates the left offset for a sticky column or header in a table.
 *
 * This function determines the cumulative width of all sticky columns
 * to the left of the specified column or header, ensuring proper alignment
 * for sticky positioning in a table.
 *
 * @param headerOrCell - The header or cell object containing the column information.
 * @param headerOrCell.column.id - The unique identifier of the column.
 * @param headerOrCell.column.columnDef.meta - Metadata for the column, including sticky and width properties.
 * @param headerOrCell.column.columnDef.meta.sticky - Indicates if the column is sticky.
 * @param headerOrCell.column.columnDef.meta.width - The width of the column, used for calculating the offset.
 * @param table - The table object containing all leaf columns.
 * @param table.getAllLeafColumns - A function that retrieves all leaf columns in the table.
 *
 * @returns The calculated left offset for the sticky column or header.
 */
const getStickyLeftOffset = (
  headerOrCell: {
    column: { id: string; columnDef: { meta?: { sticky?: boolean; width?: number } } };
  },
  table: { getAllLeafColumns: () => Column<SimulationOut, unknown>[] },
): number => {
  const all = table.getAllLeafColumns();
  const idx = all.findIndex((c) => c.id === headerOrCell.column.id);

  let left = 0;

  for (let i = 0; i < idx; i++) {
    if (all[i].columnDef.meta?.sticky) {
      left += all[i].columnDef.meta?.width ?? 0;
    }
  }
  return left;
};

export const SimulationResultsTable = ({
  simulations,
  filteredData,
  page,
  pageSize,
  selectedSimulationIds,
  setSelectedSimulationIds,
  handleCompareButtonClick,
  columnVisibility,
  setColumnVisibility,
}: SimulationResultsTable) => {
  // -------------------- Local State --------------------
  const [sorting, setSorting] = useState<SortingState>([]);
  const [columnFilters, setColumnFilters] = useState<ColumnFiltersState>([]);

  // -------------------- Derived Data --------------------
  const rowSelection = idsToRowSelection(selectedSimulationIds);

  const renderSelectCheckbox = (row: Row<SimulationOut>) => {
    const isSelected = row.getIsSelected();
    const isDisabled =
      !isSelected && Object.values(rowSelection).filter(Boolean).length >= MAX_SELECTION;

    return (
      <Checkbox
        checked={isSelected}
        disabled={isDisabled}
        onCheckedChange={(value) => row.toggleSelected(!!value)}
        aria-label="Select row"
        onClick={(e) => e.stopPropagation()}
      />
    );
  };

  const tableColumns = columns.map((col: ColumnDef<SimulationOut>) =>
    col.id === 'select'
      ? {
          ...col,
          cell: ({ row }) => renderSelectCheckbox(row),
        }
      : col,
  ) as ColumnDef<SimulationOut>[];

  const isCompareButtonDisabled = selectedSimulationIds.length < 2;

  // -------------------- Handlers --------------------
  const handleRowSelectionChange = (
    updater: Record<string, boolean> | ((prev: Record<string, boolean>) => Record<string, boolean>),
  ) => {
    const nextRowSelection = typeof updater === 'function' ? updater(rowSelection) : updater;
    const limitedSelection = limitRowSelection(nextRowSelection, MAX_SELECTION);
    const selectedIds = Object.keys(limitedSelection).filter((id) => limitedSelection[id]);

    setSelectedSimulationIds(selectedIds);
  };

  // -------------------- Render --------------------
  const table = useReactTable({
    data: filteredData,
    columns: tableColumns,
    onSortingChange: setSorting,
    onColumnFiltersChange: setColumnFilters,
    getCoreRowModel: getCoreRowModel(),
    getRowId: (row) => row.id,
    getSortedRowModel: getSortedRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    onColumnVisibilityChange: setColumnVisibility,
    onRowSelectionChange: handleRowSelectionChange,
    state: {
      sorting,
      columnFilters,
      columnVisibility,
      rowSelection,
    },
  });

  const sortedFilteredRows = table.getRowModel().rows;
  const pageStart = (page - 1) * pageSize;
  const paginatedRows = sortedFilteredRows.slice(pageStart, pageStart + pageSize);
  const tableMinWidth = table.getVisibleLeafColumns().reduce((sum, column) => {
    const meta = column.columnDef.meta as { width?: number } | undefined;
    return sum + (meta?.width ?? 180);
  }, 0);

  return (
    <div className="w-full min-w-0">
      <div className="py-4">
        <BrowseToolbar
          simulations={simulations}
          buttonText="Compare"
          onCompareButtonClick={handleCompareButtonClick}
          selectedSimulationIds={selectedSimulationIds}
          setSelectedSimulationIds={setSelectedSimulationIds}
          isCompareButtonDisabled={isCompareButtonDisabled}
        />
      </div>

      <div className="overflow-x-auto overflow-y-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
        <Table
          className="w-full table-fixed border-separate border-spacing-0 [&_th]:whitespace-nowrap [&_td]:whitespace-nowrap"
          style={{ minWidth: tableMinWidth }}
        >
          <TableHeader className="bg-slate-50/95">
            {table.getHeaderGroups().map((hg) => (
              <TableRow key={hg.id} className="border-b border-slate-200 hover:bg-transparent">
                {hg.headers.map((header) => {
                  const meta = header.column.columnDef.meta;

                  const isSticky = meta?.sticky;
                  const left =
                    meta?.position === 'left' ? getStickyLeftOffset(header, table) : undefined;
                  const right = meta?.position === 'right' ? 0 : undefined;

                  return (
                    <TableHead
                      key={header.id}
                      className={
                        isSticky
                          ? 'sticky z-20 overflow-hidden border-b border-slate-200 bg-slate-50/95 shadow-[inset_0_-1px_0_0_rgba(226,232,240,1)]'
                          : 'overflow-hidden border-b border-slate-200 bg-slate-50/95 shadow-[inset_0_-1px_0_0_rgba(226,232,240,1)]'
                      }
                      style={{
                        left,
                        right,
                        minWidth: meta?.width,
                        maxWidth: meta?.width,
                        width: meta?.width,
                      }}
                    >
                      {header.isPlaceholder
                        ? null
                        : flexRender(header.column.columnDef.header, header.getContext())}
                    </TableHead>
                  );
                })}
              </TableRow>
            ))}
          </TableHeader>
          <TableBody>
            {paginatedRows.map((row) => (
              <TableRow
                key={row.id}
                data-state={row.getIsSelected() ? 'selected' : undefined}
                className="cursor-pointer border-b border-slate-100 hover:bg-slate-50/60 data-[state=selected]:bg-slate-50/80"
                onClick={(event) => {
                  if (shouldIgnoreRowSelection(event.target)) {
                    return;
                  }

                  const isSelected = row.getIsSelected();
                  const canSelectMore =
                    isSelected || Object.values(rowSelection).filter(Boolean).length < MAX_SELECTION;

                  if (canSelectMore) {
                    row.toggleSelected(!isSelected);
                  }
                }}
              >
                {row.getVisibleCells().map((cell) => {
                  const meta = cell.column.columnDef.meta;
                  const isSticky = meta?.sticky;
                  const left =
                    meta?.position === 'left' ? getStickyLeftOffset(cell, table) : undefined;
                  const right = meta?.position === 'right' ? 0 : undefined;

                  return (
                    <TableCell
                      key={cell.id}
                      className={
                        isSticky
                          ? 'sticky z-10 overflow-hidden bg-white align-middle text-slate-700'
                          : 'overflow-hidden align-middle text-slate-700'
                      }
                      style={{
                        left,
                        right,
                        minWidth: meta?.width,
                        maxWidth: meta?.width,
                        width: meta?.width,
                      }}
                    >
                      {flexRender(cell.column.columnDef.cell, cell.getContext())}
                    </TableCell>
                  );
                })}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>

      <div className="flex items-center justify-end space-x-2 py-4">
        <div className="flex-1 text-sm text-slate-500">
          {selectedSimulationIds.length} of {filteredData.length} row(s) selected.
        </div>
      </div>
    </div>
  );
};
