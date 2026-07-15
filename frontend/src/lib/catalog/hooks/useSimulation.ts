import { useQuery } from '@tanstack/react-query';

import { getSimulationById } from '@/api/catalog';
import { catalogQueryKeys } from '@/lib/catalog/queryKeys';

export const useSimulation = (id: string, enabled = true) => {
  const query = useQuery({
    queryKey: catalogQueryKeys.simulations.detail(id),
    queryFn: () => getSimulationById(id),
    enabled: enabled && Boolean(id),
  });
  return {
    ...query,
    data: query.data ?? null,
    loading: query.isLoading,
    error: query.error instanceof Error ? query.error.message : null,
  };
};
