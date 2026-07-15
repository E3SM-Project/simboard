import { useQuery } from '@tanstack/react-query';

import { getCatalogOverview } from '@/features/simulations/api/api';
import { catalogQueryKeys } from '@/features/simulations/queryKeys';

export const useCatalogOverview = () =>
  useQuery({
    queryKey: catalogQueryKeys.overview,
    queryFn: getCatalogOverview,
  });
