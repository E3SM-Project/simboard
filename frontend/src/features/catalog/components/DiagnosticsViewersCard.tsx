import { Check, ChevronDown, ExternalLink, Info, Plus, RotateCw } from 'lucide-react';
import { useMemo, useState } from 'react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';
import { useToast } from '@/hooks/use-toast';
import { useCaseDiagnosticsViewers } from '@/lib/catalog/hooks/useCaseDiagnosticsViewers';
import { IICE_ENTRANCE_URL, suggestIiceLabel } from '@/lib/iice';
import { IICE_BASKET_MAX_PER_TOOL, toBasketEntry, useIiceBasket } from '@/lib/iiceBasket';
import { cn } from '@/lib/utils';
import type { DiagnosticsViewerOut, DiagnosticsViewerSourceOut } from '@/types';

interface DiagnosticsViewersCardProps {
  caseId: string;
  caseName: string;
  /** Whether the case has any `diagnostic` link at all; avoids a pointless fetch. */
  hasDiagnosticLinks: boolean;
}

const TOOL_LABELS: Record<DiagnosticsViewerOut['tool'], string> = {
  e3sm_diags: 'E3SM Diags',
  mpas_analysis: 'MPAS-Analysis',
};

// Axios surfaces transport detail such as "timeout of 30000ms exceeded",
// which tells a scientist nothing. Discovery reads a shared archive, so a
// failure here is nearly always that archive being slow or unreachable.
const FAILED_SUMMARY =
  'The diagnostics archive could not be read just now. The runs are still published; try again shortly.';

const ERROR_MESSAGES: Record<string, string> = {
  root_not_in_reviewed_archive:
    'This link is not on a reviewed diagnostics archive, so its viewers cannot be listed.',
};

const pad = (year: number) => String(year).padStart(4, '0');

const period = (viewer: DiagnosticsViewerOut): string =>
  viewer.startYear != null && viewer.endYear != null
    ? `${pad(viewer.startYear)}-${pad(viewer.endYear)}`
    : '';

const timeseries = (viewer: DiagnosticsViewerOut): string =>
  viewer.tsStartYear != null && viewer.tsEndYear != null
    ? `ts ${pad(viewer.tsStartYear)}-${pad(viewer.tsEndYear)}`
    : '';

/**
 * Lists the e3sm_diags and mpas-analysis viewers published for a case and
 * lets the user stage them for a side-by-side IICE comparison with viewers
 * from other cases.
 *
 * Production control and historical runs publish 20+ viewers, so the card is
 * collapsed by default behind a one-line summary, matching Change History.
 */
