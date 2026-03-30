import { useEffect, useState } from 'react';

import { getCaseById } from '@/features/simulations/api/api';
import type { CaseOut } from '@/types';

export const useCase = (id: string) => {
  const [data, setData] = useState<CaseOut | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    getCaseById(id)
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
