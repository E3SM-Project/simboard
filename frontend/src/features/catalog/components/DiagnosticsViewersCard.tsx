import { Check, ExternalLink, Info, Plus } from 'lucide-react';
import { useMemo } from 'react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';
import { useToast } from '@/hooks/use-toast';
import { useCaseDiagnosticsViewers } from '@/lib/catalog/hooks/useCaseDiagnosticsViewers';
import { IICE_ENTRANCE_URL, suggestIiceLabel } from '@/lib/iice';
import { toBasketEntry, useIiceBasket } from '@/lib/iiceBasket';
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

const ERROR_MESSAGES: Record<string, string> = {
  root_not_in_reviewed_archive:
    'This link is not on a reviewed diagnostics archive, so its viewers cannot be listed.',
};

const period = (viewer: DiagnosticsViewerOut): string =>
  viewer.startYear != null && viewer.endYear != null
    ? `${String(viewer.startYear).padStart(4, '0')}-${String(viewer.endYear).padStart(4, '0')}`
    : '';

const timeseries = (viewer: DiagnosticsViewerOut): string =>
  viewer.tsStartYear != null && viewer.tsEndYear != null
    ? `ts ${String(viewer.tsStartYear).padStart(4, '0')}-${String(viewer.tsEndYear).padStart(4, '0')}`
    : '';

/**
 * Lists the e3sm_diags and mpas-analysis viewers published for a case and
 * lets the user stage them for a side-by-side IICE comparison with viewers
 * from other cases.
 */
export const DiagnosticsViewersCard = ({
  caseId,
  caseName,
  hasDiagnosticLinks,
}: DiagnosticsViewersCardProps) => {
  const { data, loading, error } = useCaseDiagnosticsViewers(
    hasDiagnosticLinks ? caseId : undefined,
  );
  const basket = useIiceBasket();
  const { toast } = useToast();

  const viewerCount = useMemo(
    () => data?.sources.reduce((total, source) => total + source.viewers.length, 0) ?? 0,
    [data],
  );

  if (!hasDiagnosticLinks) {
    return null;
  }

  const handleAdd = (viewer: DiagnosticsViewerOut) => {
    const label = suggestIiceLabel(caseName, viewer);
    const added = basket.add(toBasketEntry(viewer, caseId, caseName, label));
    if (!added) {
      toast({
        title: 'Comparison is full',
        description: 'Remove a viewer from the IICE comparison before adding another.',
        variant: 'destructive',
      });
    }
  };

  return (
    <section>
      <Card className="border-slate-200 shadow-sm">
        <CardContent className="space-y-4 p-5">
          <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
            <div>
              <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
                <h2 className="text-lg font-semibold text-slate-950">Diagnostics Viewers</h2>
                {viewerCount > 0 ? <p className="text-sm text-slate-500">({viewerCount})</p> : null}
              </div>
              <p className="text-sm text-muted-foreground">
                Published e3sm_diags and MPAS-Analysis output for this case. Add viewers here and
                from other cases, then compare them side by side in IICE.
              </p>
            </div>
            <a
              href={IICE_ENTRANCE_URL}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-1 text-sm text-slate-600 underline-offset-4 hover:underline"
            >
              About IICE
              <ExternalLink className="h-3.5 w-3.5" aria-hidden="true" />
            </a>
          </div>

          {loading ? (
            <p className="text-sm text-slate-500">Reading the diagnostics archive…</p>
          ) : error ? (
            <p className="text-sm text-red-600">Could not list diagnostics viewers: {error}</p>
          ) : data && data.sources.length > 0 ? (
            <div className="space-y-5">
              {data.sources.map((source) => (
                <SourceViewers
                  key={source.linkId}
                  source={source}
                  isAdded={basket.has}
                  onAdd={handleAdd}
                  onRemove={basket.remove}
                />
              ))}
            </div>
          ) : (
            <p className="text-sm text-slate-500">No diagnostics viewers were found.</p>
          )}
        </CardContent>
      </Card>
    </section>
  );
};

