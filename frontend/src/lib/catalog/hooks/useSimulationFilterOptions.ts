import { useQuery } from '@tanstack/react-query';

import { getSimulationFilterOptions } from '@/api/catalog';
import { catalogQueryKeys } from '@/lib/catalog/queryKeys';

export const useSimulationFilterOptions = () =>
  useQuery({
    queryKey: catalogQueryKeys.simulations.options,
    queryFn: getSimulationFilterOptions,
  });
