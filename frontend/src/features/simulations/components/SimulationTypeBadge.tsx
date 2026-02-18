import { BadgeCheck, FlaskConical, FlaskRound, GitBranch, HelpCircle } from 'lucide-react';

import { Badge } from '@/components/ui/badge';

interface SimulationTypeBadgeProps {
  simulationType: 'unknown' | 'production' | 'experimental' | 'test' | string;
}

const styles: Record<
  string,
  {
    className: string;
    style: React.CSSProperties;
    label: string;
    Icon: React.ElementType;
  }
> = {
  production: {
    className: 'text-xs px-2 py-1 bg-green-600 text-white',
    style: { backgroundColor: '#16a34a', color: '#fff' },
    label: 'Production Run',
    Icon: BadgeCheck,
  },
  master: {
    className: 'text-xs px-2 py-1 bg-blue-600 text-white',
    style: { backgroundColor: '#2563eb', color: '#fff' },
    label: 'Master Run',
    Icon: GitBranch,
  },
  experimental: {
    className: 'text-xs px-2 py-1 bg-yellow-400 text-black',
    style: { backgroundColor: '#facc15', color: '#000' },
    label: 'Experimental Run',
    Icon: FlaskConical,
  },
  test: {
    className: 'text-xs px-2 py-1 bg-purple-500 text-white',
    style: { backgroundColor: '#9333ea', color: '#fff' },
    label: 'Test Run',
    Icon: FlaskRound,
  },
  unknown: {
    className: 'text-xs px-2 py-1 bg-gray-400 text-white',
    style: { backgroundColor: '#9ca3af', color: '#fff' },
    label: 'Unknown Type',
    Icon: HelpCircle,
  },
};

const getStyleProps = (simulationType: string) => {
  if (styles[simulationType]) return styles[simulationType];
  return styles.unknown;
};

export const SimulationTypeBadge = ({ simulationType }: SimulationTypeBadgeProps) => {
  const { className, style, label, Icon } = getStyleProps(simulationType);

  return (
    <Badge className={className} style={style}>
      <Icon className="w-4 h-4 mr-1" /> {label}
    </Badge>
  );
};
