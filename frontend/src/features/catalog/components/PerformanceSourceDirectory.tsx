import { Check, Copy } from 'lucide-react';
import { useEffect, useId, useState } from 'react';

import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  filterSourceDirectoryPaths,
  preferredCaseDirectoryPaths,
} from '@/features/catalog/sourceDirectoryUtils';
import type { SourceDirectoryOut } from '@/types';

const SourceDirectoryPath = ({ path, inDialog = false }: { path: string; inDialog?: boolean }) => {
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
          className={`${inDialog ? 'h-11 min-w-11' : 'h-7'} shrink-0 gap-1.5 px-2 ${status === 'copied' ? 'text-emerald-600 hover:text-emerald-700' : ''}`}
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

const SourceDirectoryField = ({ paths }: { paths: string[] }) => (
  <div className="min-w-0 space-y-2">
    <Label className="block text-xs text-muted-foreground">Performance Source Directory</Label>
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
          Recorded performance-data location. The directory may have been moved, compressed, or
          removed.
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
}) => {
  const [query, setQuery] = useState('');
  const filterId = useId();
  const resultsId = useId();
  const paths = preferredCaseDirectoryPaths(directories);
  const filteredPaths = filterSourceDirectoryPaths(paths, query);

  if (paths.length === 1) {
    return <SourceDirectoryField paths={paths} />;
  }

  return (
    <div className="min-w-0 space-y-2">
      <Label className="block text-xs text-muted-foreground">Performance Source Directories</Label>
      {paths.length ? (
        <>
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
            <p className="text-sm">
              {paths.length} source {paths.length === 1 ? 'directory' : 'directories'}
            </p>
            <Dialog onOpenChange={() => setQuery('')}>
              <DialogTrigger asChild>
                <Button type="button" variant="outline" className="min-h-11">
                  View directories
                </Button>
              </DialogTrigger>
              <DialogContent className="flex max-h-[calc(100dvh-2rem)] w-[calc(100%-2rem)] min-w-0 flex-col sm:max-w-3xl">
                <DialogHeader className="shrink-0 pr-6">
                  <DialogTitle>Performance Source Directories</DialogTitle>
                  <DialogDescription>
                    Recorded performance-data locations. Directories may have been moved,
                    compressed, or removed.
                  </DialogDescription>
                </DialogHeader>
                <div className="shrink-0 space-y-2">
                  <Label htmlFor={filterId}>Filter directories</Label>
                  <Input
                    id={filterId}
                    type="search"
                    placeholder="Search full paths"
                    value={query}
                    onChange={(event) => setQuery(event.target.value)}
                    aria-controls={resultsId}
                  />
                  <p role="status" className="text-xs text-muted-foreground">
                    Showing {filteredPaths.length} of {paths.length}{' '}
                    {paths.length === 1 ? 'directory' : 'directories'}
                  </p>
                </div>
                <div
                  id={resultsId}
                  role="region"
                  aria-label="Source directory results"
                  tabIndex={0}
                  className="min-h-0 min-w-0 overflow-y-auto overscroll-contain rounded-md border p-3 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-inset"
                >
                  {filteredPaths.length ? (
                    <ul className="space-y-3">
                      {filteredPaths.map((path) => (
                        <li key={path}>
                          <SourceDirectoryPath path={path} inDialog />
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p className="text-sm text-muted-foreground">
                      No directories match your filter.
                    </p>
                  )}
                </div>
              </DialogContent>
            </Dialog>
          </div>
          <p className="text-xs text-muted-foreground">
            Recorded performance-data locations. Directories may have been moved, compressed, or
            removed.
          </p>
        </>
      ) : (
        <p className="text-sm text-muted-foreground">Not recorded</p>
      )}
    </div>
  );
};
