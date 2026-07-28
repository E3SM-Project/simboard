import type { RouteObject } from 'react-router-dom';

import { BrowsePage } from '@/features/browse/BrowsePage';

interface BrowseRoutesProps {
  selectedExecutionIds: string[];
  setSelectedExecutionIds: (ids: string[]) => void;
}

export const browseRoutes = ({
  selectedExecutionIds,
  setSelectedExecutionIds,
}: BrowseRoutesProps): RouteObject[] => {
  return [
    {
      path: '/browse',
      element: (
        <BrowsePage
          selectedExecutionIds={selectedExecutionIds}
          setSelectedExecutionIds={setSelectedExecutionIds}
        />
      ),
    },
  ];
};
