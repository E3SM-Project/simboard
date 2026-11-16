import { CircleCheck, CirclePlay, CircleSlash, CircleX, Clock } from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import type { JobStatus } from '@/features/operations/operationsUtils';
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