export const DiagnosticsViewersCard = ({
  caseId,
  caseName,
  hasDiagnosticLinks,
}: DiagnosticsViewersCardProps) => {
  const { data, loading, error, isFetching, refetch } = useCaseDiagnosticsViewers(
    hasDiagnosticLinks ? caseId : undefined,
  );
  const basket = useIiceBasket();
  const { toast } = useToast();
  const [isOpen, setIsOpen] = useState(false);

  const counts = useMemo(() => {
    const result = { total: 0, e3sm_diags: 0, mpas_analysis: 0, truncated: false };
    data?.sources.forEach((source) => {
      result.truncated ||= source.truncated;
      source.viewers.forEach((viewer) => {
        result.total += 1;
        result[viewer.tool] += 1;
      });
    });
    return result;
  }, [data]);

  if (!hasDiagnosticLinks) {
    return null;
  }

  const stagedHere = basket.entries.filter((entry) => entry.caseId === caseId).length;

  const summary = loading
    ? 'Reading the diagnostics archive…'
    : error
      ? FAILED_SUMMARY
      : counts.total === 0
        ? 'No e3sm_diags or MPAS-Analysis runs were found.'
        : [
            counts.e3sm_diags ? `${counts.e3sm_diags} E3SM Diags` : null,
            counts.mpas_analysis ? `${counts.mpas_analysis} MPAS-Analysis` : null,
            counts.truncated ? 'partial listing' : null,
            stagedHere ? `${stagedHere} staged for IICE` : null,
          ]
            .filter(Boolean)
            .join(' · ');

  const handleAdd = (viewer: DiagnosticsViewerOut) => {
    const label = suggestIiceLabel(caseName, viewer);
    const added = basket.add(toBasketEntry(viewer, caseId, caseName, label));
    if (!added) {
      toast({
        title: `IICE compares up to ${IICE_BASKET_MAX_PER_TOOL} ${TOOL_LABELS[viewer.tool]} runs`,
        description: 'Remove one from the comparison bar before adding another.',
        variant: 'destructive',
      });
    }
  };

  return (
    <Collapsible open={isOpen} onOpenChange={setIsOpen}>
      <Card>
        <CardHeader className="p-0">
          <CollapsibleTrigger asChild>
            <button
              type="button"
              className={cn(
                'flex w-full items-center gap-3 rounded-xl p-5 text-left',
                'transition-colors hover:bg-muted/30 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2',
              )}
            >
              <div className="min-w-0 flex-1">
                <CardTitle className="text-base">
                  Diagnostics Viewers{!loading && !error ? ` (${counts.total})` : ''}
                </CardTitle>
                <p
                  className={cn(
                    'mt-1 truncate text-sm text-muted-foreground',
                    error && 'text-red-600',
                  )}
                >
                  {summary}
                </p>
              </div>
              <ChevronDown
                aria-hidden="true"
                className={cn(
                  'h-5 w-5 shrink-0 text-muted-foreground transition-transform',
                  isOpen && 'rotate-180',
                )}
              />
            </button>
          </CollapsibleTrigger>
        </CardHeader>

        <CollapsibleContent>
          <CardContent className="space-y-4 border-t p-5">
            <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
              <p className="text-sm text-muted-foreground">
                Published e3sm_diags and MPAS-Analysis output for this case. Add a run here, add the
                matching run from another case, then compare them side by side in IICE.
              </p>
              <a
                href={IICE_ENTRANCE_URL}
                target="_blank"
                rel="noreferrer"
                className="inline-flex shrink-0 items-center gap-1 text-sm text-slate-600 underline-offset-4 hover:underline"
              >
                About IICE
                <ExternalLink className="h-3.5 w-3.5" aria-hidden="true" />
              </a>
            </div>

            {loading ? (
              <p className="text-sm text-slate-500">Reading the diagnostics archive…</p>
            ) : error ? (
              <div className="space-y-2">
                <p className="text-sm text-red-600">{FAILED_SUMMARY}</p>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => void refetch()}
                  disabled={isFetching}
                >
                  <RotateCw className="mr-1 h-3.5 w-3.5" aria-hidden="true" />
                  {isFetching ? 'Retrying…' : 'Try again'}
                </Button>
              </div>
            ) : data && data.sources.length > 0 ? (
              <div className="space-y-5">
                {data.sources.map((source) => (
                  <SourceViewers
                    key={source.linkId}
                    source={source}
                    isAdded={basket.has}
                    isFull={basket.isFull}
                    onAdd={handleAdd}
                    onRemove={basket.remove}
                  />
                ))}
              </div>
            ) : (
              <p className="text-sm text-slate-500">No diagnostics viewers were found.</p>
            )}
          </CardContent>
        </CollapsibleContent>
      </Card>
    </Collapsible>
  );
};

interface SourceViewersProps {
  source: DiagnosticsViewerSourceOut;
  isAdded: (url: string) => boolean;
  isFull: (viewer: Pick<DiagnosticsViewerOut, 'tool' | 'comparison'>) => boolean;
  onAdd: (viewer: DiagnosticsViewerOut) => void;
  onRemove: (url: string) => void;
}

