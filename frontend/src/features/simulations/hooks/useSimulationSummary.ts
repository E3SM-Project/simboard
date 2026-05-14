import axios from 'axios';
import { useEffect, useState } from 'react';

import { generateSimulationSummary } from '@/features/simulations/api/api';
import type { SimulationSummaryResponseOut } from '@/types';

export const useSimulationSummary = (simulationId: string) => {
  const [data, setData] = useState<SimulationSummaryResponseOut | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [requested, setRequested] = useState(false);

  useEffect(() => {
    setData(null);
    setLoading(false);
    setError(null);
    setRequested(false);
  }, [simulationId]);

  const generate = async () => {
    if (!simulationId) return;

    setRequested(true);
    setLoading(true);
    setError(null);

    try {
      const result = await generateSimulationSummary(simulationId);
      setData(result);
    } catch (e) {
      setData(null);
      if (axios.isAxiosError(e) && (e.response?.status === 401 || e.response?.status === 403)) {
        setError('Log in to generate an AI summary for this simulation.');
      } else {
        setError(e instanceof Error ? e.message : 'Failed to generate AI summary.');
      }
    } finally {
      setLoading(false);
    }
  };

  return { data, loading, error, requested, generate };
};
