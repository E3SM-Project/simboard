import { useQuery } from '@tanstack/react-query';

import { getCaseById } from '@/api/catalog';
import { catalogQueryKeys } from '@/lib/catalog/queryKeys';

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
