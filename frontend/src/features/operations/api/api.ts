import { api } from '@/api/api';
import type {
  IngestionSummaryResponse,
  RejectedExecutionsResponse,
  ScheduledJobHealthResponse,
} from '@/features/operations/types';

export const getJobHealth = async (siteName?: string): Promise<ScheduledJobHealthResponse> => {
  const res = await api.get<ScheduledJobHealthResponse>('/ingestions/jobs', {
    params: { site_name: siteName },
  });

  return res.data;
};

export const getIngestionSummary = async (params: {
  siteName?: string;
  startDate: string;
  endDate: string;
}): Promise<IngestionSummaryResponse> => {
  const res = await api.get<IngestionSummaryResponse>('/ingestions/summary', {
    params: { site_name: params.siteName, start_date: params.startDate, end_date: params.endDate },
  });

  return res.data;
};

export const getRejectedExecutions = async (
  siteName?: string,
): Promise<RejectedExecutionsResponse> => {
  const res = await api.get<RejectedExecutionsResponse>('/ingestions/rejected-executions', {
    params: { site_name: siteName },
  });

  return res.data;
};
