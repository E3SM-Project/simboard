import type { UseQueryResult } from '@tanstack/react-query';
import { FileWarning } from 'lucide-react';

import { TableCell, TableRow } from '@/components/ui/table';
import { TableCellText } from '@/components/ui/table-cell-text';
import {
  CountPill,
  EmptyRow,
  OperationsSection,
  OperationsTable,
} from '@/features/operations/components/OperationsSection';
import { formatRejectionErrors } from '@/features/operations/operationsUtils';
import type { RejectedExecutionsResponse } from '@/features/operations/types';

const COLUMNS = [
  { label: 'Execution ID', className: 'w-[18%]' },
  { label: 'Case', className: 'w-[26%]' },
  { label: 'Machine', className: 'w-[12%]' },
  { label: 'Reason', className: 'w-[12%]' },
  { label: 'Validation errors' },
];

const OUTCOME_LABELS = {
  rejected_incomplete: 'Incomplete',
  rejected_invalid: 'Invalid',
};

interface RejectedExecutionsSectionProps {
  query: UseQueryResult<RejectedExecutionsResponse>;
  /** Whether filters that apply to this section are active. */
  filtered: boolean;
}

export const RejectedExecutionsSection = ({ query, filtered }: RejectedExecutionsSectionProps) => (
  <OperationsSection
    title="Rejected Executions"
    description="Executions currently rejected as incomplete or invalid by the latest validation."
    icon={FileWarning}
    query={query}
    badge={(data) => <CountPill count={data.total} label="rejected" />}
  >
    {(data) => (
      <div className="space-y-2">
        <OperationsTable columns={COLUMNS} className="min-w-[760px] table-fixed">
          {data.executions.map((row) => (
            <TableRow key={`${row.machine_name}|${row.case_identity}|${row.execution_id}`}>
              <TableCell>
                <TableCellText value={row.execution_id} mono />
              </TableCell>
              <TableCell>
                <TableCellText value={row.case_identity} mono fullValueMode="tooltip" />
              </TableCell>
              <TableCell>{row.machine_name}</TableCell>
              <TableCell>{OUTCOME_LABELS[row.outcome]}</TableCell>
              <TableCell>
                <TableCellText
                  value={formatRejectionErrors(row.errors)}
                  lines={2}
                  fullValueMode="tooltip"
                />
              </TableCell>
            </TableRow>
          ))}
          {data.executions.length === 0 ? (
            <EmptyRow
              colSpan={COLUMNS.length}
              message={
                filtered
                  ? 'No rejected executions match these filters.'
                  : 'No executions are currently rejected.'
              }
            />
          ) : null}
        </OperationsTable>
        {data.executions.length < data.total ? (
          <p className="text-xs text-muted-foreground">
            Showing {data.executions.length} of {data.total} rejected executions.
          </p>
        ) : null}
      </div>
    )}
  </OperationsSection>
);
