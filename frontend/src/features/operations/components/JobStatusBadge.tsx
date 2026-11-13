import { CircleCheck, CirclePlay, CircleSlash, CircleX, Clock } from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import type { JobStatus } from '@/features/operations/operationsUtils';
import { cn } from '@/lib/utils';

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
    className: 'border-amber-300 bg-amber-50 text-amber-900',
  },
  failed: { label: 'Failed', Icon: CircleX, className: 'border-red-200 bg-red-50 text-red-800' },
  stale: { label: 'Stale', Icon: Clock, className: 'border-amber-300 bg-amber-50 text-amber-900' },
  never_reported: {
    label: 'Never reported',
    Icon: CircleSlash,
    className: 'border-border bg-muted text-muted-foreground',
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

/** Count of jobs in one status, for the summary row above the job table. */
export const JobStatusTile = ({ status, count }: { status: JobStatus; count: number }) => {
  const { label, Icon, className } = JOB_STATUS_STYLES[status];

  return (
    <div className={cn('flex items-center gap-3 rounded-xl border p-3', className)}>
      <Icon className="h-6 w-6 shrink-0" />
      <div>
        <dt className="text-sm font-medium">{label}</dt>
        <dd className="text-2xl font-semibold leading-tight">{count}</dd>
      </div>
    </div>
  );
};
