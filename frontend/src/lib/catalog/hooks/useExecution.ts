import { useQuery } from '@tanstack/react-query';

import { getExecutionById } from '@/api/catalog';
import { catalogQueryKeys } from '@/lib/catalog/queryKeys';

export const useExecution = (id: string, enabled = true) => {
  const query = useQuery({
    queryKey: catalogQueryKeys.executions.detail(id),
    queryFn: () => getExecutionById(id),
    enabled: enabled && Boolean(id),
  });
  return {
    ...query,
    data: query.data ?? null,
    loading: query.isLoading,
    error: query.error instanceof Error ? query.error.message : null,
  };
};
