import { useQuery } from '@tanstack/react-query';

import { getCatalogOverview } from '@/api/catalog';
import { catalogQueryKeys } from '@/lib/catalog/queryKeys';

export const useCatalogOverview = () =>
  useQuery({
    queryKey: catalogQueryKeys.overview,
    queryFn: getCatalogOverview,
  });
