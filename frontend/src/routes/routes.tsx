import { RouteObject, useParams, useRoutes } from 'react-router-dom';

import { useSimulation } from '@/api/simulation';
import AuthCallback from '@/auth/AuthCallback';
import { BrowsePage } from '@/features/browse/BrowsePage';
import { ComparePage } from '@/features/compare/ComparePage';
import { DocsPage } from '@/features/docs/DocsPage';
import { HomePage } from '@/features/home/HomePage';
import { SimulationDetailsPage } from '@/features/simulations/SimulationDetailsPage';
import { SimulationsPage } from '@/features/simulations/SimulationsPage';
import Upload from '@/pages/Upload/Upload';
import ProtectedRoute from '@/routes/ProtectedRoute';
import type { Machine, SimulationOut } from '@/types/index';

interface RoutesProps {
  simulations: SimulationOut[];
  machines: Machine[];
  selectedSimulationIds: string[];
  setSelectedSimulationIds: (ids: string[]) => void;
  selectedSimulations: SimulationOut[];
}

const SimulationDetailsRoute = () => {
  const { id } = useParams<{ id: string }>();

  const { data: simulation, loading, error } = useSimulation(id || '');

  if (!id)
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-center text-gray-500">Invalid simulation ID</div>
      </div>
    );
  if (loading)
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-center text-gray-500">Loading simulation details...</div>
      </div>
    );
  if (error)
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-center text-red-600">Error: {error}</div>
      </div>
    );
  if (!simulation)
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-center text-gray-500">Simulation not found</div>
      </div>
    );

  return <SimulationDetailsPage simulation={simulation} />;
};

const createRoutes = ({
  simulations,
  machines,
  selectedSimulationIds,
  setSelectedSimulationIds,
  selectedSimulations,
}: RoutesProps): RouteObject[] => {
  return [
    { path: '/', element: <HomePage simulations={simulations} machines={machines} /> },
    {
      path: '/browse',
      element: (
        <BrowsePage
          simulations={simulations}
          selectedSimulationIds={selectedSimulationIds}
          setSelectedSimulationIds={setSelectedSimulationIds}
        />
      ),
    },
    { path: '/simulations', element: <SimulationsPage simulations={simulations} /> },
    { path: '/simulations/:id', element: <SimulationDetailsRoute /> },
    {
      path: '/compare',
      element: (
        <ComparePage
          simulations={simulations}
          selectedSimulationIds={selectedSimulationIds}
          setSelectedSimulationIds={setSelectedSimulationIds}
          selectedSimulations={selectedSimulations}
        />
      ),
    },
    {
      element: <ProtectedRoute />,
      children: [{ path: '/upload', element: <Upload machines={machines} /> }],
    },
    { path: '/upload', element: <Upload machines={machines} /> },
    { path: '/docs', element: <DocsPage /> },
    { path: '/auth/callback', element: <AuthCallback /> },
    { path: '*', element: <div className="p-8">404 - Page not found</div> },
  ];
};

export const AppRoutes = ({
  simulations,
  machines,
  selectedSimulationIds,
  setSelectedSimulationIds,
  selectedSimulations,
}: RoutesProps) => {
  const routes = createRoutes({
    simulations,
    machines,
    selectedSimulationIds,
    setSelectedSimulationIds,
    selectedSimulations,
  });
  const routing = useRoutes(routes);
  return routing;
};
