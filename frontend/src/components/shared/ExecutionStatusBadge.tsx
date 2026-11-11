import { BadgeCheck, CircleDashed, Rocket, X } from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';

interface ExecutionStatusBadgeProps {
  status:
    | 'unknown'
    | 'created'
    | 'queued'
    | 'running'
    | 'failed'
    | 'completed'
    | 'complete'
    | 'not-started'
    | string;
}

type StatusTone = 'success' | 'warning' | 'error' | 'info' | 'neutral';

const TONE_CLASSES: Record<StatusTone, string> = {
  success: 'border-green-300 bg-green-50 text-green-900',
  warning: 'border-amber-300 bg-amber-50 text-amber-900',
  error: 'border-red-200 bg-red-50 text-red-800',
  info: 'border-blue-200 bg-blue-50 text-blue-900',
  neutral: 'border-border bg-muted text-muted-foreground',
};

const STATUS_STYLES: Record<string, { tone: StatusTone; label: string; Icon?: typeof BadgeCheck }> =
  {
    completed: { tone: 'success', label: 'Completed', Icon: BadgeCheck },
    complete: { tone: 'success', label: 'Complete', Icon: BadgeCheck },
    running: { tone: 'warning', label: 'Running', Icon: Rocket },
    failed: { tone: 'error', label: 'Failed', Icon: X },
    queued: { tone: 'info', label: 'Queued' },
    created: { tone: 'neutral', label: 'Created' },
    unknown: { tone: 'neutral', label: 'Unknown', Icon: CircleDashed },
    'not-started': { tone: 'neutral', label: 'Not Started', Icon: CircleDashed },
  };

export const ExecutionStatusBadge = ({ status }: ExecutionStatusBadgeProps) => {
  const style = STATUS_STYLES[status.toLowerCase()] ?? {
    tone: 'neutral',
    label: status.charAt(0).toUpperCase() + status.slice(1),
  };
  const Icon = style.Icon;

  return (
    <Badge variant="outline" className={cn('gap-1 px-2', TONE_CLASSES[style.tone])}>
      {Icon ? <Icon className="h-3.5 w-3.5 shrink-0" /> : null}
      {style.label}
    </Badge>
  );
};
