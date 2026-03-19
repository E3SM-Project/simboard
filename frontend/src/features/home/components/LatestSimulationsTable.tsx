import { ColumnDef, flexRender, getCoreRowModel, useReactTable } from '@tanstack/react-table';
import { ArrowRight, Check, GitBranch } from 'lucide-react';
import { useNavigate } from 'react-router-dom';

import { Button } from '@/components/ui/button';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { TableCellText } from '@/components/ui/table-cell-text';
import type { SimulationOut } from '@/types/index';

const simulationTypeIcon = (sim: SimulationOut) => {
  if (sim.simulationType === 'production') {
    return (
      <span
        title="Production"
        style={{ display: 'inline-flex', alignItems: 'center', marginRight: 4 }}
      >
        <Check className="w-4 h-4" style={{ marginRight: 4 }} />
        Production
      </span>
    );
  }
  return (
    <span title="Master" style={{ display: 'inline-flex', alignItems: 'center', marginRight: 4 }}>
      <GitBranch className="w-4 h-4" style={{ marginRight: 4 }} />
      Master
    </span>
  );
};

interface LatestSimulationsTableProps {
  latestSimulations: SimulationOut[];
}

const LatestSimulationsTable = ({ latestSimulations }: LatestSimulationsTableProps) => {
  const navigate = useNavigate();

  const tableColumns: ColumnDef<SimulationOut>[] = [
    {
      accessorKey: 'executionId',
      header: 'Execution ID',
      cell: (info) => <TableCellText value={String(info.getValue() ?? 'N/A')} mono />,
    },
    {
      accessorKey: 'caseName',
      header: 'Case Name',
      cell: (info) => <TableCellText value={String(info.getValue() ?? 'N/A')} />,
    },
    {
      accessorKey: 'campaign',
      header: 'Campaign',
      cell: (info) => <TableCellText value={String(info.getValue() ?? 'N/A')} />,
    },
    {
      accessorKey: 'createdAt',
      header: 'Submitted',
      cell: (info) => {
        const value = info.getValue();
        return value ? new Date(value as string).toLocaleDateString() : 'N/A';
      },
    },
    {
      accessorKey: 'simulationType',
      header: 'Type',
      cell: (info) => simulationTypeIcon(info.row.original) || 'N/A',
    },
    {
      id: 'details',
      header: 'Details',
      cell: (info) => (
        <Button
          variant="outline"
          size="sm"
          onClick={() => navigate(`/simulations/${info.row.original.id}`)}
          aria-label="Details"
          className="p-2"
        >
          <ArrowRight className="w-4 h-4" />
        </Button>
      ),
      enableSorting: false,
      enableColumnFilter: false,
    },
  ];

  const table = useReactTable({
    data: latestSimulations,
    columns: tableColumns,
    getCoreRowModel: getCoreRowModel(),
    getRowId: (row) => row.id,
  });

  return (
    <Table className="table-fixed">
      <TableHeader>
        {table.getHeaderGroups().map((headerGroup) => (
          <TableRow key={headerGroup.id}>
            {headerGroup.headers.map((header) => (
              <TableHead
                key={header.id}
                className="bg-muted/40"
              >
                {header.isPlaceholder
                  ? null
                  : flexRender(header.column.columnDef.header, header.getContext())}
              </TableHead>
            ))}
          </TableRow>
        ))}
      </TableHeader>
      <TableBody>
        {table.getRowModel().rows.map((row) => (
          <TableRow key={row.id}>
            {row.getVisibleCells().map((cell) => (
              <TableCell key={cell.id} className="align-top">
                {flexRender(cell.column.columnDef.cell, cell.getContext())}
              </TableCell>
            ))}
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
};

export default LatestSimulationsTable;
