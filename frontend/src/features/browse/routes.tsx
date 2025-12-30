import type { RouteObject } from 'react-router-dom';

import { BrowsePage } from '@/features/browse/BrowsePage';
import { SimulationOut } from '@/types';

interface BrowseRoutesProps {
  simulations: SimulationOut[];
  selectedSimulationIds: string[];
  setSelectedSimulationIds: (ids: string[]) => void;
}

export const browseRoutes = ({
  simulations,
  selectedSimulationIds,
  setSelectedSimulationIds,
}: BrowseRoutesProps): RouteObject[] => {
  return [
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
  ];
};