interface SourceViewersProps {
  source: DiagnosticsViewerSourceOut;
  isAdded: (url: string) => boolean;
  onAdd: (viewer: DiagnosticsViewerOut) => void;
  onRemove: (url: string) => void;
}

const SourceViewers = ({ source, isAdded, onAdd, onRemove }: SourceViewersProps) => {
  const byTool = useMemo(() => {
    const groups = new Map<DiagnosticsViewerOut['tool'], DiagnosticsViewerOut[]>();
    source.viewers.forEach((viewer) => {
      const list = groups.get(viewer.tool) ?? [];
      list.push(viewer);
      groups.set(viewer.tool, list);
    });
    return groups;
  }, [source.viewers]);

  if (source.error) {
    return (
      <div className="rounded-lg border border-amber-200 bg-amber-50/60 px-3 py-2.5 text-sm text-amber-900">
        <p className="font-medium break-all">{source.rootUrl}</p>
        <p>{ERROR_MESSAGES[source.error] ?? `Viewers could not be listed (${source.error}).`}</p>
      </div>
    );
  }

  if (source.viewers.length === 0) {
    return (
      <div className="rounded-lg border border-slate-200/80 bg-white/80 px-3 py-2.5 text-sm text-slate-500">
        <p className="font-medium break-all text-slate-700">{source.rootUrl}</p>
        <p>No e3sm_diags or MPAS-Analysis runs were found under this archive root.</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <a
        href={source.rootUrl}
        target="_blank"
        rel="noreferrer"
        className="inline-flex items-center gap-1 text-xs text-slate-500 underline-offset-4 hover:underline break-all"
      >
        {source.rootUrl}
        <ExternalLink className="h-3 w-3 shrink-0" aria-hidden="true" />
      </a>
      {source.truncated ? (
        <p className="text-xs text-amber-700">
          The archive has more runs than were listed; only the first ones are shown.
        </p>
      ) : null}
      {[...byTool.entries()].map(([tool, viewers]) => (
        <div key={tool} className="space-y-2">
          <h3 className="text-sm font-semibold text-slate-900">
            {TOOL_LABELS[tool]}{' '}
            <span className="font-normal text-slate-500">({viewers.length})</span>
          </h3>
          <div className="space-y-1.5">
            {viewers.map((viewer) => (
              <ViewerRow
                key={viewer.url}
                viewer={viewer}
                added={isAdded(viewer.url)}
                onAdd={() => onAdd(viewer)}
                onRemove={() => onRemove(viewer.url)}
              />
            ))}
          </div>
        </div>
      ))}
    </div>
  );
};

interface ViewerRowProps {
  viewer: DiagnosticsViewerOut;
  added: boolean;
  onAdd: () => void;
  onRemove: () => void;
}

const ViewerRow = ({ viewer, added, onAdd, onRemove }: ViewerRowProps) => {
  const isModelVsModel = viewer.comparison === 'model_vs_model';

  return (
    <div className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-slate-200/80 bg-white/80 px-3 py-2">
      <div className="flex min-w-0 flex-wrap items-center gap-2 text-sm">
        {viewer.comparison ? (
          <Badge variant={isModelVsModel ? 'secondary' : 'outline'}>
            {isModelVsModel ? 'model vs model' : 'model vs obs'}
          </Badge>
        ) : (
          <Badge variant="outline">climatology</Badge>
        )}
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
                <span className="inline-flex items-center text-slate-400">
                  <Info className="h-3.5 w-3.5" aria-label="Reference case needed" />
                </span>
              </TooltipTrigger>
              <TooltipContent className="max-w-xs text-xs">
                IICE needs the reference case name to resolve model-vs-model plots.
                {viewer.referenceHint ? ` zppy tagged this run “${viewer.referenceHint}”.` : ''} You
                can edit it in the comparison bar.
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
