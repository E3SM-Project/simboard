import { useEffect, useMemo, useState } from "react";

import { listMachines } from "@/features/machines/api/api";
import { Machine } from "@/types";

export const useMachines = () => {
  const [data, setData] = useState<Machine[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    listMachines()
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