import { useLocation, useParams } from 'react-router-dom';

import { SimulationDetailsView } from '@/features/simulations/components/SimulationDetailsView';
import { useSimulation } from '@/features/simulations/hooks/useSimulation';

export const SimulationDetailsPage = () => {
  const { id } = useParams<{ id: string }>();
  const location = useLocation();
  const { data: simulation, loading, error } = useSimulation(id ?? '');
  const state = location.state as { from?: string } | null;
  const backHref = typeof state?.from === 'string' ? state.from : '/browse';
  const backLabel = backHref.startsWith('/cases/')
    ? 'Back to Case'
    : backHref === '/cases'
      ? 'Back to Cases'
      : backHref.startsWith('/simulations')
        ? 'Back to Simulations'
        : 'Back to Runs';

  if (!id) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-center text-gray-500">Invalid simulation ID</div>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-center text-gray-500">Loading simulation details…</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-center text-red-600">Error: {error}</div>
      </div>
    );
  }

  if (!simulation) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-center text-gray-500">Simulation not found</div>
      </div>
    );
  }

  return <SimulationDetailsView simulation={simulation} backHref={backHref} backLabel={backLabel} />;
};
