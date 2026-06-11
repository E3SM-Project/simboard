import { BadgeCheck, CircleDashed, Rocket, X } from 'lucide-react';

interface SimulationStatusBadgeProps {
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

const STATUS_STYLES: Record<
  string,
  {
    className: string;
    label: string;
    Icon?: typeof BadgeCheck;
  }
> = {
  completed: {
    className: 'bg-green-50 text-green-900 border border-green-300',
    label: 'Completed',
    Icon: BadgeCheck,
  },
  complete: {
    className: 'bg-green-50 text-green-900 border border-green-300',
    label: 'Complete',
    Icon: BadgeCheck,
  },
  running: {
    className: 'bg-yellow-50 text-yellow-900 border border-yellow-300',
    label: 'Running',
    Icon: Rocket,
  },
  failed: {
    className: 'bg-red-100 text-red-800 border border-red-200',
    label: 'Failed',
    Icon: X,
  },
  queued: {
    className: 'bg-blue-50 text-blue-900 border border-blue-200',
    label: 'Queued',
  },
  created: {
    className: 'bg-slate-100 text-slate-800 border border-slate-200',
    label: 'Created',
  },
  unknown: {
    className: 'bg-gray-200 text-gray-600 border border-gray-300',
    label: 'Unknown',
    Icon: CircleDashed,
  },
  'not-started': {
    className: 'bg-gray-200 text-gray-600 border border-gray-300',
    label: 'Not Started',
    Icon: CircleDashed,
  },
};

export const SimulationStatusBadge = ({ status }: SimulationStatusBadgeProps) => {
  const normalizedStatus = status.toLowerCase();
  const style = STATUS_STYLES[normalizedStatus] ?? {
    className: 'bg-gray-200 text-gray-600 border border-gray-300',
    label: status.charAt(0).toUpperCase() + status.slice(1),
  };
  const Icon = style.Icon;

  return (
    <span
      className={`px-2 py-1 rounded text-xs font-semibold flex items-center gap-1 ${style.className}`}
    >
      {Icon ? <Icon className="w-4 h-4" /> : null}
      {style.label}
    </span>
  );
};
