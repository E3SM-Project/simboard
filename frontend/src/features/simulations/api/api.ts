import { api } from '@/api/api';
import type {
  CaseOut,
  SimulationCreate,
  SimulationOut,
  SimulationSummaryResponseOut,
  SimulationUpdate,
} from '@/types';

export const SIMULATIONS_URL = '/simulations';
export const CASES_URL = '/cases';
export const PACE_URL = '/pace';
const SUMMARY_REQUEST_TIMEOUT_MS = 120_000;

export interface PaceResolutionOut {
  executionId: string;
  experimentId: string | null;
}

export const createSimulation = async (data: SimulationCreate): Promise<SimulationOut> => {
  const res = await api.post<SimulationOut>(SIMULATIONS_URL, data);

  return res.data;
};

export const listSimulations = async (url: string = SIMULATIONS_URL): Promise<SimulationOut[]> => {
  const res = await api.get<SimulationOut[]>(url, {
    headers: { 'Cache-Control': 'no-cache' },
  });

  return res.data;
};

export const getSimulationById = async (id: string): Promise<SimulationOut> => {
  const res = await api.get<SimulationOut>(`${SIMULATIONS_URL}/${id}`, {
    headers: { 'Cache-Control': 'no-cache' },
  });

  return res.data;
};

export const updateSimulation = async (
  id: string,
  data: SimulationUpdate,
): Promise<SimulationOut> => {
  const res = await api.patch<SimulationOut>(`${SIMULATIONS_URL}/${id}`, data);

  return res.data;
};

export const generateSimulationSummary = async (
  id: string,
): Promise<SimulationSummaryResponseOut> => {
  const res = await api.post<SimulationSummaryResponseOut>(
    `${SIMULATIONS_URL}/${id}/summary`,
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

export const listCases = async (url: string = CASES_URL): Promise<CaseOut[]> => {
  const res = await api.get<CaseOut[]>(url, {
    headers: { 'Cache-Control': 'no-cache' },
  });

  return res.data;
};

export const getCaseById = async (id: string): Promise<CaseOut> => {
  const res = await api.get<CaseOut>(`${CASES_URL}/${id}`, {
    headers: { 'Cache-Control': 'no-cache' },
  });

  return res.data;
};

export const listCaseNames = async (): Promise<string[]> => {
  const res = await api.get<string[]>(`${CASES_URL}/names`, {
    headers: { 'Cache-Control': 'no-cache' },
  });

  return res.data;
};
