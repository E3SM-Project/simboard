const POST_LOGIN_RETURN_TARGET_KEY = 'post-login-return-target';
const AUTH_CALLBACK_PATH = '/auth/callback';
const DEFAULT_RETURN_TARGET = '/';

const isAuthCallbackTarget = (target: string): boolean =>
  target === AUTH_CALLBACK_PATH || target.startsWith(`${AUTH_CALLBACK_PATH}/`);

const isValidReturnPath = (target: string): boolean =>
  target.startsWith('/') && !target.startsWith('//') && !isAuthCallbackTarget(target);

export const buildCurrentReturnTarget = (): string => window.location.href;

export const buildCurrentReturnPath = (): string =>
  `${window.location.pathname}${window.location.search}${window.location.hash}`;

const toRelativeReturnPath = (target: string): string | null => {
  if (isValidReturnPath(target)) {
    return target;
  }

  try {
    const parsed = new URL(target, window.location.origin);
    if (parsed.origin !== window.location.origin) {
      return null;
    }

    const relativeTarget = `${parsed.pathname}${parsed.search}${parsed.hash}`;
    return isValidReturnPath(relativeTarget) ? relativeTarget : null;
  } catch {
    return null;
  }
};

export const savePostLoginReturnTarget = (target: string): void => {
  const normalizedTarget = toRelativeReturnPath(target);
  if (normalizedTarget === null) {
    return;
  }

  try {
    window.sessionStorage.setItem(POST_LOGIN_RETURN_TARGET_KEY, normalizedTarget);
  } catch {
    // Ignore storage failures and fall back to the default redirect.
  }
};

export const readPostLoginReturnTarget = (search: string): string | null => {
  const returnTo = new URLSearchParams(search).get('return_to');
  if (!returnTo) {
    return null;
  }

  return toRelativeReturnPath(returnTo);
};

export const consumePostLoginReturnTarget = (): string => {
  try {
    const target = window.sessionStorage.getItem(POST_LOGIN_RETURN_TARGET_KEY);
    window.sessionStorage.removeItem(POST_LOGIN_RETURN_TARGET_KEY);

    if (target) {
      const normalizedTarget = toRelativeReturnPath(target);
      if (normalizedTarget) {
        return normalizedTarget;
      }
    }
  } catch {
    // Ignore storage failures and fall back to the default redirect.
  }

  return DEFAULT_RETURN_TARGET;
};
