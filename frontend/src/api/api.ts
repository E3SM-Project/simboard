import axios from 'axios';

import { getAuthenticated } from '@/api/authState';

export const API_PREFIX = '/api/v1';

const API_ORIGIN = import.meta.env.VITE_API_BASE_URL ?? '';

const stripTrailingSlashes = (s: string) => s.replace(/\/+$/, '');
const stripLeadingSlashes = (s: string) => s.replace(/^\/+/, '');

export const API_BASE_URL =
  `${stripTrailingSlashes(API_ORIGIN || window.location.origin)}` +
  `/${stripLeadingSlashes(API_PREFIX)}`;

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
