import { Check, ChevronDown, ExternalLink, Plus } from 'lucide-react';
import { useEffect, useState } from 'react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible';
import { runPeriod } from '@/features/diagnostics/compareState';
import { RUN_GROUPS, runGroup } from '@/features/diagnostics/discoveryState';
import type { DiagnosticsRunOut, DiagnosticsSourceOut } from '@/features/diagnostics/types';
import { cn } from '@/lib/utils';

export interface DiagnosticRunListProps {
  source: DiagnosticsSourceOut;
  id: string;
  target?: string;
  navigationKey?: string;
  isAdded: (url: string) => boolean;
  onAdd: (run: DiagnosticsRunOut) => void;
  onRemove: (url: string) => void;
}

/** Shared discovery presentation; callers own staging or workspace drafts. */
export const DiagnosticRunList = ({
  source,
  id,
  target,
  navigationKey,
  ...actions
}: DiagnosticRunListProps) => (
  <section
    id={id}
    tabIndex={-1}
    className="scroll-mt-20 space-y-3 rounded-md focus-visible:ring-2 focus-visible:ring-ring"
  >
    <a
      href={source.rootUrl}
      target="_blank"
      rel="noreferrer"
      title={source.rootUrl}
      className="inline-flex items-center gap-1 rounded text-sm font-medium text-slate-600 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
    >
      {source.label || 'Browse diagnostics directory'}
      <ExternalLink className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
      <span className="sr-only"> (opens in a new tab)</span>
    </a>
    {source.error ? (
      <p className="text-sm text-amber-800">
        {source.error === 'url_not_allowed'
          ? 'This directory is not on a supported public diagnostics server.'
          : 'This directory could not be read. Browse the original output or try again.'}
      </p>
    ) : null}
    {source.partial ? (
      <p className="text-xs text-amber-700">
        Some runs may be missing: part of the archive could not be read.
      </p>
    ) : null}
    {RUN_GROUPS.map((group) => {
      const runs = source.runs.filter((run) => runGroup(run) === group.key);
      return runs.length ? (
        <RunGroup
          key={group.key}
          title={group.title}
          runs={runs}
          id={`${id}-${group.key}`}
          target={target}
          navigationKey={navigationKey}
          {...actions}
        />
      ) : null;
    })}
  </section>
);

const RunGroup = ({
  title,
  runs,
  id,
  target,
  navigationKey,
  isAdded,
  onAdd,
  onRemove,
}: Omit<DiagnosticRunListProps, 'source'> & { title: string; runs: DiagnosticsRunOut[] }) => {
  const [open, setOpen] = useState(true);
  useEffect(() => {
    if (target === id) setOpen(true);
  }, [id, target, navigationKey]);
  const added = runs.filter((run) => isAdded(run.url)).length;

  return (
    <Collapsible
      id={id}
      tabIndex={-1}
      open={open}
      onOpenChange={setOpen}
      className="scroll-mt-20 rounded-md focus-visible:ring-2 focus-visible:ring-ring"
    >
      <CollapsibleTrigger asChild>
        <button
          type="button"
          className="flex w-full items-center gap-2 rounded-md bg-slate-50 px-3 py-2 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          <ChevronDown
            aria-hidden="true"
            className={cn(
              'h-4 w-4 shrink-0 text-slate-500 transition-transform motion-reduce:transition-none',
              !open && '-rotate-90',
            )}
          />
          <span className="text-sm font-semibold text-slate-900">
            {title} <span className="font-normal text-slate-500">({runs.length})</span>
          </span>
          {added ? (
            <Badge variant="secondary" className="ml-auto">
              {added} added
            </Badge>
          ) : null}
        </button>
      </CollapsibleTrigger>
      <CollapsibleContent className="space-y-2 pt-2">
        {runs.map((run) => {
          const selected = isAdded(run.url);
          const label = [title, runPeriod(run), run.subsection].filter(Boolean).join(' · ');
          return (
            <div
              key={run.url}
              className={cn(
                'flex flex-wrap items-center justify-between gap-2 rounded-lg border px-3 py-2.5 text-sm',
                selected ? 'border-slate-400 bg-slate-50' : 'border-slate-200 bg-white',
              )}
            >
              <div className="min-w-0 flex-1 space-y-1">
                <p className="font-medium text-slate-900">
                  {runPeriod(run) ? `Climatology ${runPeriod(run)}` : 'Diagnostic run'}
                </p>
                {run.tsStartYear != null ? (
                  <p className="text-xs text-slate-500">
                    Time series {runPeriod({ startYear: run.tsStartYear, endYear: run.tsEndYear })}
                  </p>
                ) : null}
                {run.subsection ? (
                  <p className="break-words text-xs text-slate-500">{run.subsection}</p>
                ) : null}
              </div>
              <div className="flex items-center gap-1">
                <Button asChild variant="ghost" size="sm">
                  <a
                    href={run.url}
                    target="_blank"
                    rel="noreferrer"
                    title={run.url}
                    aria-label={`Open ${label} (new tab)`}
                  >
                    Open <ExternalLink className="ml-1 h-3.5 w-3.5" aria-hidden="true" />
                  </a>
                </Button>
                <Button
                  type="button"
                  variant={selected ? 'secondary' : 'outline'}
                  size="sm"
                  aria-pressed={selected}
                  aria-label={`${selected ? 'Remove' : 'Add'} ${label}`}
                  onClick={() => (selected ? onRemove(run.url) : onAdd(run))}
                >
                  {selected ? (
                    <Check className="mr-1 h-3.5 w-3.5" aria-hidden="true" />
                  ) : (
                    <Plus className="mr-1 h-3.5 w-3.5" aria-hidden="true" />
                  )}
                  {selected ? 'Added' : 'Add'}
                </Button>
              </div>
            </div>
          );
        })}
      </CollapsibleContent>
    </Collapsible>
  );
};
