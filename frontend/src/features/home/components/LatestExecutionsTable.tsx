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
import { executionDetailsPath } from '@/lib/catalog/urls';
import type { ExecutionOut } from '@/types/index';

const simulationTypeIcon = (execution: ExecutionOut) => {
  if (execution.simulationType === 'production') {
    return (
      <span title="Production" className="inline-flex items-center gap-1.5 text-foreground">
        <Check className="h-4 w-4" />
        Production
      </span>
    );
  }
  return (
    <span title="Master" className="inline-flex items-center gap-1.5 text-foreground">
      <GitBranch className="h-4 w-4" />
      Master
    </span>
  );
};

interface LatestExecutionsTableProps {
  latestExecutions: ExecutionOut[];
}

const LatestExecutionsTable = ({ latestExecutions }: LatestExecutionsTableProps) => {
  const navigate = useNavigate();

  const tableColumns: ColumnDef<ExecutionOut>[] = [
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
          onClick={() =>
            navigate(
              executionDetailsPath({
                machineName: info.row.original.machine.name,
                hpcUsername: info.row.original.hpcUsername,
                caseName: info.row.original.caseName,
                executionId: info.row.original.executionId,
              }),
            )
          }
          aria-label="Details"
          className="h-8 w-8 p-0 text-muted-foreground"
        >
          <ArrowRight className="h-4 w-4" />
        </Button>
      ),
      enableSorting: false,
      enableColumnFilter: false,
    },
  ];

  const table = useReactTable({
    data: latestExecutions,
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
                className="bg-muted/30 text-xs font-medium uppercase tracking-wide text-muted-foreground"
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

export default LatestExecutionsTable;
