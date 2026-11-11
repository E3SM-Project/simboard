import { Check, ExternalLink, Plus } from 'lucide-react';
import { useEffect, useState } from 'react';

import { Alert } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { MAX_COMPARED_RUNS } from '@/features/diagnostics/compareState';
import {
  type DiagnosticAnalysis,
  diagnosticClimatologyPeriod,
  diagnosticIdentifier,
  diagnosticPeriod,
  diagnosticTimeSeriesPeriod,
  diagnosticTitle,
  type DiagnosticToolFilter,
  periodGroups,
  RUN_GROUPS,
  runGroup,
} from '@/features/diagnostics/discoveryState';
import type { DiagnosticsRunOut, DiagnosticsSourceOut } from '@/features/diagnostics/types';
import { cn } from '@/lib/utils';

const ANALYSES = [
  { key: 'all', label: 'All' },
  { key: 'climatology', label: 'Climatology' },
  { key: 'time_series', label: 'Time Series' },
] as const;

const TOOLS = [
  { key: 'all', label: 'All' },
  { key: 'e3sm_diags', label: 'E3SM Diags' },
  { key: 'mpas_analysis', label: 'MPAS-Analysis' },
] as const;

export interface DiagnosticRunListProps {
  sources: DiagnosticsSourceOut[];
  id: string;
  isAdded: (url: string) => boolean;
  /** True when the run's comparison group is at its selection limit. */
  isFull?: (run: DiagnosticsRunOut) => boolean;
  onAdd: (run: DiagnosticsRunOut) => void;
  onRemove: (url: string) => void;
  analysis?: DiagnosticAnalysis;
  onAnalysisChange?: (analysis: DiagnosticAnalysis) => void;
  tool?: DiagnosticToolFilter;
  onToolChange?: (tool: DiagnosticToolFilter) => void;
}

/** Shared discovery presentation; callers own staging or workspace drafts. */
export const DiagnosticRunList = ({
  sources,
  id,
  analysis: selectedAnalysis,
  onAnalysisChange,
  tool: selectedTool,
  onToolChange,
  ...actions
}: DiagnosticRunListProps) => {
  const [localAnalysis, setLocalAnalysis] = useState<DiagnosticAnalysis>('all');
  const [localTool, setLocalTool] = useState<DiagnosticToolFilter>('all');
  const requestedTool = selectedTool ?? localTool;
  const activeTool = periodGroups(sources, 'all', requestedTool).length ? requestedTool : 'all';
  const filters = ANALYSES.map((analysis) => ({
    ...analysis,
    groups: periodGroups(sources, analysis.key, activeTool),
  }));
  const requestedAnalysis = selectedAnalysis ?? localAnalysis;
  const activeAnalysis = filters.find((analysis) => analysis.key === requestedAnalysis)?.groups
    .length
    ? requestedAnalysis
    : 'all';
  const tools = TOOLS.map((tool) => ({
    ...tool,
    count: periodGroups(sources, activeAnalysis, tool.key).reduce(
      (count, [, runs]) => count + runs.length,
      0,
    ),
  }));

  useEffect(() => {
    if (requestedAnalysis === activeAnalysis) return;
    setLocalAnalysis(activeAnalysis);
    onAnalysisChange?.(activeAnalysis);
  }, [requestedAnalysis, activeAnalysis, onAnalysisChange]);

  useEffect(() => {
    if (requestedTool === activeTool) return;
    setLocalTool(activeTool);
    onToolChange?.(activeTool);
  }, [requestedTool, activeTool, onToolChange]);

  const groupedRuns = (
    <div className="space-y-3">
      {filters
        .find((analysis) => analysis.key === activeAnalysis)
        ?.groups.map(([period, runs], index) => (
          <section key={period} aria-labelledby={`${id}-${activeAnalysis}-period-${index}`}>
            <h4
              id={`${id}-${activeAnalysis}-period-${index}`}
              className="mb-1 flex items-center gap-2 border-b pb-1 text-xs font-semibold text-foreground"
            >
              {period}
              <span className="text-xs font-normal text-muted-foreground">{runs.length} runs</span>
            </h4>
            <ul className="space-y-1">
              {runs.map((run) => (
                <DiagnosticRunRow key={run.url} run={run} {...actions} />
              ))}
            </ul>
          </section>
        ))}
    </div>
  );

  return (
    <div className="min-w-0 max-w-3xl space-y-2">
      <div className="space-y-2">
        {sources.map((source, index) => (
          <section
            key={source.rootUrl}
            id={`${id}-source-${index}`}
            tabIndex={-1}
            className="scroll-mt-20 rounded focus-visible:ring-2 focus-visible:ring-ring"
          >
            {/* Preserve existing resource shortcuts and bookmarked tool-group anchors. */}
            {[...new Set(source.runs.map(runGroup))].map((group) => (
              <span
                key={group}
                id={`${id}-source-${index}-${group}`}
                tabIndex={-1}
                role="group"
                aria-label={`${RUN_GROUPS.find((item) => item.key === group)?.title ?? group} in ${source.label || 'diagnostics directory'}; runs grouped by period below`}
                className="block scroll-mt-20 rounded focus-visible:ring-2 focus-visible:ring-ring"
              />
            ))}
            <a
              href={source.rootUrl}
              target="_blank"
              rel="noreferrer"
              title={source.rootUrl}
              className="inline-flex max-w-full items-center gap-1 rounded text-xs font-medium text-blue-600 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              <span className="min-w-0 break-words [overflow-wrap:anywhere]">
                {source.label || 'Browse diagnostics directory'}
              </span>
              <ExternalLink className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
              <span className="sr-only"> (opens in a new tab)</span>
            </a>
            {source.error ? (
              <Alert variant="warning" className="mt-1 px-2 py-1.5 text-xs">
                {source.error === 'url_not_allowed'
                  ? 'This directory is not on a supported public diagnostics server.'
                  : 'This directory could not be read. Browse the original output or try again.'}
              </Alert>
            ) : null}
            {source.partial ? (
              <Alert variant="warning" className="mt-1 px-2 py-1.5 text-xs">
                Run discovery is incomplete. Open the directory or retry to check for missing runs.
              </Alert>
            ) : null}
          </section>
        ))}
      </div>
      <div className="space-y-1">
        <p id={`${id}-tool-label`} className="text-xs font-medium text-muted-foreground">
          Tool
        </p>
        <div
          role="group"
          aria-label="Filter diagnostics by tool"
          aria-labelledby={`${id}-tool-label`}
          className="flex w-fit max-w-full flex-wrap gap-0.5 rounded-lg bg-muted p-1"
        >
          {tools.map((tool) => (
            <Button
              key={tool.key}
              type="button"
              variant="ghost"
              size="sm"
              className={cn(
                'h-7 gap-1 px-2 text-xs',
                activeTool === tool.key &&
                  'bg-background text-foreground shadow hover:bg-background',
              )}
              aria-pressed={activeTool === tool.key}
              disabled={tool.key !== 'all' && !tool.count}
              onClick={() => {
                setLocalTool(tool.key);
                onToolChange?.(tool.key);
              }}
            >
              {tool.label} <span>({tool.count})</span>
            </Button>
          ))}
        </div>
      </div>
      <Tabs
        value={activeAnalysis}
        onValueChange={(value) => {
          setLocalAnalysis(value as DiagnosticAnalysis);
          onAnalysisChange?.(value as DiagnosticAnalysis);
        }}
      >
        <p id={`${id}-analysis-label`} className="mb-1 text-xs font-medium text-muted-foreground">
          Analysis
        </p>
        <TabsList
          aria-label="Filter diagnostics by analysis"
          aria-labelledby={`${id}-analysis-label`}
          className="grid w-full max-w-sm grid-cols-3"
        >
          {filters.map((analysis) => (
            <TabsTrigger
              key={analysis.key}
              value={analysis.key}
              disabled={analysis.key !== 'all' && !analysis.groups.length}
              className="gap-1 px-2 text-xs"
            >
              {analysis.label}{' '}
              <span>({analysis.groups.reduce((count, [, runs]) => count + runs.length, 0)})</span>
            </TabsTrigger>
          ))}
        </TabsList>
        <TabsContent value={activeAnalysis}>{groupedRuns}</TabsContent>
      </Tabs>
    </div>
  );
};

