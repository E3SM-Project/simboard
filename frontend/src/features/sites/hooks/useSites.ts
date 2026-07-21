import { useQuery } from '@tanstack/react-query';

import { listSites } from '@/features/sites/api/api';
import { catalogQueryKeys } from '@/lib/catalog/queryKeys';

export const useSites = () => {
  const query = useQuery({
    queryKey: catalogQueryKeys.sites,
    queryFn: listSites,
  });

  return {
    ...query,
    data: query.data ?? [],
  };
};
