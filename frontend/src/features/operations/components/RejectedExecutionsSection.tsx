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
import { formatRejectionError, formatUtc } from '@/features/operations/operationsUtils';
import type { RejectedExecutionsResponse } from '@/features/operations/types';

const COLUMNS = [
  { label: 'Site', className: 'w-[8%]' },
  { label: 'Reason', className: 'w-[10%]' },
  { label: 'Error', className: 'w-[22%]' },
  { label: 'Executions', className: 'w-[9%] text-right' },
  { label: 'Cases', className: 'w-[7%] text-right' },
  { label: 'New in range', className: 'w-[9%] text-right' },
  { label: 'Latest (UTC)', className: 'w-[13%]' },
  { label: 'Example' },
];

const OUTCOME_LABELS = {
  rejected_incomplete: 'Incomplete',
  rejected_invalid: 'Invalid',
};

interface RejectedExecutionsSectionProps {
  query: UseQueryResult<RejectedExecutionsResponse>;
  rangeDays: number;
  /** Whether filters that apply to this section are active. */
  filtered: boolean;
}

export const RejectedExecutionsSection = ({
  query,
  rangeDays,
  filtered,
}: RejectedExecutionsSectionProps) => (
  <OperationsSection
    title="Rejected Executions"
    description={`Current rejections grouped by first validation error; "new" means first detected in the last ${rangeDays} days.`}
    icon={FileWarning}
    query={query}
    badge={(data) => <CountPill count={data.total} label="rejected" />}
  >
    {(data) => (
      <OperationsTable columns={COLUMNS} className="min-w-[960px] table-fixed">
        {data.groups.map((group) => {
          const { example } = group;
          const error = formatRejectionError(group);

          return (
            <TableRow
              key={JSON.stringify([group.site_name, group.outcome, group.code, group.target])}
            >
              <TableCell>{group.site_name}</TableCell>
              <TableCell>{OUTCOME_LABELS[group.outcome]}</TableCell>
              <TableCell>
                <span
                  className="line-clamp-2 break-all font-mono text-xs"
                  title={example.message ?? undefined}
                >
                  {error}
                </span>
              </TableCell>
              <TableCell className="text-right">{group.executions}</TableCell>
              <TableCell className="text-right">{group.cases}</TableCell>
              <TableCell className="text-right">{group.new_in_range}</TableCell>
              <TableCell>{formatUtc(group.latest_detected_at)}</TableCell>
              <TableCell>
                <TableCellText
                  value={`${example.case_identity} / ${example.execution_id} (${example.machine_name})`}
                  lines={2}
                  mono
                  fullValueMode="tooltip"
                />
              </TableCell>
            </TableRow>
          );
        })}
        {data.groups.length === 0 ? (
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
    )}
  </OperationsSection>
);
