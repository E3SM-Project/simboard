import { CircleCheck, CirclePlay, CircleSlash, CircleX, Clock } from 'lucide-react';
import { Fragment } from 'react';

import { Badge } from '@/components/ui/badge';
import { JOB_STATUSES, type JobStatus } from '@/features/operations/operationsUtils';
import { cn } from '@/lib/utils';

const NEUTRAL_CLASS = 'border-border bg-muted text-muted-foreground';

const JOB_STATUS_STYLES: Record<
  JobStatus,
  { label: string; Icon: typeof CircleCheck; className: string }
> = {
  healthy: {
    label: 'Healthy',
    Icon: CircleCheck,
    className: 'border-green-300 bg-green-50 text-green-900',
  },
  running: {
    label: 'Running',
    Icon: CirclePlay,
    // Blue, not the design system's in-progress amber, so it differs from Stale.
    className: 'border-blue-200 bg-blue-50 text-blue-900',
  },
  failed: { label: 'Failed', Icon: CircleX, className: 'border-red-200 bg-red-50 text-red-800' },
  stale: { label: 'Stale', Icon: Clock, className: 'border-amber-300 bg-amber-50 text-amber-900' },
  never_reported: {
    label: 'Never reported',
    Icon: CircleSlash,
    className: NEUTRAL_CLASS,
  },
};

export const JobStatusBadge = ({ status }: { status: JobStatus }) => {
  const { label, Icon, className } = JOB_STATUS_STYLES[status];

  return (
    <Badge variant="outline" className={cn('gap-1 whitespace-nowrap px-2', className)}>
      <Icon className="h-3.5 w-3.5 shrink-0" />
      {label}
    </Badge>
  );
};

// Mirrors how the API derives health; Failed outranks Running.
const JOB_STATUS_DESCRIPTIONS: Record<JobStatus, string> = {
  healthy: 'Last run succeeded and the job reported on time.',
  running: 'A run is in progress.',
  failed: 'The latest finished run failed, even if a new run is in progress.',
  stale: 'No report by Stale after, or a run took longer than allowed.',
  never_reported: 'No report received yet.',
};

/** Defines every status once, instead of repeating it on each row. */
export const JobStatusLegend = () => (
  // One status per row, badges aligned in the first column.
  <dl className="grid grid-cols-[max-content_1fr] items-center gap-x-3 gap-y-1.5 text-xs text-muted-foreground">
    {JOB_STATUSES.map((status) => (
      <Fragment key={status}>
        <dt>
          <JobStatusBadge status={status} />
        </dt>
        <dd>{JOB_STATUS_DESCRIPTIONS[status]}</dd>
      </Fragment>
    ))}
  </dl>
);
