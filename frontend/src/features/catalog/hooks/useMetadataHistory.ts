import { useInfiniteQuery, useQueryClient } from '@tanstack/react-query';
import { useMemo } from 'react';

import { getCaseHistory, getExecutionHistory } from '@/api/catalog';
import { catalogQueryKeys } from '@/lib/catalog/queryKeys';

const HISTORY_PAGE_SIZE = 10;

export const useMetadataHistory = (
  entityType: 'case' | 'execution',
  id: string,
  enabled: boolean,
) => {
  const queryClient = useQueryClient();
  const queryKey =
    entityType === 'case'
      ? catalogQueryKeys.cases.history(id)
      : catalogQueryKeys.executions.history(id);
  const query = useInfiniteQuery({
    queryKey,
    queryFn: ({ pageParam }) =>
      entityType === 'case'
        ? getCaseHistory(id, { page: pageParam, pageSize: HISTORY_PAGE_SIZE })
        : getExecutionHistory(id, { page: pageParam, pageSize: HISTORY_PAGE_SIZE }),
    initialPageParam: 1,
    getNextPageParam: (lastPage) =>
      lastPage.page * lastPage.pageSize < lastPage.total ? lastPage.page + 1 : undefined,
    enabled: Boolean(id) && enabled,
  });
  const entries = useMemo(
    () => query.data?.pages.flatMap((page) => page.items) ?? [],
    [query.data],
  );

  return {
    ...query,
    data: entries,
    total: query.data?.pages[0]?.total ?? 0,
    loading: enabled && query.isLoading,
    loaded: query.isFetched,
    error: query.error instanceof Error ? query.error.message : null,
    reset: () => queryClient.resetQueries({ queryKey, exact: true }),
  };
};
