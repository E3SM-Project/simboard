import { useEffect, useMemo, useState } from 'react';

import axiosInstance from '@/api/axios';
import type { Machine, SimulationOut } from '@/types';

const SIMULATIONS_URL = '/simulations';

export const fetchSimulations = async (
  url: string = SIMULATIONS_URL
): Promise<SimulationOut[]> => {
  const res = await axiosInstance.get<SimulationOut[]>(url, {
    headers: { 'Cache-Control': 'no-cache' },
  });

  return res.data;
};

export const fetchSimulationById = async (id: string): Promise<SimulationOut> => {
  const res = await axiosInstance.get<SimulationOut>(`${SIMULATIONS_URL}/${id}`, {
    headers: { 'Cache-Control': 'no-cache' },
  });

  return res.data;
};

export const useSimulation = (id: string) => {
  const [data, setData] = useState<SimulationOut | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    fetchSimulationById(id)
      .then((json) => {
        if (!cancelled) setData(json);
      })
      .catch((e) => {
        if (!cancelled) setError(e.message);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [id]);

  return { data, loading, error };
};

export const useSimulations = (url: string = SIMULATIONS_URL) => {
  const [data, setData] = useState<SimulationOut[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    fetchSimulations(url)
      .then((json) => {
        if (!cancelled) setData(json);
      })
      .catch((e) => {
        if (!cancelled) setError(e.message);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [url]);

  const byId = useMemo(() => new Map(data.map((s) => [s.id, s])), [data]);

  return { data, loading, error, byId };
};

export const useMachines = (url: string = '/machines') => {
  const [data, setData] = useState<Machine[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    axiosInstance.get<Machine[]>(url, {
      headers: { 'Cache-Control': 'no-cache' },
    })
      .then((res) => {
        if (!cancelled) setData(res.data);
      })
      .catch((e) => {
        if (!cancelled) setError(e.message);
      }
      )

      .finally(() => {
        if (!cancelled) setLoading(false);
      }
      );

    return () => {
      cancelled = true;
    };
  }, [url]);

  const byId = useMemo(() => new Map(data.map((s) => [s.id, s])), [data]);

  return { data, loading, error, byId };
}
