import { useQuery } from '@tanstack/react-query';

import { getCaseDiagnosticsViewers } from '@/api/catalog';
import { catalogQueryKeys } from '@/lib/catalog/queryKeys';

/**
 * Diagnostics viewers published for a case, grouped by the link they came from.
 *
 * Discovery is served from a backend cache after the first request, and the
 * archive layout changes rarely, so results are kept fresh for ten minutes to
 * avoid re-crawling on every navigation.
 */
export const useCaseDiagnosticsViewers = (caseId: string | undefined) => {
  const query = useQuery({
    queryKey: catalogQueryKeys.cases.diagnosticsViewers(caseId ?? ''),
    queryFn: () => getCaseDiagnosticsViewers(caseId as string),
    enabled: Boolean(caseId),
    staleTime: 10 * 60 * 1000,
  });

  return {
    ...query,
    data: query.data ?? null,
    loading: query.isLoading,
    error: query.error instanceof Error ? query.error.message : null,
  };
};
