import type { RouteObject } from 'react-router-dom';

import { BrowsePage } from '@/features/browse/BrowsePage';

interface BrowseRoutesProps {
  selectedSimulationIds: string[];
  setSelectedSimulationIds: (ids: string[]) => void;
}

export const browseRoutes = ({
  selectedSimulationIds,
  setSelectedSimulationIds,
}: BrowseRoutesProps): RouteObject[] => {
  return [
    {
      path: '/browse',
      element: (
        <BrowsePage
          selectedSimulationIds={selectedSimulationIds}
          setSelectedSimulationIds={setSelectedSimulationIds}
        />
      ),
    },
  ];
};
