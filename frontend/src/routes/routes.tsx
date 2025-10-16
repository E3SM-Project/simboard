import { RouteObject, useParams, useRoutes } from 'react-router-dom';

import { useSimulation } from '@/api/simulation';
import Browse from '@/pages/Browse/Browse';
import Compare from '@/pages/Compare/Compare';
import Docs from '@/pages/Docs/Docs';
import Home from '@/pages/Home/Home';
import SimulationDetails from '@/pages/SimulationsCatalog/SimulationDetails';
import SimulationsCatalog from '@/pages/SimulationsCatalog/SimulationsCatalog';
import Upload from '@/pages/Upload/Upload';
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

  return <SimulationDetails simulation={simulation} />;
};

const createRoutes = ({
  simulations,
  machines,
  selectedSimulationIds,
  setSelectedSimulationIds,
  selectedSimulations,
}: RoutesProps): RouteObject[] => {
  return [
    { path: '/', element: <Home simulations={simulations} machines={machines} /> },
    {
      path: '/browse',
      element: (
        <Browse
          simulations={simulations}
          selectedSimulationIds={selectedSimulationIds}
          setSelectedSimulationIds={setSelectedSimulationIds}
        />
      ),
    },
    { path: '/simulations', element: <SimulationsCatalog simulations={simulations} /> },
    { path: '/simulations/:id', element: <SimulationDetailsRoute /> },
    {
      path: '/compare',
      element: (
        <Compare
          simulations={simulations}
          selectedSimulationIds={selectedSimulationIds}
          setSelectedSimulationIds={setSelectedSimulationIds}
          selectedSimulations={selectedSimulations}
        />
      ),
    },
    { path: '/upload', element: <Upload machines={machines} /> },
    { path: '/docs', element: <Docs /> },
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
