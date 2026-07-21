import { api } from '@/api/api';
import type { Site } from '@/types';

export const SITES_URL = '/sites';

export const listSites = async (): Promise<Site[]> => {
  const res = await api.get<Site[]>(SITES_URL, {
    headers: { 'Cache-Control': 'no-cache' },
  });

  return res.data;
};
