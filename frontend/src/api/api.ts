import axios, { AxiosError, AxiosResponse } from "axios";

export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'https://127.0.0.1:8000/api';

export type LogoutFn = () => void;
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
  (response: AxiosResponse) => response,
  (error: AxiosError) => {
    const status = error.response?.status;

    if (status === 401 || status === 403) {
      const logoutEndpoint = "/logout";
      const requestUrl = error.config?.url ?? "";

      // Avoid recursive logout when logout call itself fails.
      const isLogoutRequest =
        requestUrl.endsWith(logoutEndpoint) ||
        requestUrl.includes(`${logoutEndpoint}?`) ||
        requestUrl.includes(`${logoutEndpoint}/`);

      if (!isLogoutRequest) {
        onLogout?.();
      }
    }

    if (import.meta.env.DEV) {
      console.warn("API Error:", status, error.response?.data);
    }

    return Promise.reject(error);
  }
);

export default api;