interface ViewerGroup {
  key: string;
  title: string;
  viewers: DiagnosticsViewerOut[];
  /** Groups people rarely want first are collapsed inside the card. */
  defaultOpen: boolean;
}

/**
 * Order groups by how people use them: model-vs-obs first, then model-vs-model
 * (often the bulk of the rows), then MPAS-Analysis.
 */
const groupViewers = (viewers: DiagnosticsViewerOut[]): ViewerGroup[] => {
  const obs = viewers.filter((v) => v.tool === 'e3sm_diags' && v.comparison !== 'model_vs_model');
  const mvm = viewers.filter((v) => v.tool === 'e3sm_diags' && v.comparison === 'model_vs_model');
  const mpas = viewers.filter((v) => v.tool === 'mpas_analysis');

  const groups: ViewerGroup[] = [];
  if (obs.length) {
    groups.push({
      key: 'obs',
      title: `${TOOL_LABELS.e3sm_diags} · model vs observations`,
      viewers: obs,
      defaultOpen: true,
    });
  }
  if (mvm.length) {
    groups.push({
      key: 'mvm',
      title: `${TOOL_LABELS.e3sm_diags} · model vs model`,
      viewers: mvm,
      defaultOpen: false,
    });
  }
  if (mpas.length) {
    groups.push({
      key: 'mpas',
      title: TOOL_LABELS.mpas_analysis,
      viewers: mpas,
      defaultOpen: false,
    });
  }
  return groups;
};

const SourceViewers = ({ source, isAdded, isFull, onAdd, onRemove }: SourceViewersProps) => {
  const groups = useMemo(() => groupViewers(source.viewers), [source.viewers]);

  if (source.error) {
    return (
      <div className="rounded-lg border border-amber-200 bg-amber-50/60 px-3 py-2.5 text-sm text-amber-900">
        <p className="break-all font-medium">{source.rootUrl}</p>
        <p>{ERROR_MESSAGES[source.error] ?? `Viewers could not be listed (${source.error}).`}</p>
      </div>
    );
  }

  if (source.viewers.length === 0) {
    return (
      <div className="rounded-lg border border-slate-200/80 bg-white/80 px-3 py-2.5 text-sm text-slate-500">
        <p className="break-all font-medium text-slate-700">{source.rootUrl}</p>
        <p>No e3sm_diags or MPAS-Analysis runs were found under this archive root.</p>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <a
        href={source.rootUrl}
        target="_blank"
        rel="noreferrer"
        className="inline-flex items-center gap-1 break-all text-xs text-slate-500 underline-offset-4 hover:underline"
      >
        {source.rootUrl}
        <ExternalLink className="h-3 w-3 shrink-0" aria-hidden="true" />
      </a>
      {source.truncated ? (
        <p className="text-xs text-amber-700">
          The archive has more runs than were listed; only the first ones are shown.
        </p>
      ) : null}
      {groups.map((group) => (
        <ViewerGroupSection
          key={group.key}
          group={group}
          isAdded={isAdded}
          isFull={isFull}
          onAdd={onAdd}
          onRemove={onRemove}
        />
      ))}
    </div>
  );
};

interface ViewerGroupSectionProps {
  group: ViewerGroup;
  isAdded: (url: string) => boolean;
  isFull: (viewer: Pick<DiagnosticsViewerOut, 'tool' | 'comparison'>) => boolean;
  onAdd: (viewer: DiagnosticsViewerOut) => void;
  onRemove: (url: string) => void;
}

const ViewerGroupSection = ({
  group,
  isAdded,
  isFull,
  onAdd,
  onRemove,
}: ViewerGroupSectionProps) => {
  const [open, setOpen] = useState(group.defaultOpen);
  const staged = group.viewers.filter((viewer) => isAdded(viewer.url)).length;

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
              'h-4 w-4 shrink-0 text-muted-foreground transition-transform',
              open && 'rotate-180',
            )}
          />
          <h3 className="text-sm font-semibold text-slate-900">
            {group.title}{' '}
            <span className="font-normal text-slate-500">({group.viewers.length})</span>
          </h3>
          {staged > 0 ? (
            <Badge variant="secondary" className="ml-auto">
              {staged} staged
            </Badge>
          ) : null}
        </button>
      </CollapsibleTrigger>
      <CollapsibleContent>
        <div className="mt-1.5 space-y-1.5 pl-6">
          {group.viewers.map((viewer) => (
            <ViewerRow
              key={viewer.url}
              viewer={viewer}
              added={isAdded(viewer.url)}
              full={isFull(viewer)}
              onAdd={() => onAdd(viewer)}
              onRemove={() => onRemove(viewer.url)}
            />
          ))}
        </div>
      </CollapsibleContent>
    </Collapsible>
  );
};

