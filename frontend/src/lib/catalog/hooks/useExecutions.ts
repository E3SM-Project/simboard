import { keepPreviousData, useQuery } from '@tanstack/react-query';

import { listExecutions, type PageParams } from '@/api/catalog';
import { catalogQueryKeys } from '@/lib/catalog/queryKeys';

export const useExecutions = (params: PageParams = {}, enabled = true) => {
  const queryKey = params.caseId
    ? catalogQueryKeys.executions.casePage(String(params.caseId), params)
    : catalogQueryKeys.executions.page(params);
  const query = useQuery({
    queryKey,
    queryFn: () => listExecutions(params),
    placeholderData: keepPreviousData,
    enabled,
  });

  return {
    ...query,
    data: query.data?.items ?? [],
    page: query.data,
    loading: query.isLoading,
    error: query.error instanceof Error ? query.error.message : null,
  };
};
