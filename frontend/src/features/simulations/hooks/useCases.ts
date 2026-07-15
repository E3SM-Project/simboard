import { keepPreviousData, useQuery } from '@tanstack/react-query';

import { listCases, type PageParams } from '@/features/simulations/api/api';
import { catalogQueryKeys } from '@/features/simulations/queryKeys';

export const useCases = (params: PageParams = {}) => {
  const query = useQuery({
    queryKey: catalogQueryKeys.cases.page(params),
    queryFn: () => listCases(params),
    placeholderData: keepPreviousData,
  });

  return {
    ...query,
    data: query.data?.items ?? [],
    page: query.data,
    loading: query.isLoading,
    error: query.error instanceof Error ? query.error.message : null,
  };
};
