import type { UseQueryResult } from '@tanstack/react-query';
import { Activity } from 'lucide-react';

import { TableCell, TableRow } from '@/components/ui/table';
import { TableCellText } from '@/components/ui/table-cell-text';
import { JobStatusBadge, JobStatusTile } from '@/features/operations/components/JobStatusBadge';
import {
  EmptyRow,
  OperationsSection,
  OperationsTable,
} from '@/features/operations/components/OperationsSection';
import {
  filterJobs,
  formatUtc,
  getJobDetails,
  getJobStatus,
  JOB_STATUSES,
  type JobStatus,
} from '@/features/operations/operationsUtils';
import type { JobType, ScheduledJobHealthResponse } from '@/features/operations/types';

// Jobs needing attention come first.
const STATUS_PRIORITY: JobStatus[] = ['failed', 'stale', 'never_reported', 'running', 'healthy'];

const COLUMNS = [
  { label: 'Job', className: 'w-[22%]' },
  { label: 'Type', className: 'w-[11%]' },
  { label: 'Machine', className: 'w-[11%]' },
  { label: 'Status', className: 'w-[14%]' },
  { label: 'Last reported (UTC)', className: 'w-[16%]' },
  { label: 'Details' },
];

interface JobHealthSectionProps {
  query: UseQueryResult<ScheduledJobHealthResponse>;
  jobType?: JobType;
  /** Whether filters that apply to this section are active. */
  filtered: boolean;
}

export const JobHealthSection = ({ query, jobType, filtered }: JobHealthSectionProps) => (
  <OperationsSection
    title="Job Health"
    description="Latest status of each scheduled ingestion job."
    icon={Activity}
    query={query}
  >
    {(data) => {
      const jobs = filterJobs(data.jobs, jobType)
        .map((job) => ({ job, status: getJobStatus(job) }))
        .sort(
          (left, right) =>
            STATUS_PRIORITY.indexOf(left.status) - STATUS_PRIORITY.indexOf(right.status),
        );
      const counts = new Map<JobStatus, number>();
      jobs.forEach(({ status }) => counts.set(status, (counts.get(status) ?? 0) + 1));

      return (
        <div className="space-y-4">
          <dl className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
            {JOB_STATUSES.map((status) => (
              <JobStatusTile key={status} status={status} count={counts.get(status) ?? 0} />
            ))}
          </dl>

          <OperationsTable columns={COLUMNS} className="min-w-[760px] table-fixed">
            {jobs.map(({ job, status }) => (
              <TableRow key={job.id}>
                <TableCell>
                  <TableCellText value={job.id} mono />
                </TableCell>
                <TableCell>{job.scan_mode}</TableCell>
                <TableCell>{job.machine_name}</TableCell>
                <TableCell>
                  <JobStatusBadge status={status} />
                </TableCell>
                <TableCell>
                  <TableCellText value={formatUtc(job.last_reported_at)} />
                </TableCell>
                <TableCell>
                  <TableCellText value={getJobDetails(job)} lines={2} fullValueMode="tooltip" />
                </TableCell>
              </TableRow>
            ))}
            {jobs.length === 0 ? (
              <EmptyRow
                colSpan={COLUMNS.length}
                message={
                  filtered ? 'No jobs match these filters.' : 'No scheduled jobs have reported yet.'
                }
              />
            ) : null}
          </OperationsTable>
        </div>
      );
    }}
  </OperationsSection>
);
