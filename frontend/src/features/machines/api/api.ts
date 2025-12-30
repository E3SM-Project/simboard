import { api } from '@/api/api';
import { Machine } from '@/types';

export const MACHINES_URL = '/machines';

export const listMachines = async (url: string = MACHINES_URL): Promise<Machine[]> => {
  const res = await api.get<Machine[]>(url, {
    headers: { 'Cache-Control': 'no-cache' },
  });

  return res.data;
};
