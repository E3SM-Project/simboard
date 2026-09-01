import { useQuery } from '@tanstack/react-query';

import { type CaseIdentityParams,getCaseByIdentity } from '@/api/catalog';
import { catalogQueryKeys } from '@/lib/catalog/queryKeys';

export const useReadableCase = (identity: CaseIdentityParams | null) => {
  const query = useQuery({
    queryKey: catalogQueryKeys.cases.readableDetail(
      identity?.machineName ?? '',
      identity?.hpcUsername ?? '',
      identity?.caseName ?? '',
    ),
    queryFn: () => {
      if (!identity) {
        throw new Error('Case identity is required.');
      }

      return getCaseByIdentity(identity);
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
