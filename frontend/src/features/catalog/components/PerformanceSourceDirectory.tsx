import { Check, Copy } from 'lucide-react';
import { useEffect, useState } from 'react';

import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { preferredCaseDirectoryPaths } from '@/features/catalog/sourceDirectoryUtils';
import type { SourceDirectoryOut } from '@/types';

const SourceDirectoryPath = ({ path }: { path: string }) => {
  const [feedback, setFeedback] = useState<{
    path: string;
    status: 'copied' | 'error';
  } | null>(null);
  const status = feedback?.path === path ? feedback?.status : undefined;

  useEffect(() => {
    if (!feedback) return;
    const timeout = window.setTimeout(() => setFeedback(null), 2000);
    return () => window.clearTimeout(timeout);
  }, [feedback]);

  const copyPath = async () => {
    try {
      await navigator.clipboard.writeText(path);
      setFeedback({ path, status: 'copied' });
    } catch {
      setFeedback({ path, status: 'error' });
    }
  };

  return (
    <div className="min-w-0">
      <div className="flex min-w-0 items-start gap-2">
        <code className="min-w-0 break-all rounded bg-muted px-2 py-1 text-xs">{path}</code>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className={`h-7 shrink-0 gap-1.5 px-2 ${status === 'copied' ? 'text-emerald-600 hover:text-emerald-700' : ''}`}
          onClick={() => void copyPath()}
          aria-label={`Copy performance source directory ${path}`}
          title={status === 'copied' ? 'Copied to clipboard' : 'Copy full path'}
        >
          {status === 'copied' ? (
            <>
              <Check size={14} aria-hidden="true" />
              <span className="text-xs">Copied</span>
            </>
          ) : (
            <Copy size={14} aria-hidden="true" />
          )}
        </Button>
      </div>
      <span
        role="status"
        aria-live="polite"
        className={status === 'error' ? 'block text-xs text-destructive' : 'sr-only'}
      >
        {status === 'copied'
          ? 'Performance source directory copied to clipboard.'
          : status === 'error'
            ? 'Could not copy. Try again or select the path to copy manually.'
            : ''}
      </span>
    </div>
  );
};

const SourceDirectoryField = ({ paths, plural = false }: { paths: string[]; plural?: boolean }) => (
  <div className="min-w-0 space-y-2">
    <Label className="block text-xs text-muted-foreground">
      {plural ? 'Performance Source Directories' : 'Performance Source Directory'}
    </Label>
    {paths.length ? (
      <>
        <ul className="space-y-2">
          {paths.map((path) => (
            <li key={path}>
              <SourceDirectoryPath path={path} />
            </li>
          ))}
        </ul>
        <p className="text-xs text-muted-foreground">
          {plural
            ? 'Recorded performance-data locations. Directories may have been moved, compressed, or removed.'
            : 'Recorded performance-data location. The directory may have been moved, compressed, or removed.'}
        </p>
      </>
    ) : (
      <p className="text-sm text-muted-foreground">Not recorded</p>
    )}
  </div>
);

export const PerformanceSourceDirectory = ({
  directory,
}: {
  directory?: SourceDirectoryOut | null;
}) => <SourceDirectoryField paths={directory ? [directory.path] : []} />;

export const PerformanceSourceDirectories = ({
  directories,
}: {
  directories?: SourceDirectoryOut[];
}) => <SourceDirectoryField paths={preferredCaseDirectoryPaths(directories)} plural />;
