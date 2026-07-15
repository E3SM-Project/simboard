import { useQuery } from '@tanstack/react-query';

import { getCaseFilterOptions } from '@/features/simulations/api/api';
import { catalogQueryKeys } from '@/features/simulations/queryKeys';

export const useCaseFilterOptions = () =>
  useQuery({
    queryKey: catalogQueryKeys.cases.options,
    queryFn: getCaseFilterOptions,
  });
