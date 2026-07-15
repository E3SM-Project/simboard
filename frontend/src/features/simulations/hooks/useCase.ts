import { useQuery } from '@tanstack/react-query';

import { getCaseById } from '@/features/simulations/api/api';
import { catalogQueryKeys } from '@/features/simulations/queryKeys';

export const useCase = (id: string) => {
  const query = useQuery({
    queryKey: catalogQueryKeys.cases.detail(id),
    queryFn: () => getCaseById(id),
    enabled: Boolean(id),
  });
  return {
    ...query,
    data: query.data ?? null,
    loading: query.isLoading,
    error: query.error instanceof Error ? query.error.message : null,
  };
};
