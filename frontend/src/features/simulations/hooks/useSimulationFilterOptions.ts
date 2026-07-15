import { useQuery } from '@tanstack/react-query';

import { getSimulationFilterOptions } from '@/features/simulations/api/api';
import { catalogQueryKeys } from '@/features/simulations/queryKeys';

export const useSimulationFilterOptions = () =>
  useQuery({
    queryKey: catalogQueryKeys.simulations.options,
    queryFn: getSimulationFilterOptions,
  });
