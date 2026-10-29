import { useQuery } from '@tanstack/react-query';
import { Check, ChevronDown, ExternalLink, Plus, RotateCw } from 'lucide-react';
import { useMemo, useState } from 'react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible';
import { getCaseDiagnosticsRuns } from '@/features/diagnostics/api';
import { runPeriod } from '@/features/diagnostics/compareState';
import {
  MAX_RUNS_PER_GROUP,
  toEntry,
  useComparisonBasket,
} from '@/features/diagnostics/comparisonBasket';
import type { DiagnosticsRunOut, DiagnosticsSourceOut } from '@/features/diagnostics/types';
import { useToast } from '@/hooks/use-toast';
import { cn } from '@/lib/utils';

const UNREADABLE =
  'The diagnostics archive could not be read just now. The runs are still published; try again shortly.';

const SOURCE_ERRORS: Record<string, string> = {
  url_not_allowed:
    'This link is not on a public E3SM diagnostics server, so its runs cannot be listed.',
  archive_unavailable: UNREADABLE,
};

interface RunGroup {
  title: string;
  runs: DiagnosticsRunOut[];
  defaultOpen: boolean;
}

/** Observation runs first (what people usually compare), then the rest. */
const groupRuns = (runs: DiagnosticsRunOut[]): RunGroup[] =>
  [
    {
      title: 'E3SM Diags · model vs observations',
      runs: runs.filter((r) => r.tool === 'e3sm_diags' && r.comparison !== 'model_vs_model'),
      defaultOpen: true,
    },
    {
      title: 'E3SM Diags · model vs model',
      runs: runs.filter((r) => r.comparison === 'model_vs_model'),
      defaultOpen: false,
    },
    {
      title: 'MPAS-Analysis',
      runs: runs.filter((r) => r.tool === 'mpas_analysis'),
      defaultOpen: false,
    },
  ].filter((group) => group.runs.length > 0);

/**
 * The E3SM Diags and MPAS-Analysis runs published for a case, each of which
 * can be added to the comparison bar. Collapsed by default: a production run
 * publishes twenty or more.
 */
export const DiagnosticsRunsCard = ({ caseId, caseName }: { caseId: string; caseName: string }) => {
  const query = useQuery({
    queryKey: ['diagnostics', 'case-runs', caseId],
    queryFn: () => getCaseDiagnosticsRuns(caseId),
    staleTime: 10 * 60_000,
  });
  const basket = useComparisonBasket();
  const { toast } = useToast();
  const [open, setOpen] = useState(false);

  const runs = useMemo(() => query.data?.sources.flatMap((s) => s.runs) ?? [], [query.data]);
  const counts = {
    e3sm: runs.filter((r) => r.tool === 'e3sm_diags').length,
    mpas: runs.filter((r) => r.tool === 'mpas_analysis').length,
    staged: basket.entries.filter((e) => e.caseId === caseId).length,
  };

  const summary = query.isLoading
    ? 'Reading the diagnostics archive…'
    : query.isError
      ? UNREADABLE
      : runs.length === 0
        ? 'No E3SM Diags or MPAS-Analysis runs were found.'
        : [
            counts.e3sm && `${counts.e3sm} E3SM Diags`,
            counts.mpas && `${counts.mpas} MPAS-Analysis`,
            counts.staged && `${counts.staged} added to compare`,
          ]
            .filter(Boolean)
            .join(' · ');

  const add = (run: DiagnosticsRunOut) => {
    if (!basket.add(toEntry(run, caseId, caseName))) {
      toast({
        title: `Compare up to ${MAX_RUNS_PER_GROUP} runs of one kind at a time`,
        description: 'Remove one from the comparison bar first.',
        variant: 'destructive',
      });
    }
  };

  return (
    <Collapsible open={open} onOpenChange={setOpen}>
      <Card>
        <CardHeader className="p-0">
          <CollapsibleTrigger asChild>
            <button
              type="button"
              className="flex w-full items-center gap-3 rounded-xl p-5 text-left transition-colors hover:bg-muted/30"
            >
              <div className="min-w-0 flex-1">
                <CardTitle className="text-base">
                  Diagnostics{query.isSuccess ? ` (${runs.length})` : ''}
                </CardTitle>
                <p
                  className={cn(
                    'mt-1 truncate text-sm text-muted-foreground',
                    query.isError && 'text-red-600',
                  )}
                >
                  {summary}
                </p>
              </div>
              <ChevronDown
                aria-hidden="true"
                className={cn(
                  'h-5 w-5 text-muted-foreground transition-transform',
                  open && 'rotate-180',
                )}
              />
            </button>
          </CollapsibleTrigger>
        </CardHeader>

        <CollapsibleContent>
          <CardContent className="space-y-4 border-t p-5">
            <p className="text-sm text-muted-foreground">
              Add a run here and the matching run from another case, then compare them side by side.
            </p>
            {query.isError ? (
              <Button
                variant="outline"
                size="sm"
                onClick={() => void query.refetch()}
                disabled={query.isFetching}
              >
                <RotateCw className="mr-1 h-3.5 w-3.5" aria-hidden="true" />
                {query.isFetching ? 'Retrying…' : 'Try again'}
              </Button>
            ) : (
              query.data?.sources.map((source) => (
                <Source
                  key={source.rootUrl}
                  source={source}
                  isAdded={basket.has}
                  onAdd={add}
                  onRemove={basket.remove}
                />
              ))
            )}
          </CardContent>
        </CollapsibleContent>
      </Card>
    </Collapsible>
  );
};

