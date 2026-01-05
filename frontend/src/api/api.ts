import axios from 'axios';

import { getAuthenticated } from '@/api/authState';

const rawApiBaseUrl = import.meta.env.VITE_API_BASE_URL;
const API_BASE_URL = rawApiBaseUrl ?? (import.meta.env.DEV ? 'http://localhost:3000' : undefined);

if (!API_BASE_URL) {
  throw new Error(
    'VITE_API_BASE_URL is not defined. Please set it in your environment (e.g., .env file).',
  );
}

export type LogoutFn = (opts?: { silent?: boolean }) => void;
let onLogout: LogoutFn | null = null;

export const registerLogoutHandler = (fn: LogoutFn): void => {
  onLogout = fn;
};

export const api = axios.create({
  baseURL: API_BASE_URL,
  // Required for cookie authentication (e.g., GitHub OAuth).
  withCredentials: true,
  timeout: 10000,
});

// Intercept 401/403 to auto-logout.
api.interceptors.response.use(
  (res) => res,
  (err) => {
    const status = err.response?.status;
    const url = err.config?.url ?? '';

    if ((status === 401 || status === 403) && getAuthenticated() && !url.includes('/logout')) {
      onLogout?.({ silent: true });
    }

    return Promise.reject(err);
  },
);
