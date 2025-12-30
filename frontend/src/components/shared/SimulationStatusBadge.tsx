import { BadgeCheck, CircleDashed, Rocket, X } from 'lucide-react';

interface SimulationStatusBadgeProps {
  status: 'complete' | 'running' | 'failed' | 'not-started' | string;
}

export const SimulationStatusBadge = ({ status }: SimulationStatusBadgeProps) => (
  <span
    className={`px-2 py-1 rounded text-xs font-semibold flex items-center gap-1 ${
      status === 'complete'
        ? 'bg-green-50 text-green-900 border border-green-300'
        : status === 'running'
          ? 'bg-yellow-50 text-yellow-900 border border-yellow-300'
          : status === 'failed'
            ? 'bg-red-100 text-red-800'
            : 'bg-gray-200 text-gray-600'
    }`}
  >
    {status === 'complete' && <BadgeCheck className="w-4 h-4" />}
    {status === 'running' && <Rocket className="w-4 h-4" />}
    {status === 'failed' && <X className="w-4 h-4" />}
    {status === 'not-started' && <CircleDashed className="w-4 h-4" />}
    {status === 'not-started' ? 'Not Started' : status.charAt(0).toUpperCase() + status.slice(1)}
  </span>
);
