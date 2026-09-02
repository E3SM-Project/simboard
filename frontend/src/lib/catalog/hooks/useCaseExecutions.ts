import { useInfiniteQuery } from '@tanstack/react-query';
import { useMemo } from 'react';

import { listExecutions, type PageParams } from '@/api/catalog';
import { catalogQueryKeys } from '@/lib/catalog/queryKeys';

const CASE_EXECUTION_PAGE_SIZE = 100;

export const useCaseExecutions = (
  caseId: string | undefined,
  options: Pick<PageParams, 'sortBy' | 'sortOrder'> = {},
) => {
  const params = { caseId, pageSize: CASE_EXECUTION_PAGE_SIZE, ...options };
  const query = useInfiniteQuery({
    queryKey: catalogQueryKeys.executions.caseInfinite(caseId ?? '', params),
    queryFn: ({ pageParam }) => listExecutions({ ...params, page: pageParam }),
    initialPageParam: 1,
    getNextPageParam: (lastPage) =>
      lastPage.page * lastPage.pageSize < lastPage.total ? lastPage.page + 1 : undefined,
    enabled: Boolean(caseId),
  });
  const executions = useMemo(
    () => query.data?.pages.flatMap((page) => page.items) ?? [],
    [query.data],
  );

  return {
    ...query,
    data: executions,
    total: query.data?.pages[0]?.total ?? 0,
    error: query.error instanceof Error ? query.error.message : null,
  };
};
