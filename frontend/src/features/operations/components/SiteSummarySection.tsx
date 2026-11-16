import type { UseQueryResult } from '@tanstack/react-query';
import { LayoutGrid } from 'lucide-react';
import { Link } from 'react-router-dom';

import { Button } from '@/components/ui/button';
import { TableCell, TableRow } from '@/components/ui/table';
import {
  EmptyRow,
  OperationsSection,
  OperationsTable,
} from '@/features/operations/components/OperationsSection';
import {
  getSiteSummaryRows,
  type ProblemStatus,
  type SiteSummaryRow,
  UNKNOWN_SITE,
} from '@/features/operations/operationsUtils';
import type {
  IngestionSummaryResponse,
  RejectedExecutionsResponse,
  ScheduledJobHealthResponse,
} from '@/features/operations/types';
import type { Machine } from '@/types/machine';

const COLUMNS = [
  { label: 'Site', className: 'w-[14%]' },
  { label: 'Jobs', className: 'w-[22%]' },
  { label: 'Updated cases', className: 'text-right' },
  { label: 'New executions', className: 'text-right' },
  { label: 'Last new execution' },
  { label: 'Rejected (new / total)', className: 'text-right' },
  { label: 'Failed uploads', className: 'text-right' },
];

const PROBLEM_LABELS: Record<ProblemStatus, string> = {
  failed: 'failed',
  stale: 'stale',
  never_reported: 'never reported',
};

interface SummaryData {
  jobs: ScheduledJobHealthResponse;
  summary: IngestionSummaryResponse;
  rejected: RejectedExecutionsResponse;
}

interface SiteSummarySectionProps {
  queries: [
    UseQueryResult<ScheduledJobHealthResponse>,
    UseQueryResult<IngestionSummaryResponse>,
    UseQueryResult<RejectedExecutionsResponse>,
  ];
  machines: Machine[];
  rangeDays: number;
  /** Whether filters that apply to this section are active. */
  filtered: boolean;
  onSelectSite: (siteName: string) => void;
}

/** One row per site, so a problem at any site is visible without scrolling. */
export const SiteSummarySection = ({
  queries,
  machines,
  rangeDays,
  filtered,
  onSelectSite,
}: SiteSummarySectionProps) => {
  const [jobs, summary, rejected] = queries;
  const failed = queries.find((query) => query.isError);
  const query = {
    data:
      jobs.data && summary.data && rejected.data
        ? { jobs: jobs.data, summary: summary.data, rejected: rejected.data }
        : undefined,
    error: failed?.error ?? null,
    isError: Boolean(failed),
    isFetching: queries.some((item) => item.isFetching),
    refetch: () => Promise.all(queries.map((item) => item.refetch())),
  };

  return (
    <OperationsSection<SummaryData>
      title="Site Summary"
      description={`Current job status and problems per site; ingestions and new rejections over the last ${rangeDays} days.`}
      icon={LayoutGrid}
      query={query}
      actions={
        <Link to="/cases" className="text-sm text-blue-600 hover:underline">
          View cases
        </Link>
      }
    >
      {(data) => {
        const rows = getSiteSummaryRows({
          machines,
          jobs: data.jobs.jobs,
          ingestions: data.summary.rows,
          rejections: data.rejected.groups,
        });

        return (
          <OperationsTable columns={COLUMNS} className="min-w-[760px]">
            {rows.map((row) => (
              <TableRow key={row.siteName}>
                <TableCell>
                  {row.siteName === UNKNOWN_SITE ? (
                    <span className="font-medium" title="Machines missing from the machine list">
                      {row.siteName}
                    </span>
                  ) : (
                    <Button
                      type="button"
                      variant="link"
                      className="h-auto p-0 font-medium"
                      title={`Show only ${row.siteName}`}
                      onClick={() => onSelectSite(row.siteName)}
                    >
                      {row.siteName}
                    </Button>
                  )}
                </TableCell>
                <TableCell>
                  <JobCounts row={row} />
                </TableCell>
                <TableCell className="text-right" title="Cases with new executions">
                  {row.distinctCases}
                </TableCell>
                <TableCell className="text-right">{row.newExecutions}</TableCell>
                <TableCell>{row.lastNewExecutionDay ?? 'None in range'}</TableCell>
                <TableCell className="text-right">
                  {row.rejectedNew} / {row.rejectedTotal}
                </TableCell>
                <TableCell className="text-right">{row.failedUploads}</TableCell>
              </TableRow>
            ))}
            {rows.length === 0 ? (
              <EmptyRow
                colSpan={COLUMNS.length}
                message={
                  filtered ? 'No activity matches these filters.' : 'No site has jobs or data yet.'
                }
              />
            ) : null}
          </OperationsTable>
        );
      }}
    </OperationsSection>
  );
};

/** Healthy and running jobs count as OK; only problems are colored. */
const JobCounts = ({ row }: { row: SiteSummaryRow }) => {
  const problems = Object.entries(row.problemCounts) as [ProblemStatus, number][];
  if (row.jobCount === 0) return <span className="text-muted-foreground">No jobs</span>;
  if (problems.length === 0) return <span>{`${row.jobCount}/${row.jobCount} OK`}</span>;

  return (
    <span className="font-medium text-red-700">
      {problems.map(([status, count]) => `${count} ${PROBLEM_LABELS[status]}`).join(' · ')}
    </span>
  );
};
