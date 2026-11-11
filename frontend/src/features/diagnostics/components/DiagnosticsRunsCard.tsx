import { useQuery } from '@tanstack/react-query';
import { ChevronDown } from 'lucide-react';
import { useEffect, useState } from 'react';
import { Link, useLocation } from 'react-router-dom';

import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible';
import { getCaseDiagnosticsRuns } from '@/features/diagnostics/api';
import {
  MAX_RUNS_PER_GROUP,
  toEntry,
  useComparisonBasket,
} from '@/features/diagnostics/comparisonBasket';
import { DiagnosticRunList } from '@/features/diagnostics/components/DiagnosticRunList';
import { diagnosticsId, periodGroups, resourceTarget } from '@/features/diagnostics/discoveryState';
import type { DiagnosticsRunOut } from '@/features/diagnostics/types';
import { useToast } from '@/hooks/use-toast';
import { cn } from '@/lib/utils';

interface Props {
  caseId: string;
  caseName: string;
  directories?: { url: string; label: string | null }[];
}

/** The E3SM Diags and MPAS-Analysis runs published for a case. */
export const DiagnosticsRunsCard = ({ caseId, caseName, directories = [] }: Props) => {
  const query = useQuery({
    queryKey: ['diagnostics', 'case-runs', caseId],
    queryFn: () => getCaseDiagnosticsRuns(caseId),
    staleTime: 10 * 60_000,
  });
  const basket = useComparisonBasket();
  const { toast } = useToast();
  const [expanded, setExpanded] = useState<boolean | null>(null);
  const location = useLocation();
  const target = location.hash.slice(1);
  const id = diagnosticsId(caseId);
  const runs = periodGroups(query.data?.sources ?? []).flatMap(([, runs]) => runs);
  const open = expanded ?? runs.length > 0;
  const selected = basket.entries.filter((entry) => entry.caseId === caseId).length;
  const sources =
    query.data?.sources ??
    directories.map((directory) => ({
      rootUrl: directory.url,
      label: directory.label,
      runs: [],
      partial: false,
      error: null,
    }));

  useEffect(() => {
    if (target !== id && !target.startsWith(`${id}-source-`)) return;
    setExpanded(true);
  }, [id, target, location.key]);

  useEffect(() => {
    if (!open || (target !== id && !target.startsWith(`${id}-source-`))) return;
    const timer = setTimeout(() => {
      const section = document.getElementById(target);
      section?.focus({ preventScroll: true });
      section?.scrollIntoView({
        behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches
          ? 'instant'
          : 'smooth',
        block: 'start',
      });
    });
    return () => clearTimeout(timer);
  }, [id, target, location.key, query.data, open]);

  const add = (run: DiagnosticsRunOut) => {
    if (!basket.add(toEntry(run, caseId, caseName, location.pathname))) {
      toast({
        title: `Compare up to ${MAX_RUNS_PER_GROUP} runs of one kind at a time`,
        description: 'Remove one from the comparison tray first.',
        variant: 'destructive',
      });
    }
  };

  return (
    <Collapsible
      id={id}
      tabIndex={-1}
      open={open}
      onOpenChange={setExpanded}
      className="scroll-mt-20 rounded-xl focus-visible:ring-2 focus-visible:ring-ring"
    >
      <Card>
        <CardHeader className="p-0">
          <CollapsibleTrigger asChild>
            <button
              type="button"
              className="flex w-full items-center gap-3 rounded-xl p-4 text-left hover:bg-muted/30 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              <div className="min-w-0 flex-1">
                <CardTitle className="text-base">
                  Diagnostics{query.isSuccess ? ` (${runs.length})` : ''}
                </CardTitle>
                <p className="mt-1 text-sm text-muted-foreground">
                  {query.isLoading
                    ? 'Reading the diagnostics archive…'
                    : query.isError
                      ? 'Diagnostics could not be read. Browse the original output or try again.'
                      : `${runs.length} supported runs${selected ? ` · ${selected} added to compare` : ''}`}
                </p>
              </div>
              <ChevronDown
                aria-hidden="true"
                className={cn(
                  'h-5 w-5 shrink-0 text-muted-foreground transition-transform motion-reduce:transition-none',
                  open && 'rotate-180',
                )}
              />
            </button>
          </CollapsibleTrigger>
        </CardHeader>
        <CollapsibleContent>
          <CardContent className="max-h-[min(65dvh,36rem)] space-y-3 overflow-y-auto border-t p-3 sm:p-4">
            {query.isError ||
            query.data?.sources.some(
              (source) => (source.error && source.error !== 'url_not_allowed') || source.partial,
            ) ? (
              <Button
                variant="outline"
                size="sm"
                disabled={query.isFetching}
                onClick={() => void query.refetch()}
              >
                {query.isFetching ? 'Retrying…' : 'Try again'}
              </Button>
            ) : null}
            {/* Resource navigation must reveal runs hidden by an analysis filter. */}
            <DiagnosticRunList
              key={location.key}
              sources={sources}
              id={id}
              isAdded={basket.has}
              onAdd={add}
              onRemove={basket.remove}
            />
            {query.isSuccess && !runs.length ? (
              <p className="text-sm text-muted-foreground">
                No supported runs were found. Original directories may contain other tools or raw
                outputs.
              </p>
            ) : null}
          </CardContent>
        </CollapsibleContent>
      </Card>
    </Collapsible>
  );
};

/** Resource links retain their original destination; this is an optional shortcut. */
export const DiagnosticsResourceLink = ({ caseId, url }: { caseId: string; url: string }) => {
  const query = useQuery({
    queryKey: ['diagnostics', 'case-runs', caseId],
    queryFn: () => getCaseDiagnosticsRuns(caseId),
    staleTime: 10 * 60_000,
  });
  const location = useLocation();
  const target = resourceTarget(caseId, url, query.data?.sources ?? []);
  if (!target) return null;

  return (
    <Link
      to={{ pathname: location.pathname, search: location.search, hash: `#${target}` }}
      state={location.state}
      className="rounded px-2 text-xs text-muted-foreground hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
    >
      View in Diagnostics<span className="sr-only"> for {url}</span>
    </Link>
  );
};