interface ViewerRowProps {
  viewer: DiagnosticsViewerOut;
  added: boolean;
  /** The tool's comparison group already holds the maximum IICE can show well. */
  full: boolean;
  onAdd: () => void;
  onRemove: () => void;
}

const ViewerRow = ({ viewer, added, full, onAdd, onRemove }: ViewerRowProps) => {
  const isModelVsModel = viewer.comparison === 'model_vs_model';

  return (
    <div className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-slate-200/80 bg-white/80 px-3 py-2">
      <div className="flex min-w-0 flex-wrap items-center gap-2 text-sm">
        <span className="font-medium text-slate-900">{period(viewer)}</span>
        {timeseries(viewer) ? <span className="text-slate-500">{timeseries(viewer)}</span> : null}
        {viewer.subsection ? (
          <span className="truncate text-slate-500" title={viewer.subsection}>
            {viewer.subsection}
          </span>
        ) : null}
        {isModelVsModel ? (
          <TooltipProvider delayDuration={150}>
            <Tooltip>
              <TooltipTrigger asChild>
                <span className="inline-flex items-center gap-1 text-xs text-slate-500">
                  <Info className="h-3.5 w-3.5" aria-hidden="true" />
                  needs reference case
                </span>
              </TooltipTrigger>
              <TooltipContent className="max-w-xs text-xs">
                IICE needs the reference case name to resolve model-vs-model plots.
                {viewer.referenceHint ? ` zppy tagged this run “${viewer.referenceHint}”.` : ''} You
                can enter it in the comparison bar after adding.
              </TooltipContent>
            </Tooltip>
          </TooltipProvider>
        ) : null}
      </div>
      <div className="flex shrink-0 items-center gap-1.5">
        <Button asChild variant="ghost" size="sm">
          <a href={viewer.url} target="_blank" rel="noreferrer">
            Open
            <ExternalLink className="ml-1 h-3.5 w-3.5" aria-hidden="true" />
          </a>
        </Button>
        {added ? (
          <Button variant="secondary" size="sm" onClick={onRemove} aria-pressed="true">
            <Check className="mr-1 h-3.5 w-3.5" aria-hidden="true" />
            Added
          </Button>
        ) : full ? (
          <TooltipProvider delayDuration={150}>
            <Tooltip>
              <TooltipTrigger asChild>
                <span>
                  <Button variant="outline" size="sm" disabled aria-pressed="false">
                    <Plus className="mr-1 h-3.5 w-3.5" aria-hidden="true" />
                    Add to IICE
                  </Button>
                </span>
              </TooltipTrigger>
              <TooltipContent className="text-xs">
                IICE compares up to {IICE_BASKET_MAX_PER_TOOL} {TOOL_LABELS[viewer.tool]} runs.
                Remove one in the comparison bar first.
              </TooltipContent>
            </Tooltip>
          </TooltipProvider>
        ) : (
          <Button variant="outline" size="sm" onClick={onAdd} aria-pressed="false">
            <Plus className="mr-1 h-3.5 w-3.5" aria-hidden="true" />
            Add to IICE
          </Button>
        )}
      </div>
    </div>
  );
};
