import type { SourceDirectoryOut } from '@/types';

export const preferredCaseDirectoryPaths = (directories: SourceDirectoryOut[] = []): string[] => {
  const archives = directories.filter(({ kind }) => kind === 'archive');
  const preferred = archives.length
    ? archives
    : directories.filter(({ kind }) => kind === 'staging');
  return [...new Set(preferred.map(({ path }) => path))].sort();
};
