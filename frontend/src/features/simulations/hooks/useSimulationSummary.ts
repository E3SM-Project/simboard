import axios from 'axios';
import { useEffect, useRef, useState } from 'react';

import { generateSimulationSummary } from '@/features/simulations/api/api';
import type { SimulationSummaryResponseOut } from '@/types';

export const useSimulationSummary = (simulationId: string) => {
  const [data, setData] = useState<SimulationSummaryResponseOut | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [requested, setRequested] = useState(false);
  const currentSimulationIdRef = useRef(simulationId);
  const requestIdRef = useRef(0);

  useEffect(() => {
    currentSimulationIdRef.current = simulationId;
    requestIdRef.current += 1;
    setData(null);
    setLoading(false);
    setError(null);
    setRequested(false);
  }, [simulationId]);

  const generate = async () => {
    if (!simulationId) return;

    const requestedSimulationId = simulationId;
    const requestId = requestIdRef.current + 1;
    requestIdRef.current = requestId;
    const isLatestRequest = () =>
      requestId === requestIdRef.current &&
      currentSimulationIdRef.current === requestedSimulationId;

    setRequested(true);
    setLoading(true);
    setError(null);

    try {
      const result = await generateSimulationSummary(requestedSimulationId);
      if (!isLatestRequest()) {
        return;
      }
      setData(result);
    } catch (e) {
      if (!isLatestRequest()) {
        return;
      }
      setData(null);
      if (axios.isAxiosError(e) && (e.response?.status === 401 || e.response?.status === 403)) {
        setError('Log in to generate an AI summary for this simulation.');
      } else {
        setError(e instanceof Error ? e.message : 'Failed to generate AI summary.');
      }
    } finally {
      if (isLatestRequest()) {
        setLoading(false);
      }
    }
  };

  return { data, loading, error, requested, generate };
};
