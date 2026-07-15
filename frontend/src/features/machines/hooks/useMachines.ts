import { useQuery } from '@tanstack/react-query';

import { listMachines } from '@/features/machines/api/api';
import { catalogQueryKeys } from '@/features/simulations/queryKeys';

export const useMachines = () => {
  const query = useQuery({
    queryKey: catalogQueryKeys.machines,
    queryFn: () => listMachines(),
  });
  const data = query.data ?? [];

  return {
    ...query,
    data,
    loading: query.isLoading,
    error: query.error instanceof Error ? query.error.message : null,
    byId: new Map(data.map((machine) => [machine.id, machine])),
  };
};
