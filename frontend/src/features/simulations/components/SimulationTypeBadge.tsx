import { BadgeCheck, FlaskConical, GitBranch } from 'lucide-react';

import { Badge } from '@/components/ui/badge';

interface SimulationTypeBadgeProps {
  simulationType: 'production' | 'master' | string;
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
};

const getStyleProps = (simulationType: string) => {
  if (simulationType === 'production') return styles.production;
  if (simulationType === 'master') return styles.master;
  return styles.experimental;
};

export const SimulationTypeBadge = ({ simulationType }: SimulationTypeBadgeProps) => {
  const { className, style, label, Icon } = getStyleProps(simulationType);

  return (
    <Badge className={className} style={style}>
      <Icon className="w-4 h-4 mr-1" /> {label}
    </Badge>
  );
};

