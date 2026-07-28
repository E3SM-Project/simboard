import { api } from '@/api/api';
import type {
  CaseDetailOut,
  CaseFilterOptionsOut,
  CasePageOut,
  CaseUpdate,
  CatalogOverviewOut,
  ExecutionCreate,
  ExecutionFilterOptionsOut,
  ExecutionOut,
  ExecutionPageOut,
  ExecutionSummaryResponseOut,
  ExecutionUpdate,
} from '@/types';

export interface PageParams {
  page?: number;
  pageSize?: number;
  search?: string;
  sortBy?: string;
  sortOrder?: 'asc' | 'desc';
  [key: string]: string | number | string[] | undefined;
}

const toQueryParams = (params: PageParams) => {
  const query = new URLSearchParams();

  Object.entries(params).forEach(([key, rawValue]) => {
    if (rawValue === undefined) return;
    const queryKey = key.replace(/[A-Z]/g, (letter) => `_${letter.toLowerCase()}`);
    const values = Array.isArray(rawValue) ? rawValue : [rawValue];
    values.forEach((value) => query.append(queryKey, String(value)));
  });

  return query;
};

export const EXECUTIONS_URL = '/executions';
export const CASES_URL = '/cases';
export const PACE_URL = '/pace';
const SUMMARY_REQUEST_TIMEOUT_MS = 120_000;

export interface PaceResolutionOut {
  executionId: string;
  experimentId: string | null;
}

export const createExecution = async (data: ExecutionCreate): Promise<ExecutionOut> => {
  const res = await api.post<ExecutionOut>(EXECUTIONS_URL, data);

  return res.data;
};

export const listExecutions = async (params: PageParams = {}): Promise<ExecutionPageOut> => {
  const res = await api.get<ExecutionPageOut>(EXECUTIONS_URL, {
    headers: { 'Cache-Control': 'no-cache' },
    params: toQueryParams(params),
  });

  return res.data;
};

export const getExecutionById = async (id: string): Promise<ExecutionOut> => {
  const res = await api.get<ExecutionOut>(`${EXECUTIONS_URL}/${id}`, {
    headers: { 'Cache-Control': 'no-cache' },
  });

  return res.data;
};

export const updateExecution = async (
  id: string,
  data: ExecutionUpdate,
): Promise<ExecutionOut> => {
  const res = await api.patch<ExecutionOut>(`${EXECUTIONS_URL}/${id}`, data);

  return res.data;
};

export const generateExecutionSummary = async (
  id: string,
): Promise<ExecutionSummaryResponseOut> => {
  const res = await api.post<ExecutionSummaryResponseOut>(
    `${EXECUTIONS_URL}/${id}/summary`,
    undefined,
    { timeout: SUMMARY_REQUEST_TIMEOUT_MS },
  );

  return res.data;
};

export const resolvePaceExecution = async (executionId: string): Promise<PaceResolutionOut> => {
  const res = await api.get<PaceResolutionOut>(`${PACE_URL}/resolve`, {
    headers: { 'Cache-Control': 'no-cache' },
    params: { execution_id: executionId },
  });

  return res.data;
};

export const listCases = async (params: PageParams = {}): Promise<CasePageOut> => {
  const res = await api.get<CasePageOut>(CASES_URL, {
    headers: { 'Cache-Control': 'no-cache' },
    params: toQueryParams(params),
  });

  return res.data;
};

export const getCatalogOverview = async (): Promise<CatalogOverviewOut> => {
  const res = await api.get<CatalogOverviewOut>(`${CASES_URL}/overview`);
  return res.data;
};

export const getCaseFilterOptions = async (): Promise<CaseFilterOptionsOut> => {
  const res = await api.get<CaseFilterOptionsOut>(`${CASES_URL}/filter-options`);
  return res.data;
};

export const getExecutionFilterOptions = async (): Promise<ExecutionFilterOptionsOut> => {
  const res = await api.get<ExecutionFilterOptionsOut>(`${EXECUTIONS_URL}/filter-options`);
  return res.data;
};

export const getCaseById = async (id: string): Promise<CaseDetailOut> => {
  const res = await api.get<CaseDetailOut>(`${CASES_URL}/${id}`, {
    headers: { 'Cache-Control': 'no-cache' },
  });

  return res.data;
};

export const updateCase = async (id: string, data: CaseUpdate): Promise<CaseDetailOut> => {
  const res = await api.patch<CaseDetailOut>(`${CASES_URL}/${id}`, data);

  return res.data;
};

export const listCaseNames = async (): Promise<string[]> => {
  const res = await api.get<string[]>(`${CASES_URL}/names`, {
    headers: { 'Cache-Control': 'no-cache' },
  });

  return res.data;
};
