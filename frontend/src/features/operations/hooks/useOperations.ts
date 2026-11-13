import { keepPreviousData, useQuery } from '@tanstack/react-query';

import {
  getIngestionSummary,
  getJobHealth,
  getRejectedExecutions,
} from '@/features/operations/api/api';

export const operationsQueryKeys = {
  jobs: (siteName?: string) => ['operations', 'jobs', siteName ?? null] as const,
  summary: (siteName: string | undefined, startDate: string, endDate: string) =>
    ['operations', 'summary', siteName ?? null, startDate, endDate] as const,
  rejected: (siteName?: string) => ['operations', 'rejected', siteName ?? null] as const,
};

export const useJobHealth = (siteName?: string) =>
  useQuery({
    queryKey: operationsQueryKeys.jobs(siteName),
    queryFn: () => getJobHealth(siteName),
    placeholderData: keepPreviousData,
  });

export const useIngestionSummary = (
  siteName: string | undefined,
  startDate: string,
  endDate: string,
) =>
  useQuery({
    queryKey: operationsQueryKeys.summary(siteName, startDate, endDate),
    queryFn: () => getIngestionSummary({ siteName, startDate, endDate }),
    placeholderData: keepPreviousData,
  });

export const useRejectedExecutions = (siteName?: string) =>
  useQuery({
    queryKey: operationsQueryKeys.rejected(siteName),
    queryFn: () => getRejectedExecutions(siteName),
    placeholderData: keepPreviousData,
  });
