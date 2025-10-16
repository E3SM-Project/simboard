import { flexRender, getCoreRowModel, useReactTable } from '@tanstack/react-table';
import { ColumnDef } from '@tanstack/react-table';
import { ArrowRight, Check, GitBranch } from 'lucide-react';
import { useNavigate } from 'react-router-dom';

import { Button } from '@/components/ui/button';
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
      accessorKey: 'name',
      header: 'Name',
      cell: (info) => info.getValue() || 'N/A',
    },
    {
      accessorKey: 'campaignId',
      header: 'Campaign',
      cell: (info) => info.getValue() || 'N/A',
    },
    {
      accessorKey: 'simulationStartDate',
      header: 'Sim Start Date',
      cell: (info) => {
        const value = info.getValue();
        return value ? new Date(value as string).toLocaleDateString() : 'N/A';
      },
    },
    {
      accessorKey: 'simulationEndDate',
      header: 'Sim End Date',
      cell: (info) => {
        const value = info.getValue();
        return value ? new Date(value as string).toLocaleDateString() : 'N/A';
      },
    },
    {
      id: 'versionOrHash',
      header: 'Version / Git Hash',
      cell: (info) => {
        const sim = info.row.original;
        return sim.simulationType === 'production'
          ? sim.gitTag || 'N/A'
          : sim.gitCommitHash || 'N/A';
      },
    },
    {
      accessorKey: 'createdAt',
      header: 'Upload Date',
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
    <table style={{ width: '100%', borderCollapse: 'collapse' }}>
      <thead>
        {table.getHeaderGroups().map((headerGroup) => (
          <tr key={headerGroup.id}>
            {headerGroup.headers.map((header) => (
              <th
                key={header.id}
                style={{
                  borderBottom: '1px solid #ddd',
                  padding: '8px',
                  textAlign: 'left',
                  background: '#f9f9f9',
                }}
              >
                {header.isPlaceholder
                  ? null
                  : flexRender(header.column.columnDef.header, header.getContext())}
              </th>
            ))}
          </tr>
        ))}
      </thead>
      <tbody>
        {table.getRowModel().rows.map((row) => (
          <tr key={row.id}>
            {row.getVisibleCells().map((cell) => (
              <td
                key={cell.id}
                style={{
                  borderBottom: '1px solid #eee',
                  padding: '8px',
                }}
              >
                {flexRender(cell.column.columnDef.cell, cell.getContext())}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
};

export default LatestSimulationsTable;
