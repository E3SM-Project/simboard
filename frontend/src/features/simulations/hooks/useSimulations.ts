import { keepPreviousData, useQuery } from '@tanstack/react-query';

import { listSimulations, type PageParams } from '@/features/simulations/api/api';
import { catalogQueryKeys } from '@/features/simulations/queryKeys';

export const useSimulations = (params: PageParams = {}, enabled = true) => {
  const queryKey = params.caseId
    ? catalogQueryKeys.simulations.casePage(String(params.caseId), params)
    : catalogQueryKeys.simulations.page(params);
  const query = useQuery({
    queryKey,
    queryFn: () => listSimulations(params),
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
