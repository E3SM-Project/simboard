import type { UseQueryResult } from '@tanstack/react-query';
import { Database } from 'lucide-react';
import { Link } from 'react-router-dom';

import { TableCell, TableRow } from '@/components/ui/table';
import { TableCellText } from '@/components/ui/table-cell-text';
import {
  CountPill,
  EmptyRow,
  OperationsSection,
  OperationsTable,
} from '@/features/operations/components/OperationsSection';
import type { IngestionSummaryResponse } from '@/features/operations/types';
import { caseDetailsPath } from '@/lib/catalog/urls';

const COLUMNS = [
  { label: 'Date (UTC)', className: 'w-[16%]' },
  { label: 'Machine', className: 'w-[14%]' },
  { label: 'Case' },
  { label: 'HPC user', className: 'w-[14%]' },
  { label: 'New executions', className: 'w-[16%] text-right' },
];

interface RecentIngestionsSectionProps {
  query: UseQueryResult<IngestionSummaryResponse>;
  rangeDays: number;
  onResetFilters?: () => void;
}

export const RecentIngestionsSection = ({
  query,
  rangeDays,
  onResetFilters,
}: RecentIngestionsSectionProps) => (
  <OperationsSection
    title="Recent Ingestions"
    description="New executions by UTC day, machine, and case."
    icon={Database}
    query={query}
    badge={(data) => <CountPill>{data.totals.new_executions} new executions</CountPill>}
  >
    {(data) => {
      const rows = [...data.rows].sort(
        (left, right) =>
          right.day.localeCompare(left.day) ||
          left.machine.localeCompare(right.machine) ||
          left.case_name.localeCompare(right.case_name),
      );

      return (
        <OperationsTable columns={COLUMNS} className="min-w-[680px] table-fixed">
          {rows.map((row) => (
            <TableRow key={`${row.day}|${row.case_id}`}>
              <TableCell>{row.day}</TableCell>
              <TableCell>{row.machine}</TableCell>
              <TableCell>
                <Link
                  to={caseDetailsPath({
                    machineName: row.machine,
                    hpcUsername: row.hpc_username,
                    caseName: row.case_name,
                  })}
                  className="block min-w-0 text-blue-600 hover:underline"
                >
                  <TableCellText value={row.case_name} />
                </Link>
              </TableCell>
              <TableCell>
                <TableCellText value={row.hpc_username} />
              </TableCell>
              <TableCell className="text-right">{row.new_executions}</TableCell>
            </TableRow>
          ))}
          {rows.length === 0 ? (
            <EmptyRow
              colSpan={COLUMNS.length}
              message={
                onResetFilters
                  ? 'No new executions match these filters.'
                  : `No new executions in the last ${rangeDays} days.`
              }
              onResetFilters={onResetFilters}
            />
          ) : null}
        </OperationsTable>
      );
    }}
  </OperationsSection>
);
