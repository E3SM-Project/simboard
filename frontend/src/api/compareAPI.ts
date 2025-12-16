import api from '@/api/api';
import type { SimulationOut } from '@/types/index';

export const fetchAISimAnalysis = async (simulations: SimulationOut[]): Promise<string> => {
  const response = await api.post(`/analyze-simulations`, {
    simulations,
  });
  return response.data.summary;
};
