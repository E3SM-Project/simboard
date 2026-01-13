import { useParams } from 'react-router-dom';

import { useAuth } from '@/auth/hooks/useAuth';
import { SimulationDetailsView } from '@/features/simulations/components/SimulationDetailsView';
import { useSimulation } from '@/features/simulations/hooks/useSimulation';

export const SimulationDetailsPage = () => {
  const { user, isAuthenticated } = useAuth();
  const { id } = useParams<{ id: string }>();
  const { data: simulation, loading, error } = useSimulation(id ?? '');

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

  const canEdit = !!(
    isAuthenticated &&
    user &&
    simulation.createdBy &&
    user.id === simulation.createdBy
  );

  return <SimulationDetailsView simulation={simulation} canEdit={canEdit} />;
};
