/** Derive a browser link without changing the original repository source. */
export const repositoryBrowserUrl = (source?: string | null): string | null => {
  if (!source || source.trim() !== source || /[\s\\]/.test(source)) return null;

  if (/^https?:\/\//i.test(source)) {
    try {
      const url = new URL(source);
      if (!url.hostname || url.username || url.password) return null;

      return url.href;
    } catch {
      return null;
    }
  }

  const match = source.match(
    /^(?:git@github\.com:|ssh:\/\/git@github\.com\/)([A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+)$/,
  );
  if (!match || match[1].split('/').some((part) => part === '.' || part === '..')) {
    return null;
  }

  return `https://github.com/${match[1]}`;
};