const DiagnosticRunRow = ({
  run,
  isAdded,
  isFull,
  onAdd,
  onRemove,
}: Pick<DiagnosticRunListProps, 'isAdded' | 'isFull' | 'onAdd' | 'onRemove'> & {
  run: DiagnosticsRunOut;
}) => {
  const selected = isAdded(run.url);
  const full = !selected && Boolean(isFull?.(run));
  const title = diagnosticTitle(run);
  const identifier = diagnosticIdentifier(run);
  const tool = run.tool === 'e3sm_diags' ? 'E3SM Diags' : 'MPAS-Analysis';
  const climatology = diagnosticClimatologyPeriod(run);
  const timeSeries = diagnosticTimeSeriesPeriod(run);
  const combinedPeriods =
    climatology && timeSeries ? `Climatology: ${climatology} · Time Series: ${timeSeries}` : '';
  const label = `${tool} · ${identifier} · ${title} · ${combinedPeriods || diagnosticPeriod(run)}`;

  return (
    <li
      className={cn(
        'flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1 rounded-md border px-2 py-1.5 text-sm',
        selected ? 'border-muted-foreground bg-muted-subtle' : 'border-border bg-card',
      )}
    >
      <div className="min-w-0 flex-1 basis-48">
        <p className="text-xs font-medium text-foreground">{title}</p>
        <p className="text-xs text-muted-foreground [overflow-wrap:anywhere]">
          {tool} · <span className="font-mono">{identifier}</span>
        </p>
        {combinedPeriods ? (
          <p className="text-xs text-muted-foreground">{combinedPeriods}</p>
        ) : null}
      </div>
      <div className="ml-auto flex shrink-0 items-center gap-1">
        <Button asChild variant="ghost" size="sm" className="h-7 px-2 text-xs">
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
          className="h-7 w-[4.5rem] px-2 text-xs"
          aria-pressed={selected}
          aria-label={`${selected ? 'Remove' : 'Add'} ${label}`}
          disabled={full}
          title={
            full
              ? `Compare up to ${MAX_COMPARED_RUNS} runs of one kind. Remove one first.`
              : undefined
          }
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
    </li>
  );
};
