import { useQuery } from '@tanstack/react-query';

import { getCaseFilterOptions } from '@/api/catalog';
import { catalogQueryKeys } from '@/lib/catalog/queryKeys';

export const useCaseFilterOptions = () =>
  useQuery({
    queryKey: catalogQueryKeys.cases.options,
    queryFn: getCaseFilterOptions,
  });
