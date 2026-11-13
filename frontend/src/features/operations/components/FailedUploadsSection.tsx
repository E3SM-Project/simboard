import type { UseQueryResult } from '@tanstack/react-query';
import { CloudAlert } from 'lucide-react';

import { TableCell, TableRow } from '@/components/ui/table';
import { TableCellText } from '@/components/ui/table-cell-text';
import {
  CountPill,
  EmptyPanel,
  EmptyRow,
  OperationsSection,
  OperationsTable,
} from '@/features/operations/components/OperationsSection';
import {
  filterJobs,
  getDailyFailureRows,
  getFailedUploads,
  UPLOAD_FAILURE_CATEGORY_LABELS,
} from '@/features/operations/operationsUtils';
import type { JobType, ScheduledJobHealthResponse } from '@/features/operations/types';

const CASE_COLUMNS = [
  { label: 'Case', className: 'w-[30%]' },
  { label: 'Job', className: 'w-[18%]' },
  { label: 'HTTP', className: 'w-[9%]' },
  { label: 'Attempts', className: 'w-[10%] text-right' },
  { label: 'Message' },
];

interface FailedUploadsSectionProps {
  query: UseQueryResult<ScheduledJobHealthResponse>;
  jobType?: JobType;
  dateWindow: { startDate: string; endDate: string };
  rangeDays: number;
  onResetFilters?: () => void;
}

export const FailedUploadsSection = ({
  query,
  jobType,
  dateWindow,
  rangeDays,
  onResetFilters,
}: FailedUploadsSectionProps) => (
  <OperationsSection
    title="Failed Uploads"
    description="Cases whose uploads still failed after retries in each job's latest upload run."
    icon={CloudAlert}
    query={query}
    badge={(data) => (
      <CountPill>{getFailedUploads(filterJobs(data.jobs, jobType)).total} failed uploads</CountPill>
    )}
  >
    {(data) => {
      const { rows, truncatedJobs } = getFailedUploads(filterJobs(data.jobs, jobType));
      const daily = getDailyFailureRows(data.upload_failure_daily_counts, dateWindow);
      const dailyColumns = [
        { label: 'Date (UTC)' },
        { label: 'Machine' },
        ...daily.categories.map((category) => ({
          label: UPLOAD_FAILURE_CATEGORY_LABELS[category],
          className: 'text-right',
        })),
        { label: 'Total', className: 'text-right' },
      ];

      if (rows.length === 0 && daily.rows.length === 0) {
        return (
          <EmptyPanel
            message={
              onResetFilters
                ? 'No failed uploads match these filters.'
                : `No failed uploads in the latest runs or the last ${rangeDays} days.`
            }
            onResetFilters={onResetFilters}
          />
        );
      }

      return (
        <div className="space-y-6">
          <div className="space-y-2">
            <OperationsTable columns={CASE_COLUMNS} className="min-w-[760px] table-fixed">
              {rows.map((row) => (
                <TableRow key={`${row.jobId}|${row.case_path}`}>
                  <TableCell>
                    <TableCellText value={row.case_path} mono fullValueMode="tooltip" />
                  </TableCell>
                  <TableCell>
                    <TableCellText value={row.jobId} mono />
                  </TableCell>
                  <TableCell>{row.status_code ?? 'Network'}</TableCell>
                  <TableCell className="text-right">{row.attempts}</TableCell>
                  <TableCell>
                    <TableCellText value={row.message} lines={2} fullValueMode="tooltip" />
                  </TableCell>
                </TableRow>
              ))}
              {rows.length === 0 ? (
                <EmptyRow
                  colSpan={CASE_COLUMNS.length}
                  message={
                    onResetFilters
                      ? 'No failed uploads match these filters.'
                      : 'No failed uploads in the latest runs.'
                  }
                  onResetFilters={onResetFilters}
                />
              ) : null}
            </OperationsTable>
            {truncatedJobs.map(({ jobId, shown, total }) => (
              <p key={jobId} className="text-xs text-muted-foreground">
                Showing {shown} of {total} failed cases for{' '}
                <span className="font-mono">{jobId}</span>.
              </p>
            ))}
          </div>

          <div className="space-y-2">
            <h3 className="text-sm font-semibold">Daily failure counts</h3>
            <p className="text-xs text-muted-foreground">
              Failed case uploads by report day and category, for all job types.
            </p>
            <OperationsTable columns={dailyColumns}>
              {daily.rows.map((row) => (
                <TableRow key={`${row.day}|${row.machineName}`}>
                  <TableCell>{row.day}</TableCell>
                  <TableCell>{row.machineName}</TableCell>
                  {daily.categories.map((category) => (
                    <TableCell key={category} className="text-right">
                      {row.counts[category] ?? 0}
                    </TableCell>
                  ))}
                  <TableCell className="text-right font-medium">{row.total}</TableCell>
                </TableRow>
              ))}
              {daily.rows.length === 0 ? (
                <EmptyRow
                  colSpan={dailyColumns.length}
                  message={`No failed uploads in the last ${rangeDays} days.`}
                />
              ) : null}
            </OperationsTable>
          </div>
        </div>
      );
    }}
  </OperationsSection>
);
