import type { QueryClient } from '@tanstack/react-query';

import { catalogQueryKeys } from '@/lib/catalog/queryKeys';

export const invalidateCatalog = async (queryClient: QueryClient) => {
  await Promise.all([
    queryClient.invalidateQueries({ queryKey: catalogQueryKeys.overview }),
    queryClient.invalidateQueries({ queryKey: catalogQueryKeys.cases.all }),
    queryClient.invalidateQueries({ queryKey: catalogQueryKeys.cases.options }),
    queryClient.invalidateQueries({ queryKey: catalogQueryKeys.simulations.all }),
    queryClient.invalidateQueries({ queryKey: catalogQueryKeys.simulations.options }),
  ]);
};
