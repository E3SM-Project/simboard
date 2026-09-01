import { useQuery } from '@tanstack/react-query';

import { type ExecutionIdentityParams,getExecutionByIdentity } from '@/api/catalog';
import { catalogQueryKeys } from '@/lib/catalog/queryKeys';

export const useReadableExecution = (identity: ExecutionIdentityParams | null) => {
  const query = useQuery({
    queryKey: catalogQueryKeys.executions.readableDetail(
      identity?.machineName ?? '',
      identity?.hpcUsername ?? '',
      identity?.caseName ?? '',
      identity?.executionId ?? '',
    ),
    queryFn: () => {
      if (!identity) {
        throw new Error('Execution identity is required.');
      }

      return getExecutionByIdentity(identity);
    },
    enabled: identity !== null,
  });

  return {
    ...query,
    data: query.data ?? null,
    loading: query.isLoading,
    error: query.error instanceof Error ? query.error.message : null,
  };
};