interface SourceProps {
  source: DiagnosticsSourceOut;
  isAdded: (url: string) => boolean;
  onAdd: (run: DiagnosticsRunOut) => void;
  onRemove: (url: string) => void;
}

const Source = ({ source, ...actions }: SourceProps) => {
  if (source.error) {
    return (
      <div className="rounded-lg border border-amber-200 bg-amber-50/60 px-3 py-2.5 text-sm text-amber-900">
        <p className="break-all font-medium">{source.rootUrl}</p>
        <p>{SOURCE_ERRORS[source.error] ?? `Runs could not be listed (${source.error}).`}</p>
      </div>
    );
  }
  return (
    <div className="space-y-3">
      <a
        href={source.rootUrl}
        target="_blank"
        rel="noreferrer"
        className="inline-flex items-center gap-1 break-all text-xs text-slate-500 hover:underline"
      >
        {source.rootUrl}
        <ExternalLink className="h-3 w-3 shrink-0" aria-hidden="true" />
      </a>
      {source.partial ? (
        <p className="text-xs text-amber-700">
          Some runs may be missing: part of the archive could not be read.
        </p>
      ) : null}
      {groupRuns(source.runs).map((group) => (
        <Group key={group.title} group={group} {...actions} />
      ))}
    </div>
  );
};

const Group = ({
  group,
  isAdded,
  onAdd,
  onRemove,
}: Omit<SourceProps, 'source'> & { group: RunGroup }) => {
  const [open, setOpen] = useState(group.defaultOpen);
  const added = group.runs.filter((run) => isAdded(run.url)).length;

  return (
    <Collapsible open={open} onOpenChange={setOpen}>
      <CollapsibleTrigger asChild>
        <button
          type="button"
          className="flex w-full items-center gap-2 rounded-md px-1 py-1 text-left hover:bg-muted/30"
        >
          <ChevronDown
            aria-hidden="true"
            className={cn(
              'h-4 w-4 text-muted-foreground transition-transform',
              open && 'rotate-180',
            )}
          />
          <h3 className="text-sm font-semibold text-slate-900">
            {group.title} <span className="font-normal text-slate-500">({group.runs.length})</span>
          </h3>
          {added ? (
            <Badge variant="secondary" className="ml-auto">
              {added} added
            </Badge>
          ) : null}
        </button>
      </CollapsibleTrigger>
      <CollapsibleContent className="mt-1.5 space-y-1.5 pl-6">
        {group.runs.map((run) => (
          <div
            key={run.url}
            className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-slate-200/80 bg-white/80 px-3 py-2 text-sm"
          >
            <div className="flex min-w-0 items-center gap-2">
              <span className="font-medium text-slate-900">{runPeriod(run)}</span>
              {run.tsStartYear != null ? (
                <span className="text-slate-500">
                  ts {runPeriod({ startYear: run.tsStartYear, endYear: run.tsEndYear })}
                </span>
              ) : null}
              {run.subsection ? (
                <span className="truncate text-slate-500" title={run.subsection}>
                  {run.subsection}
                </span>
              ) : null}
            </div>
            <div className="flex items-center gap-1.5">
              <Button asChild variant="ghost" size="sm">
                <a href={run.url} target="_blank" rel="noreferrer">
                  Open
                  <ExternalLink className="ml-1 h-3.5 w-3.5" aria-hidden="true" />
                </a>
              </Button>
              {isAdded(run.url) ? (
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => onRemove(run.url)}
                  aria-pressed
                >
                  <Check className="mr-1 h-3.5 w-3.5" aria-hidden="true" />
                  Added
                </Button>
              ) : (
                <Button variant="outline" size="sm" onClick={() => onAdd(run)} aria-pressed={false}>
                  <Plus className="mr-1 h-3.5 w-3.5" aria-hidden="true" />
                  Add to compare
                </Button>
              )}
            </div>
          </div>
        ))}
      </CollapsibleContent>
    </Collapsible>
  );
};
