import { useQuery } from '@tanstack/react-query';

import { getExecutionFilterOptions } from '@/api/catalog';
import { catalogQueryKeys } from '@/lib/catalog/queryKeys';

export const useExecutionFilterOptions = () =>
  useQuery({
    queryKey: catalogQueryKeys.executions.options,
    queryFn: getExecutionFilterOptions,
  });
