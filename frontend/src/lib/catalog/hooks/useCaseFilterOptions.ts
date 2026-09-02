import { keepPreviousData, useQuery } from '@tanstack/react-query';

import { type CaseFilterOptionsParams, getCaseFilterOptions } from '@/api/catalog';
import { catalogQueryKeys } from '@/lib/catalog/queryKeys';

export const useCaseFilterOptions = (params: CaseFilterOptionsParams = {}, enabled = true) =>
  useQuery({
    queryKey: catalogQueryKeys.cases.optionsFor(params),
    queryFn: () => getCaseFilterOptions(params),
    enabled,
    placeholderData: keepPreviousData,
  });
