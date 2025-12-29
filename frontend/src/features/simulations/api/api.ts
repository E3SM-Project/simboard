import { api } from '@/api/api';
import type { SimulationCreate, SimulationOut } from '@/types';

export const SIMULATIONS_URL = '/simulations';

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

