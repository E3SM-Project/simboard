import { Check, Copy } from 'lucide-react';
import { useEffect, useState } from 'react';

import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import type { SourceDirectoryOut } from '@/types';

export const PerformanceSourceDirectory = ({
  directory,
}: {
  directory?: SourceDirectoryOut | null;
}) => {
  const [feedback, setFeedback] = useState<{
    path: string;
    status: 'copied' | 'error';
  } | null>(null);
  const status = feedback?.path === directory?.path ? feedback?.status : undefined;

  useEffect(() => {
    if (!feedback) return;
    const timeout = window.setTimeout(() => setFeedback(null), 2000);
    return () => window.clearTimeout(timeout);
  }, [feedback]);

  const copyPath = async () => {
    if (!directory) return;
    try {
      await navigator.clipboard.writeText(directory.path);
      setFeedback({ path: directory.path, status: 'copied' });
    } catch {
      setFeedback({ path: directory.path, status: 'error' });
    }
  };

  return (
    <div className="min-w-0 space-y-2">
      <Label className="block text-xs text-muted-foreground">Performance Source Directory</Label>
      {directory ? (
        <>
          <div className="flex min-w-0 items-start gap-2">
            <code className="min-w-0 break-all rounded bg-muted px-2 py-1 text-xs">
              {directory.path}
            </code>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className={`h-7 shrink-0 gap-1.5 px-2 ${status === 'copied' ? 'text-emerald-600 hover:text-emerald-700' : ''}`}
              onClick={() => void copyPath()}
              aria-label="Copy performance source directory"
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
};
