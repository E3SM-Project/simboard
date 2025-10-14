import axios from 'axios';

import type { SimulationOut } from '@/types/index';

const BASE_URL = 'http://localhost:8000/api';

export const fetchAISimAnalysis = async (simulations: SimulationOut[]): Promise<string> => {
  const response = await axios.post(`${BASE_URL}/analyze-simulations`, {
    simulations,
  });
  return response.data.summary;
};
