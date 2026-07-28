import { useQuery } from '@tanstack/react-query';

import { getCaseHistory, getExecutionHistory } from '@/api/catalog';
import { catalogQueryKeys } from '@/lib/catalog/queryKeys';

export const useMetadataHistory = (entityType: 'case' | 'execution', id: string) => {
  const query = useQuery({
    queryKey:
      entityType === 'case'
        ? catalogQueryKeys.cases.history(id)
        : catalogQueryKeys.executions.history(id),
    queryFn: () => (entityType === 'case' ? getCaseHistory(id) : getExecutionHistory(id)),
    enabled: Boolean(id),
  });

  return {
    ...query,
    data: query.data ?? [],
    loading: query.isLoading,
    error: query.error instanceof Error ? query.error.message : null,
  };
};
