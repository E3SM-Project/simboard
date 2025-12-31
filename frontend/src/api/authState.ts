/**
 * authState.ts
 *
 * Minimal, imperative auth state for the API layer.
 *
 * This module mirrors whether an authenticated session has been established so
 * non-React code (e.g. Axios interceptors) can distinguish between anonymous
 * requests and expired sessions. It is not a source of truth and does not store
 * user data or trigger side effects.
 *
 * The canonical auth state lives in AuthProvider.
 */
let isAuthenticated = false;

export const setAuthenticated = (value: boolean) => {
  isAuthenticated = value;
};

export const getAuthenticated = () => {
  return isAuthenticated;
};
