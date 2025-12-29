import { useEffect, useMemo, useState } from "react";

import { listSimulations } from "@/features/simulations/api/api";
import { SimulationOut } from "@/types/simulation";

export const useSimulations = () => {
  const [data, setData] = useState<SimulationOut[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    listSimulations()
      .then((res) => {
        if (!cancelled) setData(res);
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
  }, []);

  const byId = useMemo(() => new Map(data.map((s) => [s.id, s])), [data]);

  return { data, loading, error, byId };
};