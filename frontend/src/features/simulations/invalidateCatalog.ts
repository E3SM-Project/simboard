import type { QueryClient } from '@tanstack/react-query';

import { catalogQueryKeys } from '@/features/simulations/queryKeys';

export const invalidateCatalog = async (queryClient: QueryClient) => {
  await Promise.all([
    queryClient.invalidateQueries({ queryKey: catalogQueryKeys.overview }),
    queryClient.invalidateQueries({ queryKey: catalogQueryKeys.cases.all }),
    queryClient.invalidateQueries({ queryKey: catalogQueryKeys.simulations.all }),
  ]);
};
