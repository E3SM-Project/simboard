import type { UseQueryResult } from '@tanstack/react-query';
import { Activity } from 'lucide-react';

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { TableCell, TableRow } from '@/components/ui/table';
import { TableCellText } from '@/components/ui/table-cell-text';
import { JobStatusBadge, JobStatusLegend } from '@/features/operations/components/JobStatusBadge';
import {
  EmptyRow,
  OperationsSection,
  OperationsTable,
} from '@/features/operations/components/OperationsSection';
import {
  filterJobs,
  formatRelative,
  formatUtc,
  getJobDetails,
  getJobDueBy,
  getJobStatus,
  type JobStatus,
} from '@/features/operations/operationsUtils';
import {
  JOB_TYPES,
  type JobType,
  type ScheduledJobHealthResponse,
} from '@/features/operations/types';

const ALL = 'all';

// Jobs needing attention come first.
const STATUS_PRIORITY: JobStatus[] = ['failed', 'stale', 'never_reported', 'running', 'healthy'];

const COLUMNS = [
  { label: 'Machine', className: 'w-[16%]' },
  { label: 'Type', className: 'w-[14%]' },
  { label: 'Status', className: 'w-[34%]' },
  { label: 'Last reported (UTC)', className: 'w-[18%]' },
  {
    label: 'Stale after (UTC)',
    className: 'w-[18%]',
    title: 'Becomes Stale if no report arrives by this time',
  },
];

interface JobHealthSectionProps {
  query: UseQueryResult<ScheduledJobHealthResponse>;
  jobType?: JobType;
  onJobTypeChange: (value: string) => void;
  /** Whether filters that apply to this section are active. */
  filtered: boolean;
}

export const JobHealthSection = ({
  query,
  jobType,
  onJobTypeChange,
  filtered,
}: JobHealthSectionProps) => (
  <OperationsSection
    title="Job Health"
    description="Latest status of each scheduled ingestion job."
    icon={Activity}
    query={query}
    actions={
      <Select value={jobType ?? ALL} onValueChange={onJobTypeChange}>
        <SelectTrigger aria-label="Job type" className="w-40">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value={ALL}>All job types</SelectItem>
          {JOB_TYPES.map((value) => (
            <SelectItem key={value} value={value} className="capitalize">
              {value}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    }
  >
    {(data) => {
      const jobs = filterJobs(data.jobs, jobType)
        .map((job) => ({ job, status: getJobStatus(job) }))
        .sort(
          (left, right) =>
            STATUS_PRIORITY.indexOf(left.status) - STATUS_PRIORITY.indexOf(right.status) ||
            left.job.machine_name.localeCompare(right.job.machine_name) ||
            left.job.scan_mode.localeCompare(right.job.scan_mode),
        );

      return (
        <div className="space-y-3">
          <OperationsTable columns={COLUMNS} className="min-w-[720px] table-fixed">
            {jobs.map(({ job, status }) => (
              <TableRow key={job.id} title={`Job ${job.id}`}>
                <TableCell>{job.machine_name}</TableCell>
                <TableCell className="capitalize">{job.scan_mode}</TableCell>
                <TableCell>
                  <JobStatusBadge status={status} />
                  {status === 'healthy' ? null : (
                    <TableCellText
                      value={getJobDetails(job)}
                      placeholder=""
                      lines={2}
                      className="mt-1 text-xs text-muted-foreground"
                    />
                  )}
                </TableCell>
                <TableCell>
                  <TimeWithAge value={job.last_reported_at} />
                </TableCell>
                <TableCell>
                  <TimeWithAge value={getJobDueBy(job)} />
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
          <JobStatusLegend />
        </div>
      );
    }}
  </OperationsSection>
);

const TimeWithAge = ({ value }: { value: string | null }) =>
  value ? (
    <span className="whitespace-nowrap">
      {formatUtc(value)} <span className="text-muted-foreground">({formatRelative(value)})</span>
    </span>
  ) : (
    <span className="text-muted-foreground">—</span>
  );
