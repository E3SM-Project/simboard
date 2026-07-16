import { useInfiniteQuery } from '@tanstack/react-query';
import { useMemo } from 'react';

import { listSimulations } from '@/api/catalog';
import { catalogQueryKeys } from '@/lib/catalog/queryKeys';

const CASE_SIMULATION_PAGE_SIZE = 100;

export const useCaseSimulations = (caseId: string | undefined) => {
  const params = { caseId, pageSize: CASE_SIMULATION_PAGE_SIZE };
  const query = useInfiniteQuery({
    queryKey: catalogQueryKeys.simulations.caseInfinite(caseId ?? '', params),
    queryFn: ({ pageParam }) => listSimulations({ ...params, page: pageParam }),
    initialPageParam: 1,
    getNextPageParam: (lastPage) =>
      lastPage.page * lastPage.pageSize < lastPage.total ? lastPage.page + 1 : undefined,
    enabled: Boolean(caseId),
  });
  const simulations = useMemo(
    () => query.data?.pages.flatMap((page) => page.items) ?? [],
    [query.data],
  );

  return {
    ...query,
    data: simulations,
    total: query.data?.pages[0]?.total ?? 0,
    error: query.error instanceof Error ? query.error.message : null,
  };
};
