import { useEffect, useState } from "react";

import { getSimulationById } from "@/features/simulations/api/api";
import { SimulationOut } from "@/types/simulation";

export const useSimulation = (id: string) => {
  const [data, setData] = useState<SimulationOut | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    getSimulationById(id)
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